import re
from dataclasses import dataclass
from datetime import date

from . import config
from .actions import SLOTS, Draft, ask_missing, execute, parse_date
from .answerer import Answerer, norm
from .data_loader import Corpus
from .llm import LLM
from .router import Intent, Router

CAPABILITIES = ("I can help with room listings and prices, house rules and policies, your own support "
                "tickets, and raising maintenance or other requests.")

REFUSALS = {
    Intent.out_of_scope: "I'm only able to help with resident support (your stay, bookings, billing, maintenance and house rules). ",
    Intent.legal_financial_advice: "I can't give legal or financial advice. I can only explain what our policies say. ",
    Intent.injection: "I can't do that, and I have to keep following my support rules. ",
    Intent.other_resident_data: "I can't share any information about other residents. ",
    Intent.personal_info_change: ("I'm not able to change personal details through chat. Please contact your "
                                  "property manager for that. "),
}


@dataclass
class Reply:
    text: str
    kind: str           # answer | idk | refusal | ask | summary | done | info
    intent: str = ""


class Bot:
    def __init__(self, resident_id: str, corpus: Corpus, llm: LLM, today: date | None = None,
                 main_model: str = config.MAIN_MODEL, router_model: str = config.ROUTER_MODEL,
                 use_judge: bool = config.USE_JUDGE):
        self.rid, self.corpus, self.llm = resident_id, corpus, llm
        self.today = today or date.today()
        self.router = Router(llm, router_model, corpus.rules_text)
        self.answerer = Answerer(llm, main_model, router_model, corpus, resident_id, use_judge)
        self.history: list[tuple[str, str]] = []
        self.user_texts: list[str] = []
        self.pending: Draft | None = None

    # ---- helpers --------------------------------------------------------
    def _history(self) -> str:
        return "\n".join(f"{who}: {t}" for who, t in self.history[-config.HISTORY_TURNS:])

    def _pending_state(self) -> str:
        p = self.pending
        if not p:
            return "none"
        return f"type={p.type}; fields={p.fields}; awaiting_confirmation={p.awaiting}; missing={p.missing()}"

    def _reminder(self) -> str:
        if self.pending and self.pending.awaiting:
            return '\n\n(Your pending request is still waiting: reply "yes" to confirm or "no" to discard.)'
        return ""

    def _finish(self, msg: str, reply: Reply) -> Reply:
        # Output guard: never emit another resident's IDs (computed from data at runtime).
        upper = reply.text.upper()
        if any(i.upper() in upper for i in self.corpus.foreign_identifiers(self.rid)):
            reply = Reply(REFUSALS[Intent.other_resident_data] + CAPABILITIES, "refusal", reply.intent)
        self.history += [("User", msg), ("Assistant", reply.text)]
        return reply

    def _merge_slots(self, draft: Draft, r) -> None:
        corpus_user_text = norm(" ".join(self.user_texts))
        for k in SLOTS:
            v = getattr(r, k, None)
            if v in (None, ""):
                continue
            v = str(v).strip()
            # Free-text location slots must literally come from what the resident said.
            if k in ("property_name", "room_number") and norm(v) not in corpus_user_text:
                continue
            if k == "move_in_date" and not parse_date(v):
                continue
            if k == "room_number":
                v = re.sub(r"^(room|rm|unit)\s*[#.:]?\s*", "", v, flags=re.I) or v
            draft.fields[k] = v

    # ---- main entry -----------------------------------------------------
    def handle(self, msg: str) -> Reply:
        self.user_texts.append(msg)
        r = self.router.route(msg, self._history(), self._pending_state(), self.today)
        reply = self._dispatch(msg, r)
        # pending-action bookkeeping
        if self.pending and r.intent not in (Intent.create_ticket, Intent.cancel_booking, Intent.confirm):
            self.pending.idle += 1
            if self.pending.idle > config.PENDING_MAX_IDLE:
                self.pending = None
                reply.text += "\n\n(I've dropped your earlier unfinished request; nothing was submitted.)"
        return self._finish(msg, reply)

    def _dispatch(self, msg: str, r) -> Reply:
        intent = r.intent
        if intent in REFUSALS:
            return Reply(REFUSALS[intent] + CAPABILITIES + self._reminder(), "refusal", intent.value)
        if intent == Intent.smalltalk:
            return Reply("Hi! " + CAPABILITIES + " How can I help?" + self._reminder(), "info", intent.value)
        if intent == Intent.deny:
            if self.pending:
                self.pending = None
                return Reply("Okay, I've discarded that request. Nothing was submitted.", "info", intent.value)
            return Reply("There's nothing pending right now. How can I help?", "info", intent.value)
        if intent == Intent.confirm:
            return self._confirm(intent)
        if intent in (Intent.create_ticket, Intent.cancel_booking):
            return self._collect(r)
        # info_question
        a = self.answerer.answer(msg, self._history(), self.today)
        return Reply(a.text + self._reminder(), "answer" if a.grounded else "idk", intent.value)

    # ---- action flow ----------------------------------------------------
    def _confirm(self, intent: Intent) -> Reply:
        p = self.pending
        if not p or not p.awaiting:
            if p:
                return Reply(ask_missing(p), "ask", intent.value)
            return Reply("There's nothing waiting for confirmation, so nothing has been changed. "
                         "Tell me what you'd like to do.", "info", intent.value)
        if p.fingerprint() != p.fp:  # details changed after the summary was shown
            p.awaiting = False
            return self._summary(p, intent)
        ticket = execute(p, self.corpus, self.rid)
        self.pending = None
        if p.type == "cancel_booking":
            text = (f"Your cancellation request {ticket['ticket_id']} has been submitted to the property team. "
                    "It is not final until they process it, and I can't confirm any refund amount.")
        else:
            text = f"Done. Your request has been submitted as {ticket['ticket_id']} (status: open, priority: {ticket['priority']})."
        return Reply(text, "done", intent.value)

    def _collect(self, r) -> Reply:
        p = self.pending
        prefix = ""
        if p is None or p.type != r.intent.value:
            if p is not None:
                prefix = "I've discarded your previous unfinished request. "
            p = self.pending = Draft(type=r.intent.value)
        before = p.fingerprint()
        self._merge_slots(p, r)
        p.idle = 0
        if p.missing():
            p.awaiting = False
            return Reply(prefix + ask_missing(p), "ask", r.intent.value)
        changed = p.awaiting and p.fingerprint() != before
        p.awaiting = False
        s = self._summary(p, r.intent)
        if changed:
            s.text = "Updated. " + s.text
        s.text = prefix + s.text
        return s

    def _summary(self, p: Draft, intent: Intent) -> Reply:
        f = p.fields
        lines = ["Here is what I'm about to submit. Nothing has been submitted yet:"]
        if p.type == "cancel_booking":
            move_in = parse_date(f["move_in_date"])
            days = (move_in - self.today).days
            q = (f"A resident wants to cancel their booking. Their move-in date is {move_in.isoformat()}, which is "
                 f"{days} days from today ({self.today.isoformat()}); a negative number means it has already passed. "
                 "According to the policies, what happens to their deposit / notice period? One or two sentences.")
            pol = self.answerer.answer(q, "", self.today)
            lines += ["• Action: booking cancellation request", f"• Property: {f['property_name']}",
                      f"• Move-in date: {f['move_in_date']} ({days} days from today)"]
            if f.get("booking_reference"):
                lines.append(f"• Reference: {f['booking_reference']}")
            if pol.grounded:
                lines.append(f"• Policy: {pol.text}")
            lines.append("Note: I can't look up your booking in my records, so this goes to the property team as a "
                         "request and I can't promise a refund amount.")
        else:
            lines += [f"• Type: {(f.get('category') or 'general')} request", f"• Details: {f['description']}"]
            if f.get("property_name") or f.get("room_number"):
                lines.append(f"• Location: {f.get('property_name', '')} {('Room ' + f['room_number']) if f.get('room_number') else ''}".rstrip())
            prio = f.get("priority") or "medium"
            lines.append(f"• Priority: {prio}")
            if (f.get("category") or "").lower() == "maintenance":
                kind = "urgent" if prio == "high" else "non-urgent"
                t = self.answerer.answer(
                    f"How quickly are {kind} maintenance issues normally handled according to the policy? One sentence.",
                    "", self.today)
                if t.grounded:
                    lines.append(f"• Expected handling: {t.text}")
        p.awaiting, p.fp = True, p.fingerprint()
        lines.append('\nReply "yes" to confirm and submit, "no" to discard, or tell me what to change.')
        return Reply("\n".join(lines), "summary", intent.value)
