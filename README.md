# Resident Support Assistant

A support chatbot for a co-living company's residents — bookings, maintenance, billing, and house
rules — built around one question: **how do you stop an LLM from making things up or doing things
it shouldn't?**

It's a fixed pipeline (router → grounded answerer → judge → action state machine), not a free-form
agent. Every safety-critical decision — confirmation before an action, resident-data isolation,
the "I don't know" fallback — is enforced in **code**, never left to a prompt to get right on its
own.

## Contents

- [At a glance](#at-a-glance)
- [The four guardrails](#the-four-guardrails)
- [Quickstart](#quickstart)
- [Testing](#testing)
- [Resident showcase](#resident-showcase)
- [API usage / cost tracking](#api-usage--cost-tracking)
- [Project layout](#project-layout)

## At a glance

| | |
|---|---|
| **Offline unit tests** | 14/14 passing |
| **Live guardrail tests** (real Gemini calls) | 45/45 passing |
| **Regression suite** — realistic, multi-turn, casually-worded scenarios | 70/72 across 2 runs |
| **Resident showcase** | all 18 sample residents, each in their own real conversation |
| **Known limitations** | documented, not hidden — see [`GUARDRAILS.md`](GUARDRAILS.md) and the showcase below |

## The four guardrails

The router (a cheap model) classifies each message and extracts slots. From there:
- **Scope, injection, and privacy violations** get a fixed, code-written refusal — the answering
  model is never even called.
- **Info questions** go to the answerer, which must back every claim with a verbatim quote from
  the data; code checks the quote actually exists, and a second model judges whether the answer is
  actually supported before it's allowed through.
- **Actions** (raising a ticket, cancelling a booking) are collected turn by turn and always shown
  as a summary before anything happens — only a separate, later "yes" executes it, and the
  executor is plain code the model can never call directly.
- **Every reply**, regardless of path, passes through an output guard that blocks any accidental
  mention of another resident's ID.

| Guardrail | Protects against | Enforced by |
|---|---|---|
| 1. Scope | Off-topic requests, persona changes, legal/financial advice | Router classification → fixed refusal, answering model never called |
| 2. Groundedness | Invented prices, policies, dates, availability | Verbatim quote requirement, checked in code, plus a judge pass |
| 3. Injection & privacy | Prompt injection, "ignore your instructions," another resident's data | Least-data design (only the caller's own tickets ever enter a prompt) + an output guard |
| 4. Action confirmation | State changes the resident didn't clearly approve | A summary is always shown first; only code executes, only after a separate confirmation |

Full detail — implementation, test cases, and honestly-listed limitations for each — is in
[`GUARDRAILS.md`](GUARDRAILS.md).

## Quickstart

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env               # then edit .env and set your own GEMINI_API_KEY

python -m app.cli --resident RES-3427     # CLI; resident identity is the session, not chat text
streamlit run streamlit_app.py            # web UI
```

`.env.example` lists every supported setting (model choice, judge on/off, pricing overrides) with
its default — everything past `GEMINI_API_KEY` is optional.

## Testing

```bash
pytest tests/test_state_machine.py        # offline unit tests, no API needed
pytest -m live                            # end-to-end guardrail tests (needs GEMINI_API_KEY)
python -m tests.regression_suite 2        # realistic multi-turn scenarios, run N times (needs GEMINI_API_KEY)
python -m tests.resident_showcase          # a real conversation for every resident in the sample data (needs GEMINI_API_KEY)
```

See [`REGRESSION_REPORT.md`](REGRESSION_REPORT.md) for what the regression suite found, including
two real bugs it caught and how they were fixed and re-verified.

## Resident showcase

`tests/resident_showcase.py` logs in as every one of the 18 residents in the sample data and runs a
short, real, naturally-worded conversation written around *their own* actual ticket — not a
repeated template, so the variety is organic (some naturally touch on privacy, one drifts
out of scope, one attempts a pre-authorised confirmation). The output (`resident_showcase.json`) is
committed so it can be viewed without needing an API key, and is rendered in the Streamlit app's
**"Resident showcase"** tab, filterable by resident and category.

It also surfaces a real, found limitation rather than hiding it: two residents' messages were
misclassified by the router (a status-check on an existing ticket read as a request to open a new
one). That's flagged directly in the UI and in `GUARDRAILS.md` — not a safety issue, since nothing
is ever submitted without a separate confirmation either way, but a genuine, honestly-documented gap.

## API usage / cost tracking

Every reply's real token usage (from the Gemini API's own usage metadata, not an estimate) is
tracked per call, per reply, and as a running conversation total, so cost is always visible and
never a surprise. A single question is typically 2-4 API calls (router → answer → judge, sometimes
with a retry), so cost adds up a bit faster than the message count alone suggests.

Based on running this against many real test cases (offline tests, live guardrail tests, and 18
full resident conversations), a single request typically costs around **$0.003-$0.006** — call it
half a cent — depending on whether it's answered by the main model or refused early by the router.
A longer back-and-forth of 5 or more turns has stayed comfortably **under $0.03** in practice.

## Project layout

```
app/
  router.py       intent classification and slot extraction (cheap model)
  answerer.py      grounded answer generation with evidence-quote verification and a judge pass
  actions.py       the confirmation state machine's rules (required fields, executor)
  bot.py           ties router → answerer/actions → output guard together
  data_loader.py   loads data/ at runtime and scopes ticket data per resident
  llm.py           the Gemini client (structured JSON output via a Pydantic schema)
  usage.py         real per-call token/cost tracking (thread-safe)
  cli.py           CLI entry point
streamlit_app.py   web UI entry point (Chat + Resident showcase tabs)
data/              sample listings, house rules and tickets (synthetic)
tests/
  test_state_machine.py    offline unit tests (no API calls)
  test_guardrails_live.py  end-to-end guardrail tests against the real model
  regression_suite.py      realistic multi-turn scenarios — see REGRESSION_REPORT.md
  resident_showcase.py     generates resident_showcase.json — see above
```

New tickets are written to a local `tickets_runtime.json` file, created automatically the first
time one is raised; the sample data in `data/` is never modified.
