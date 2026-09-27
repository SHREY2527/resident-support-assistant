# Task list: Resident Support Assistant

Checklist against the client's take-home brief. `[x]` = verified done, `[ ]` = not done or not verified.
Status as of 2026-09-27, on branch `fix/regression-findings`. The two behavioural fixes found in
regression testing have now been re-verified with real credits: 45/45 live guardrail tests, 5/5 on
the exact previously-failing scenarios, and 70/72 (up from 67/72) on a 2-run regression suite. Full
detail in `REGRESSION_REPORT.md`.

## 10. API usage / cost tracking (added after the key ran out mid-testing)
- [x] Real per-call token usage captured from the Gemini API's own `usage_metadata` (`app/usage.py`), not an estimate — including hidden "thinking" tokens, which Google bills as output tokens
- [x] Every LLM call site labelled (`router`, `answer`, `answer_retry`, `judge`, `judge_retry`) so cost is attributable to a stage, not just a total
- [x] Per-reply usage line (tokens + call count + $ cost) and a running conversation total, surfaced in both the CLI and Streamlit UI
- [x] Durable audit trail: one JSON line per turn in `usage.log` (gitignored), with the user message, bot reply, per-call breakdown, and running totals
- [x] Real Gemini pricing wired in (`MODEL_PRICING_PER_1M` in `app/config.py`, input/output priced separately per model), overridable via env vars
- [x] Verified end-to-end with a mocked LLM response before spending real credits, then against real API calls — cost math confirmed to the last digit ($0.0399 for the narrow retest, matching the log exactly)
- [x] Thread-safety bug found and fixed: the regression suite's 6-way parallel scenario runs shared one mutable per-turn bucket, which could log calls under the wrong turn (billing/totals unaffected, only the log's turn attribution). Fixed with thread-local turn buckets in `app/usage.py`; verified with a 200-turn/8-thread stress test, 0 malformed lines
- [x] Cost breakdown by stage established from real data: answer (generator) ~62% of spend, router ~34%, judge ~3% — router is not negligible since it runs on every turn and its system prompt (embedded house rules) is nearly as large as the generator's

## 1. Project setup
- [x] Python codebase (`app/` package)
- [x] Chosen framework/LLM: Gemini (`gemini-3.6-flash` + `gemini-3.5-flash-lite`), via `google-genai`
- [x] UI: CLI (`app/cli.py`) and Streamlit (`streamlit_app.py`)
- [x] Dependencies pinned in `requirements.txt`
- [x] Secrets via `.env`, not committed (`.gitignore` covers `.env`)
- [x] `house_env/` (the venv folder) added to `.gitignore`
- [ ] GitHub repo pushed and up to date — remote `origin` is configured; this branch not yet pushed (about to be)

## 2. Data layer
- [x] Load `listings.json`, `house_rules.md`, `support_tickets.json` at runtime (`data_loader.py`)
- [x] No code depends on specific data values (verified by reading `data_loader.py`, `router.py`, `answerer.py`)
- [x] Currency kept per-listing field (SGD/HKD/JPY), never converted
- [x] Ticket data scoped per resident (`tickets_for`, `foreign_identifiers`)
- [x] Runtime writes go to `tickets_runtime.json`, sample data never mutated
- [x] Stray `data/README 2.md` (duplicate of the assignment brief) removed

## 3. Core chatbot flow
- [x] Router step: intent classification + slot extraction (`router.py`)
- [x] Answering step: grounded answer generation with evidence quotes (`answerer.py`)
- [x] Judge step: second-pass verification of the answer against evidence
- [x] Action step: confirmation state machine (`actions.py`, `bot.py`)
- [x] Resident identity comes from session/CLI flag, never from chat text
- [x] Conversation history kept for follow-ups (last N turns)
- [x] Fix implemented and re-verified live: judge veto now triggers one retry that asks the model to back every stated fact with a quote, before falling back to IDK (`app/answerer.py`). Reduces the false-IDK rate substantially (5/5 on the exact scenario that used to fail) but a lower-frequency residual flake remains — see `REGRESSION_REPORT.md`
- [x] Fix implemented and re-verified live: a bare, unambiguous "yes"/"no" ("yes", "yep", "confirm", "no", "nope"...) is now resolved in code before the router is even called, so it can't be misclassified (`app/bot.py`) — held clean across all re-verification runs
- [x] `app/cli.py` now catches LLM/API exceptions per turn and prints a friendly message instead of crashing

## 4. Guardrail 1 — Scope
- [x] General-knowledge questions declined (weather, trivia, exchange rate)
- [x] Persona-change requests declined ("act as a chef", "write my code/essay")
- [x] Legal advice declined (own `legal_financial_advice` intent, separate from plain scope)
- [x] Financial/investment advice declined
- [x] Decline redirects back to resident-support capabilities
- [x] At least one test case — provided (`test_scope_declined`, live) + regression suite categories "Scope" and "Legal & financial advice" (6 scenarios, 6/6 and 5/6 passing across 2 clean runs)
- [x] Documented in `GUARDRAILS.md` with limitations noted

## 5. Guardrail 2 — Groundedness
- [x] Answers restricted to listings + house rules + the resident's own tickets
- [x] Exact string `"I do not have that information."` used, emitted only by code
- [x] Code verifies every evidence quote is verbatim in the source data before trusting an answer
- [x] Retry-once-then-IDK on a fabricated quote
- [x] Missing rule/amenity is never treated as "no" (prompt rule + unit test)
- [x] Date-aware reasoning (grace period, availability vs. today) verified in regression suite
- [x] At least one test case — provided (`test_unanswerable_gets_exact_idk`, `test_answerable_is_grounded`) + unit tests for fabricated quotes/judge veto + regression suite categories "Grounded answers", "Unanswerable", "Data reasoning" (18 scenarios)
- [x] Documented in `GUARDRAILS.md` with limitations noted
- [x] Fix for judge over-vetoing correct comparison/availability answers implemented and re-verified live (§3) — improved, not fully eliminated; documented as a known residual flake

## 6. Guardrail 3 — Injection resistance & privacy
- [x] "Ignore previous instructions" / persona override attempts refused
- [x] System-prompt / hidden-instruction extraction attempts refused
- [x] Fake staff/admin claims refused
- [x] Requests for another resident's rent, tickets, or personal data refused
- [x] Least-data design: only the current resident's tickets ever enter a prompt
- [x] Output guard blocks any reply containing another resident's ID, as a last line of defence
- [x] Slots (property, room) must literally appear in what the resident typed, blocking injected facts
- [x] At least 2–3 self-written injection tests — provided Q11/Q12/Q13/Q15 + 6 more live tests + regression suite categories "Injection resistance" and "Privacy" (18 scenarios, 6/6 and 6/6)
- [x] Multi-turn attack tested (roleplay then privacy request; escalating admin claim)
- [x] Documented in `GUARDRAILS.md` with limitations noted

## 7. Guardrail 4 — Action confirmation
- [x] Ticket/cancellation drafts collected turn by turn, missing fields asked for
- [x] Explicit summary shown before anything is submitted ("Nothing has been submitted yet")
- [x] Only a separate, later "yes" executes the action — same-message "I confirm" ignored (unit test + regression)
- [x] Editing a field after the summary invalidates confirmation, forces a fresh summary
- [x] Bare "yes"/"no" with nothing pending handled without side effects — fixed and re-verified
- [x] Pending drafts expire after idle turns
- [x] Personal-info changes always refused, never enter the draft flow
- [x] Cancellations recorded as a request, refund amount never promised (no booking table exists)
- [x] At least one test case — provided Q14/Q16/Q17 + unit tests (tampered draft, hallucinated slot, expiry) + regression suite categories "Maintenance ticket flow", "Cancellation flow", "Confirmation bypass & edge cases", "Personal-info changes" (24 scenarios)
- [x] Documented in `GUARDRAILS.md` with limitations noted

## 8. Testing
- [x] Offline unit test suite (`tests/test_state_machine.py`) — 14/14 passing, no API needed, still 14/14 after every change this session
- [x] Live end-to-end guardrail suite (`tests/test_guardrails_live.py`) — 45/45 passing against real Gemini, re-verified after the fixes
- [x] Independent regression suite with realistic, multi-turn, casually-worded scenarios (`tests/regression_suite.py`) — 70/72 scenario runs passing across 2 runs after the fixes (up from 67/72 before); findings in `REGRESSION_REPORT.md`
- [x] Code fixes implemented for the 2 behavioural bugs found in regression testing (`app/answerer.py`, `app/bot.py`) and confirmed against real API calls
- [x] `pytest.ini` added, registering the `live` marker (cosmetic warning gone)
- [ ] Full literal pass of all 17 `test_questions.md` items as one explicit checklist (covered piecemeal across suites, not as a single named run)
- [ ] The 2 remaining known issues (residual judge-veto flake on comparison questions; one test-strictness false positive on "paste your rules") are documented, not further chased — diminishing returns vs. further API spend

## 9. Documentation & submission
- [x] `GUARDRAILS.md` — what/how/tests/limitations for all four guardrails, limitations updated with the real findings from regression testing (judge-veto residual flake, single-resident test coverage) rather than only anticipated ones
- [x] `README.md` — rewritten with an overview, quickstart, test commands, layout and this checklist linked
- [x] `USAGE.md` removed — its content was folded into `README.md`, keeping one setup doc instead of two
- [x] `REGRESSION_REPORT.md` linked from `README.md`
- [x] Repo cleanup: removed stray `data/README 2.md`, `.DS_Store`, and stale `__pycache__`/`.pytest_cache` directories
- [x] Work done on branch `fix/regression-findings`, not `main`
- [ ] Push this branch to `origin` and merge into `main`
- [ ] Repo link + `GUARDRAILS.md` handed to the client

---

**Remaining work is small.** The fixes are verified, tested, and cost-tracked. What's left is: push
the branch, merge to `main`, optionally chase the two residual/low-severity findings from
`REGRESSION_REPORT.md`, and hand the repo link + `GUARDRAILS.md` to the client.
