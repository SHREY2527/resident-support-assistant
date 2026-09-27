# Resident Support Assistant

A Python chatbot for a co-living company's residents: room listings and prices, house rules and
policies, a resident's own support tickets, and raising maintenance requests or booking
cancellations. Built as a fixed pipeline (router → grounded answerer → judge → action state
machine), not a free-form agent, so the safety guardrails live in code, not just in prompts.

See [GUARDRAILS.md](GUARDRAILS.md) for what each guardrail protects against, how it's implemented,
and its test cases. See [REGRESSION_REPORT.md](REGRESSION_REPORT.md) for a realistic multi-turn
regression run against the live model.

## Quickstart

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
echo "GEMINI_API_KEY=..." > .env          # optional: MAIN_MODEL, ROUTER_MODEL, USE_JUDGE=0

python -m app.cli --resident RES-3427     # CLI; resident identity is the session, not chat text
streamlit run streamlit_app.py            # web UI
```

## Testing

```bash
pytest tests/test_state_machine.py        # offline unit tests, no API needed
pytest -m live                            # end-to-end guardrail tests (needs GEMINI_API_KEY)
python -m tests.regression_suite 2        # realistic multi-turn scenarios, run N times (needs GEMINI_API_KEY)
```

## Layout

- `app/router.py` — intent classification and slot extraction (cheap model)
- `app/answerer.py` — grounded answer generation with evidence-quote verification and a judge pass
- `app/actions.py` + `app/bot.py` — the confirmation state machine for tickets and cancellations
- `app/data_loader.py` — loads `data/` at runtime and scopes ticket data per resident
- `app/llm.py` — the Gemini client (structured JSON output via a Pydantic schema)
- `app/cli.py` / `streamlit_app.py` — the two entry points
- `data/` — sample listings, house rules and tickets (synthetic)
- `tests/test_state_machine.py` — offline unit tests (no API calls)
- `tests/test_guardrails_live.py` — end-to-end guardrail tests against the real model
- `tests/regression_suite.py` — realistic multi-turn scenarios; see `REGRESSION_REPORT.md`

New tickets are written to `tickets_runtime.json` (gitignored, created on first write); the sample
data in `data/` is never modified.

## API usage / cost tracking

Every reply is logged with its **real** token usage from the Gemini API (not an estimate), broken
down per call (router, answer, judge, and any retries), per reply, and as a running total for the
whole conversation:

- **CLI**: prints a `[usage] this reply: ... | conversation total: ...` line after every reply.
- **Streamlit**: shows the same line under each message, plus a running total in the sidebar.
- **`usage.log`** (gitignored, created on first use): one JSON line per turn with the exact token
  counts per call, so spend is auditable after the fact, not just visible live. See `app/usage.py`.

A single `bot.handle()` call for a question is typically 2-4 API calls (router → answer → judge,
sometimes with a retry), so tokens and call counts add up faster than the message count suggests —
this is what the logging is for. Cost in $ only appears if you set a price: `MAIN_MODEL_PRICE_PER_1K`
and/or `ROUTER_MODEL_PRICE_PER_1K` in `.env` (per 1,000 tokens); without it, only token counts show,
since guessing at pricing for a model isn't done here.

## Status

See [TASKS.md](TASKS.md) for a live checklist of what's done against the assignment brief, and what
is still open or blocked.
