"""Tracks real token usage per LLM call, per reply and for the whole conversation.

Token counts come from the Gemini API's own usage_metadata, not an estimate. Cost is only
computed if a price is configured for the model (see config.MODEL_PRICING_PER_1M); with no
price set it is shown as "n/a" rather than guessed.

One UsageTracker can be shared by several bots running concurrently (e.g. the regression suite
runs scenarios in a thread pool). Each worker thread runs one bot's turns start-to-finish without
interleaving with another thread's turn, so "this turn's calls" is kept in thread-local storage:
threads never see or clear each other's in-progress turn. `all_calls` (the running total) is a
single shared list appended to under a lock, so the grand total is correct regardless of threading.
"""
import json
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import config


@dataclass
class Call:
    label: str          # e.g. "router", "answer", "answer_retry", "judge", "judge_retry"
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


def _cost(model: str, prompt_tokens: int, completion_tokens: int) -> float | None:
    price = config.MODEL_PRICING_PER_1M.get(model)
    if price is None:
        return None
    return prompt_tokens * price["input"] / 1_000_000 + completion_tokens * price["output"] / 1_000_000


class UsageTracker:
    def __init__(self, log_path: Path | None = None):
        self.log_path = log_path
        self.all_calls: list[Call] = []      # whole session, shared across threads
        self._lock = threading.Lock()
        self._local = threading.local()      # per-thread "calls since reset_turn()"

    def _turn_calls(self) -> list[Call]:
        if not hasattr(self._local, "calls"):
            self._local.calls = []
        return self._local.calls

    def record(self, label: str, model: str, prompt_tokens: int, completion_tokens: int, total_tokens: int) -> None:
        c = Call(label, model, prompt_tokens, completion_tokens, total_tokens)
        with self._lock:
            self.all_calls.append(c)
        self._turn_calls().append(c)

    def reset_turn(self) -> None:
        self._local.calls = []

    @staticmethod
    def _totals(calls: list[Call]) -> dict:
        costs = [_cost(c.model, c.prompt_tokens, c.completion_tokens) for c in calls]
        priced = any(c is not None for c in costs)
        cost = sum(c for c in costs if c is not None)
        return {
            "calls": len(calls),
            "prompt_tokens": sum(c.prompt_tokens for c in calls),
            "completion_tokens": sum(c.completion_tokens for c in calls),
            "total_tokens": sum(c.total_tokens for c in calls),
            "cost_usd": round(cost, 6) if priced else None,
        }

    def turn_totals(self) -> dict:
        return self._totals(self._turn_calls())

    def session_totals(self) -> dict:
        with self._lock:
            calls = list(self.all_calls)
        return self._totals(calls)

    def log_turn(self, resident_id: str, user_msg: str, bot_reply: str) -> str:
        """Writes one JSON line for this turn (if log_path is set) and returns a short summary string."""
        turn_calls = self._turn_calls()
        turn, session = self._totals(turn_calls), self.session_totals()
        if self.log_path:
            line = {
                "ts": round(time.time(), 3), "resident": resident_id,
                "user": user_msg, "bot": bot_reply,
                "calls_this_turn": [{"label": c.label, "model": c.model,
                                      "prompt_tokens": c.prompt_tokens, "completion_tokens": c.completion_tokens,
                                      "total_tokens": c.total_tokens} for c in turn_calls],
                "turn": turn, "conversation_total": session,
            }
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with self._lock:  # keep concurrent writers from interleaving mid-line
                with open(self.log_path, "a") as f:
                    f.write(json.dumps(line, ensure_ascii=False) + "\n")

        def fmt(t: dict) -> str:
            cost = "n/a" if t["cost_usd"] is None else f"${t['cost_usd']:.6f}"
            return f"{t['total_tokens']} tokens, {t['calls']} call(s), {cost}"

        return f"this reply: {fmt(turn)} | conversation total: {fmt(session)}"
