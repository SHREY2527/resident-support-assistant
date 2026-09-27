import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

DATA_DIR = ROOT / "data"
RUNTIME_TICKETS = ROOT / "tickets_runtime.json"

MAIN_MODEL = os.getenv("MAIN_MODEL", "gemini-3.6-flash")
ROUTER_MODEL = os.getenv("ROUTER_MODEL", "gemini-3.5-flash-lite")
USE_JUDGE = os.getenv("USE_JUDGE", "1") == "1"

HISTORY_TURNS = 6          # messages kept for follow-up resolution
PENDING_MAX_IDLE = 5       # turns a pending action survives without being touched

# Exact string mandated by the assignment. Only code ever emits it.
IDK = "I do not have that information."

# Every reply is logged with its real token usage (from the API's own usage_metadata) and the
# running conversation total, so API spend is visible turn by turn instead of a surprise later.
USAGE_LOG = ROOT / "usage.log"

# Gemini paid-tier pricing, $ per 1,000,000 tokens, input vs output priced separately since output
# costs several times more. Current as of 2026-09-27; both models step up on 2027-01-01 (3.6 Flash:
# $1.50/$7.50, 3.5 Flash-Lite unchanged in what we were given) — update here if that date has passed.
# Unknown models fall back to no price (usage.py then reports cost as "n/a" instead of guessing).
MODEL_PRICING_PER_1M = {
    "gemini-3.6-flash": {"input": 0.75, "output": 3.75},
    "gemini-3.5-flash-lite": {"input": 0.30, "output": 2.50},
}
# Override or add a model's price via env, e.g. MAIN_MODEL_INPUT_PRICE_PER_1M=1.50
for _role, _model in (("MAIN_MODEL", MAIN_MODEL), ("ROUTER_MODEL", ROUTER_MODEL)):
    _in, _out = os.getenv(f"{_role}_INPUT_PRICE_PER_1M"), os.getenv(f"{_role}_OUTPUT_PRICE_PER_1M")
    if _in or _out:
        p = MODEL_PRICING_PER_1M.setdefault(_model, {"input": 0.0, "output": 0.0})
        if _in:
            p["input"] = float(_in)
        if _out:
            p["output"] = float(_out)
