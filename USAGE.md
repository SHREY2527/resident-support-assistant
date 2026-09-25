# Resident Support Assistant: usage

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
echo "GEMINI_API_KEY=..." > .env          # optional: MAIN_MODEL, ROUTER_MODEL, USE_JUDGE=0
python -m app.cli --resident RES-3427     # resident identity is the session, not chat text
pytest tests/test_state_machine.py        # offline unit tests
pytest -m live                            # end-to-end guardrail tests (real Gemini calls)
```

Layout: `app/router.py` (intent + slots), `app/answerer.py` (grounded answer + verification),
`app/actions.py` + `app/bot.py` (confirmation state machine), `app/data_loader.py` (data + privacy scoping).
New tickets are written to `tickets_runtime.json`; `data/` is never modified. See `GUARDRAILS.md`.
