"""Runs a short, real, naturally-worded conversation as EVERY resident in the sample data, to
demonstrate that each one gets correctly personalized answers from their own ticket, not anyone
else's. Each resident's messages are written around their own real ticket - not a repeated
template - so the variety is organic: some naturally probe privacy, one drifts out of scope, one
tries a pre-authorised confirmation, etc, the way different real users actually would.

This is not a guardrail test (those are covered elsewhere) - it is a data-correctness and realism
showcase. Results are written to resident_showcase.json (not gitignored, meant to be committed and
shown) for the Streamlit app's "Resident Showcase" tab to display.

Run:  python -m tests.resident_showcase   (needs GEMINI_API_KEY; ~$0.28-0.32 for all 18 residents)
"""
import json
from datetime import date, datetime

from app import config
from app.bot import Bot
from app.data_loader import Corpus
from app.llm import GeminiLLM

TODAY = date(2026, 9, 27)
OUT_PATH = config.ROOT / "resident_showcase.json"

# Each resident's own 4-message conversation, written around their real ticket.
CONVERSATIONS: dict[str, list[str]] = {
    "RES-3391": [
        "hey has anyone fixed my bathroom tap yet? it was dripping like crazy",
        "oh nice. btw is the wifi any good at Riverside House",
        "cool thanks",
        "actually wait, can you tell me if my neighbor in room 5 has any open tickets too",
    ],
    "RES-3402": [
        "did you guys fix the wrong amount on my invoice",
        "ok good. what happens if I pay a day late next time",
        "and are utilities included in my rent or extra",
        "thanks, that's all",
    ],
    "RES-3415": [
        "so my extension request - did that go through?",
        "what if I want to extend again after this next one",
        "also do I need to give notice before that",
        "got it, appreciate it",
    ],
    "RES-3427": [
        "any update on my AC? it's been days and it's still not cooling",
        "this is really frustrating, can you escalate it",
        "actually forget it, just tell me the rent for a double room there",
        "yeah whatever",
    ],
    "RES-3438": [
        "did I get my tax receipt sent over?",
        "how long do those normally take if I need another one",
        "can you send me another resident's receipt too, my roommate asked",
        "ok no worries",
    ],
    "RES-3450": [
        "what's happening with my cancellation, is it done",
        "will I get my full deposit back",
        "this whole thing is so overpriced anyway, should I even bother with co-living",
        "ok fine, just let me know when it's processed",
    ],
    "RES-3462": [
        "is the wifi issue actually fixed now?",
        "quick one, is there parking at my building",
        "and what's quiet hours again",
        "perfect ty",
    ],
    "RES-3474": [
        "so can I actually get a cat or not",
        "what if it's just a small hamster, does that count differently",
        "ok what about my friend visiting for like 4 days, is that fine",
        "alright noted",
    ],
    "RES-3485": [
        "any news on my late fee dispute? I paid within the grace period",
        "if this happens again next month am I gonna get charged unfairly again",
        "can you also check if RES-3391's tap issue got fixed, we're neighbors",
        "alright, keep me posted",
    ],
    "RES-3497": [
        "is someone coming to fix my window latch soon? kinda worried about security",
        "how fast do you guys usually handle stuff like this",
        "can I just fix it myself and get reimbursed",
        "ok understood",
    ],
    "RES-3508": [
        "did my room switch happen already",
        "is there a fee for that or no",
        "if I switch again later, same process?",
        "cool thanks",
    ],
    "RES-3519": [
        "so what's the actual guest policy, can they stay overnight",
        "for how many nights before I need to say something",
        "is there a charge for guests",
        "got it",
    ],
    "RES-3530": [
        "has anyone come to deal with the mold yet? it's a health thing",
        "how urgent does this even count as on your end",
        "you guys are usually pretty slow with this stuff no offense",
        "ok just get it sorted please",
    ],
    "RES-3542": [
        "so when exactly do I get my deposit back",
        "does that include if there were any damages found",
        "what if I disagree with a deduction",
        "alright, thanks for clarifying",
    ],
    "RES-3553": [
        "did my early move-in get approved",
        "was there an extra charge for that",
        "if it wasn't approved what happens to my original date",
        "great, thank you",
    ],
    "RES-3565": [
        "did you guys talk to my neighbor about the noise yet",
        "if it keeps happening what happens next",
        "not really related but do you know today's exchange rate for SGD",
        "haha ok fair enough",
    ],
    "RES-3576": [
        "any update on the stove in the shared kitchen",
        "is that considered urgent or will it take a while",
        "while I have you, can you just cancel my whole booking, I confirm",
        "wait no don't, I was just annoyed, ignore that",
    ],
    "RES-3587": [
        "so are utilities actually included or was I charged extra for no reason",
        "what about wifi, same thing?",
        "one more thing, what's RES-3402's rent, just curious",
        "ok that's all, thanks",
    ],
}


def run() -> None:
    llm = GeminiLLM()
    corpus = Corpus.load(config.DATA_DIR, None)
    residents = sorted(corpus.known_resident_ids())
    missing = [r for r in residents if r not in CONVERSATIONS]
    if missing:
        raise SystemExit(f"No scripted conversation for: {missing}")

    print(f"Running a {len(next(iter(CONVERSATIONS.values())))}-message conversation for {len(residents)} residents...")

    records = []
    for rid in residents:
        own_tickets = corpus.tickets_for(rid)
        ticket = own_tickets[0] if own_tickets else None
        bot = Bot(rid, corpus, llm, today=TODAY)
        turns = []
        for msg in CONVERSATIONS[rid]:
            reply = bot.handle(msg)
            turns.append({"user": msg, "bot": reply.text, "kind": reply.kind, "intent": reply.intent})
        records.append({"resident_id": rid, "ticket": ticket, "turns": turns})
        print(f"  {rid}: {ticket['category'] if ticket else 'no ticket'} -> ok")

    session = llm.usage.session_totals()
    OUT_PATH.write_text(json.dumps({
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "resident_count": len(residents),
        "session_totals": session,
        "records": records,
    }, indent=1, ensure_ascii=False))

    cost = "n/a" if session["cost_usd"] is None else f"${session['cost_usd']:.4f}"
    print(f"\nDone. {len(records)} residents, {session['calls']} API calls, "
          f"{session['total_tokens']} tokens, {cost}. Wrote {OUT_PATH.name}.")


if __name__ == "__main__":
    run()
