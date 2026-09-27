# Resident Support Assistant

A Python chatbot for a co-living company's residents: room listings and prices, house rules and
policies, a resident's own support tickets, and raising maintenance requests or booking
cancellations. Built as a fixed pipeline (router → grounded answerer → judge → action state
machine), not a free-form agent, so the safety guardrails live in code, not just in prompts.

See [GUARDRAILS.md](GUARDRAILS.md) for what each guardrail protects against, how it's implemented,
and its test cases. See [REGRESSION_REPORT.md](REGRESSION_REPORT.md) for a realistic multi-turn
regression run against the live model, and [TASKS.md](TASKS.md) for a checklist of what's done
against the assignment brief.

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

## Layout

- `app/router.py` — intent classification and slot extraction (cheap model)
- `app/answerer.py` — grounded answer generation with evidence-quote verification and a judge pass
- `app/actions.py` + `app/bot.py` — the confirmation state machine for tickets and cancellations
- `app/data_loader.py` — loads `data/` at runtime and scopes ticket data per resident
- `app/llm.py` — the Gemini client (structured JSON output via a Pydantic schema)
- `app/usage.py` — real per-call token/cost tracking (thread-safe; see below)
- `app/cli.py` / `streamlit_app.py` — the two entry points
- `data/` — sample listings, house rules and tickets (synthetic)
- `tests/test_state_machine.py` — offline unit tests (no API calls)
- `tests/test_guardrails_live.py` — end-to-end guardrail tests against the real model
- `tests/regression_suite.py` — realistic multi-turn scenarios; see `REGRESSION_REPORT.md`
- `tests/resident_showcase.py` — generates `resident_showcase.json`; see below

New tickets are written to `tickets_runtime.json` (gitignored, created on first write); the sample
data in `data/` is never modified.

## Resident showcase

`tests/resident_showcase.py` logs in as every one of the 18 residents in the sample data and runs a
short, real, naturally-worded conversation written around *their own* actual ticket — not a
repeated template, so the variety is organic (some naturally touch on privacy, one drifts
out of scope, one attempts a pre-authorised confirmation). The output (`resident_showcase.json`) is
committed so it can be viewed without needing an API key, and is rendered in the Streamlit app's
**"Resident showcase"** tab, filterable by resident and category.

It also honestly surfaces a real, found limitation rather than hiding it: two residents' messages
were misclassified by the router (a status-check on an existing ticket read as a request to open a
new one). That's flagged directly in the UI and in `GUARDRAILS.md` — not a safety issue, since
nothing is ever submitted without a separate confirmation either way, but a genuine known gap.

## API usage / cost tracking

Every reply's real token usage (from the Gemini API's own `usage_metadata`, not an estimate) is
logged to `usage.log` (gitignored) — one JSON line per turn, broken down per call (router, answer,
judge, and any retries), per reply, and as a running conversation total. This is written for
development/cost-auditing use; it isn't surfaced in the Streamlit UI, which only shows the resident
session and chat.

A single question is typically 2-4 API calls (router → answer → judge, sometimes with a retry), so
tokens and call counts add up faster than the message count suggests — that's what the logging is
for. Cost in $ is computed from the real Gemini pricing in `app/config.py`
(`MODEL_PRICING_PER_1M`), overridable per `.env.example`.
