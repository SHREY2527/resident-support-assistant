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
