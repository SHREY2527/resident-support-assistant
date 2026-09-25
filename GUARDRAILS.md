# Guardrails

Architecture: a fixed workflow, not a ReAct agent. Per turn: **(1)** a cheap router model (`gemini-3.5-flash-lite`) classifies intent and extracts slots, then **(2)** the main model (`gemini-3.6-flash`) answers from the data, and **(3)** an optional judge (router model) checks the answer. Everything that matters for safety (confirmation, identity, data access, the IDK string) is enforced in **code**, not in prompts. No guardrail depends on specific data values; all data is loaded at runtime.

The resident's identity comes from the session (`--resident RES-xxxx`), never from chat text.

## 1. Scope
**Protects against:** general-knowledge questions, persona changes, and legal/financial advice.
**Implementation:** the router has separate intents (`out_of_scope`, `legal_financial_advice`, `injection`). Those turns get a templated decline plus a redirect, and the answering model is never called. The answerer prompt also forbids advice and only restates policy.
**Tests:** `test_scope_declined` (exchange rate, trivia, code, chef persona, "should I withhold rent / sue", "invest my deposit"); provided Q10, Q11.
**Limitations:** relies on an LLM classifier, so a novel phrasing could be misrouted. The answerer prompt is a second line of defence. The decline text is templated, so it is less natural than a generated one.

## 2. Groundedness
**Protects against:** invented prices, policies, dates, availability or ticket info.
**Implementation:**
- The answerer sees only listings, house rules and the resident's own tickets. It returns `coverage` (full/partial/none) plus verbatim evidence quotes.
- **Code verifies every quote occurs in the source data.** A fabricated quote triggers one retry, then falls back to the exact string `I do not have that information.`
- The IDK string is emitted only by code. A judge call then checks that the answer is supported by the quotes, and a veto also becomes IDK.
- The prompt says a missing rule or amenity is not proof (no "not listed, so no").
- Today's date is injected for availability and grace-period reasoning.
- Currencies are never converted.

**Tests:** `test_unanswerable_gets_exact_idk` (pets at Maple Court, refurbishment, guests, own rent, gym, parking), `test_answerable_is_grounded` (rent, availability, refund time, minimum stay, JPY/HKD listings, utilities, quiet hours), grace-period reasoning both ways, mixed answerable and unanswerable question, and the unit tests for fabricated quotes and a judge veto.
**Limitations:** quotes are checked to exist, not that they entail the claim, so the judge (an LLM) carries that part. Verbatim quotes are matched after stripping punctuation and case. Small paraphrase-style errors in inference could slip past the judge. Ticket text is unreliable data (e.g. a ticket quotes a price that differs from the listing), so the prompt says to ignore it for facts. The judge adds latency (one extra call).

## 3. Injection resistance and privacy
**Protects against:** "ignore instructions", system-prompt extraction, fake staff claims, and requests for other residents' data.
**Implementation (layered):**
1. **Least data.** Only the current resident's tickets are ever placed in a prompt. Other residents' data cannot leak because it is never in context (`test_other_residents_data_never_enters_prompts`).
2. User text is delimited and marked untrusted in both prompts.
3. The router flags injection, prompt extraction and other-resident requests, and the refusal is templated.
4. **Output guard:** any reply containing another resident's ID or ticket ID (computed from the data at runtime) is replaced with a refusal.
5. The system prompts contain no secrets.
6. Slots the router extracts (property, room) must literally appear in what the resident typed.

**Tests:** 6 injection prompts (including the provided Q11, Q12, Q15 and "another resident's rent"), 5 privacy prompts (Q9, Q13, someone else's ticket ID, "I'm RES-3497"), a multi-turn "DAN" roleplay followed by a privacy request, and an injection inside ticket text.
**Limitations:** a determined multi-turn or encoded attack could still fool the classifier, though the data-scoping layer would still hold. Asking for a nonexistent ticket returns IDK while asking for someone else's returns IDK or a refusal, which leaks a tiny amount about ticket existence. The output guard only recognises IDs, not free-text descriptions of another person.

## 4. Action confirmation
**Protects against:** state changes the resident did not clearly approve, pre-authorised confirmations, and personal-info edits.
**Implementation:**
- Actions are a small registry (`create_ticket`, `cancel_booking`). The LLM only fills slots. Required fields are checked in code (e.g. maintenance needs property and room, as the house rules ask).
- Once complete, the bot shows a summary and stores the draft as *awaiting confirmation* with a fingerprint of its fields.
- Only a **separate, later message** classified as a clear "yes" executes it. A "yes" in the same message as the request never counts.
- The executor is plain code, so the model cannot call it. Editing a field invalidates the fingerprint and forces a fresh summary. A bare "yes" with nothing pending does nothing.
- Pending drafts expire after 5 idle turns.
- Cancellations are recorded as a **request** because the data has no booking table. The bot says it cannot promise a refund amount.
- Personal-info changes (name, phone, email…) are always refused.
- Confirmations are written to `tickets_runtime.json`; sample data is never modified.

**Tests:** unit tests with a fake LLM (no write before a separate confirm, same-message "I confirm" ignored, edit forces re-confirmation, tampered draft not executed, expiry, deny discards, hallucinated room dropped) plus live tests for the maintenance flow (Q16), cancellation (Q17), pre-authorisation attack (Q14), bare "yes", personal-info changes, and urgent-priority detection.
**Limitations:** the "yes" itself is interpreted by the LLM router, so an odd reply ("sure, whatever") might be misread, though a wrong read only matters when the resident has a pending action. There is no real booking lookup, so a cancellation cannot be verified. Priority is chosen by the router from the house-rules definition of urgent and can be wrong. Session state is in memory only.

## Running the tests
`pytest tests/test_state_machine.py` (offline) and `pytest -m live` (needs `GEMINI_API_KEY`).
