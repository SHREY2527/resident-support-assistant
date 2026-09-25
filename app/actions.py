"""Action registry: required fields per action, summaries, and the (only) executor.
The LLM never calls the executor; it only helps fill draft slots."""
import hashlib
import json
from dataclasses import dataclass, field
from datetime import date

from .data_loader import Corpus


@dataclass
class Draft:
    type: str                       # "create_ticket" | "cancel_booking"
    fields: dict = field(default_factory=dict)
    awaiting: bool = False          # summary shown, waiting for explicit confirmation
    fp: str = ""                    # fingerprint of fields at the moment the summary was shown
    idle: int = 0

    def fingerprint(self) -> str:
        return hashlib.sha256(json.dumps([self.type, self.fields], sort_keys=True).encode()).hexdigest()

    def missing(self) -> list[str]:
        f = self.fields
        if self.type == "cancel_booking":
            need = ["property_name", "move_in_date"]
        else:
            need = ["description"]
            if (f.get("category") or "").lower() == "maintenance":
                need += ["property_name", "room_number"]  # house rules ask for both on maintenance requests
        return [k for k in need if not f.get(k)]


QUESTIONS = {
    "description": "what the issue or request is",
    "property_name": "the property name",
    "room_number": "your room number",
    "move_in_date": "your move-in date",
}

SLOTS = {"category", "subject", "description", "priority", "property_name", "room_number",
         "move_in_date", "booking_reference"}


def parse_date(s: str | None) -> date | None:
    try:
        return date.fromisoformat(s) if s else None
    except ValueError:
        return None


def ask_missing(draft: Draft) -> str:
    parts = [QUESTIONS[k] for k in draft.missing()]
    label = "cancel your booking" if draft.type == "cancel_booking" else "raise this request"
    return f"I can help you {label}. To continue I need {', '.join(parts)}."


def execute(draft: Draft, corpus: Corpus, resident_id: str) -> dict:
    f = draft.fields
    if draft.type == "cancel_booking":
        ticket = {
            "category": "booking",
            "subject": "Booking cancellation request",
            "message": (f"Resident requests cancellation of booking at {f['property_name']}, "
                        f"move-in {f['move_in_date']}."
                        + (f" Reference: {f['booking_reference']}." if f.get("booking_reference") else "")),
            "priority": "high",
        }
    else:
        loc = ", ".join(x for x in [f.get("property_name"), f"Room {f['room_number']}" if f.get("room_number") else None] if x)
        ticket = {
            "category": (f.get("category") or "general").lower(),
            "subject": f.get("subject") or "Resident request",
            "message": f["description"] + (f" ({loc})" if loc else ""),
            "priority": f.get("priority") or "medium",
        }
    ticket.update(ticket_id=corpus.next_ticket_id(), resident_id=resident_id, status="open")
    corpus.add_ticket(ticket)
    return ticket
