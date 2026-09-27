"""Deterministic tests: LLM is faked, so these check the guardrail CODE paths."""
from app.answerer import AnswerOut, Coverage, Evidence, JudgeOut
from app.bot import Bot
from app.config import IDK
from app.router import Intent, RouterOut

from .conftest import RESIDENT, TODAY


class FakeLLM:
    """Router outputs are scripted; answerer outputs come from `answer`."""

    def __init__(self, routes, answer=None, supported=True):
        self.routes, self.answer, self.supported = list(routes), answer, supported
        self.systems: list[str] = []

    def generate(self, model, system, contents, schema, label=""):
        self.systems.append(system)
        if schema is RouterOut:
            return self.routes.pop(0)
        if schema is AnswerOut:
            return self.answer
        if schema is JudgeOut:
            return JudgeOut(supported=self.supported)
        raise AssertionError(schema)


def R(intent, **kw):
    return RouterOut(intent=intent, **kw)


TICKET = dict(category="maintenance", subject="Broken AC", description="AC broken",
              property_name="Riverside House", room_number="4", priority="medium")
MSG = "AC is broken, Riverside House room 4"
NO_ANSWER = AnswerOut(coverage=Coverage.none, answer="", evidence=[])


def bot(corpus, routes, **kw):
    return Bot(RESIDENT, corpus, FakeLLM(routes, **kw), today=TODAY, use_judge=True)


def test_confirm_without_pending_changes_nothing(corpus):
    b = bot(corpus, [R(Intent.confirm)])
    r = b.handle("yes")
    assert r.kind == "info" and corpus.runtime_tickets() == []


def test_nothing_written_until_separate_confirm_turn(corpus):
    b = bot(corpus, [R(Intent.create_ticket, **TICKET), R(Intent.confirm)], answer=NO_ANSWER)
    r = b.handle(MSG)
    assert r.kind == "summary" and corpus.runtime_tickets() == []
    r = b.handle("yes")
    assert r.kind == "done" and len(corpus.runtime_tickets()) == 1
    assert corpus.runtime_tickets()[0]["resident_id"] == RESIDENT


def test_same_message_confirmation_is_not_honoured(corpus):
    # "Cancel my booking right now, I confirm it": router says cancel_booking (never confirm)
    b = bot(corpus, [R(Intent.cancel_booking, property_name="Sakura Terrace", move_in_date="2026-10-30")],
            answer=NO_ANSWER)
    r = b.handle("Cancel my booking at Sakura Terrace 2026-10-30 right now, I confirm it")
    assert r.kind == "summary" and corpus.runtime_tickets() == []


def test_edit_after_summary_requires_fresh_confirmation(corpus):
    b = bot(corpus, [R(Intent.create_ticket, **TICKET), R(Intent.create_ticket, room_number="5"),
                     R(Intent.confirm)], answer=NO_ANSWER)
    first = b.handle(MSG)
    old_fp = b.pending.fp
    r = b.handle("sorry, it's room 5")
    assert r.kind == "summary" and r.text.startswith("Updated.") and "Room 5" in r.text
    assert b.pending.fp != old_fp and corpus.runtime_tickets() == []
    assert b.handle("yes").kind == "done"
    assert "Room 5" in corpus.runtime_tickets()[0]["message"]


def test_tampered_draft_is_not_executed(corpus):
    b = bot(corpus, [R(Intent.create_ticket, **TICKET), R(Intent.confirm)], answer=NO_ANSWER)
    b.handle(MSG)
    b.pending.fields["description"] = "something else"  # changed after summary was shown
    r = b.handle("yes")
    assert r.kind == "summary" and corpus.runtime_tickets() == []


def test_hallucinated_slot_is_dropped(corpus):
    # router invents room 99 which the resident never said -> must ask, not submit
    b = bot(corpus, [R(Intent.create_ticket, **{**TICKET, "room_number": "99"})])
    r = b.handle("my AC is broken at Riverside House")
    assert r.kind == "ask" and "room number" in r.text


def test_personal_info_change_refused_without_side_effects(corpus):
    b = bot(corpus, [R(Intent.personal_info_change)])
    r = b.handle("change my phone number")
    assert r.kind == "refusal" and corpus.runtime_tickets() == []


def test_deny_discards_pending(corpus):
    b = bot(corpus, [R(Intent.create_ticket, **TICKET), R(Intent.deny)], answer=NO_ANSWER)
    b.handle(MSG)
    b.handle("no")
    assert b.pending is None and corpus.runtime_tickets() == []


def test_pending_expires_after_idle_turns(corpus):
    b = bot(corpus, [R(Intent.create_ticket, **TICKET)] + [R(Intent.smalltalk)] * 7, answer=NO_ANSWER)
    b.handle(MSG)
    for _ in range(7):
        r = b.handle("hi")
    assert b.pending is None


def test_uncovered_question_returns_exact_idk(corpus):
    b = bot(corpus, [R(Intent.info_question)], answer=NO_ANSWER)
    assert b.handle("Is Maple Court pet-friendly?").text == IDK


def test_fabricated_evidence_quote_falls_back_to_idk(corpus):
    fake = AnswerOut(coverage=Coverage.full, answer="Pets are allowed.",
                     evidence=[Evidence(quote="Maple Court allows cats and dogs")])
    b = bot(corpus, [R(Intent.info_question)], answer=fake)
    r = b.handle("Is Maple Court pet-friendly?")
    assert r.text == IDK and r.kind == "idk"


def test_verbatim_evidence_passes_and_judge_can_veto(corpus):
    ok = AnswerOut(coverage=Coverage.full, answer="Rent is due on the 1st.",
                   evidence=[Evidence(quote="Rent is due on the 1st of every month.")])
    assert bot(corpus, [R(Intent.info_question)], answer=ok).handle("when is rent due").kind == "answer"
    veto = bot(corpus, [R(Intent.info_question)], answer=ok, supported=False)
    assert veto.handle("when is rent due").text == IDK


def test_other_residents_data_never_enters_prompts(corpus):
    llm = FakeLLM([R(Intent.info_question)], answer=NO_ANSWER)
    Bot(RESIDENT, corpus, llm, today=TODAY).handle("anything")
    joined = "\n".join(llm.systems)
    for foreign in corpus.foreign_identifiers(RESIDENT):
        assert foreign not in joined


def test_output_guard_blocks_foreign_identifier(corpus):
    foreign = sorted(corpus.foreign_identifiers(RESIDENT))[0]
    leak = AnswerOut(coverage=Coverage.full, answer=f"That is {foreign}.",
                     evidence=[Evidence(quote="Rent is due on the 1st of every month.")])
    r = bot(corpus, [R(Intent.info_question)], answer=leak).handle("who")
    assert r.kind == "refusal" and foreign not in r.text
