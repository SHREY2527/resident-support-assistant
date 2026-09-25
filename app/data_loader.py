"""Loads the sample data at runtime. Nothing in the code depends on data values."""
import json
import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Corpus:
    listings_text: str
    rules_text: str
    tickets: list[dict]
    runtime_path: Path | None = None
    _runtime: list[dict] = field(default_factory=list)

    @classmethod
    def load(cls, data_dir: Path, runtime_path: Path | None = None) -> "Corpus":
        tickets = json.loads((data_dir / "support_tickets.json").read_text())
        c = cls(
            listings_text=(data_dir / "listings.json").read_text(),
            rules_text=(data_dir / "house_rules.md").read_text(),
            tickets=tickets,
            runtime_path=runtime_path,
        )
        if runtime_path and runtime_path.exists():
            c._runtime = json.loads(runtime_path.read_text())
        return c

    # ---- tickets -------------------------------------------------------
    def all_tickets(self) -> list[dict]:
        return self.tickets + self._runtime

    def tickets_for(self, resident_id: str) -> list[dict]:
        return [t for t in self.all_tickets() if t.get("resident_id") == resident_id]

    def next_ticket_id(self) -> str:
        nums = [int(m.group(1)) for t in self.all_tickets()
                if (m := re.search(r"(\d+)$", t.get("ticket_id", "")))]
        return f"TKT-{max(nums, default=2000) + 1}"

    def add_ticket(self, ticket: dict) -> None:
        self._runtime.append(ticket)
        if self.runtime_path:
            self.runtime_path.write_text(json.dumps(self._runtime, indent=2))

    def runtime_tickets(self) -> list[dict]:
        return list(self._runtime)

    # ---- privacy -------------------------------------------------------
    def foreign_identifiers(self, resident_id: str) -> set[str]:
        """Resident/ticket IDs that belong to anyone but this resident."""
        own = {t["ticket_id"] for t in self.tickets_for(resident_id)}
        ids: set[str] = set()
        for t in self.all_tickets():
            if t.get("resident_id") != resident_id:
                ids.add(t["ticket_id"])
            if t.get("resident_id") and t["resident_id"] != resident_id:
                ids.add(t["resident_id"])
        return ids - own

    def known_resident_ids(self) -> set[str]:
        return {t["resident_id"] for t in self.all_tickets() if t.get("resident_id")}

    def evidence_text(self, resident_id: str) -> str:
        """Everything a quote may legitimately come from for this resident."""
        return "\n".join([
            self.listings_text, self.rules_text,
            json.dumps(self.tickets_for(resident_id)),
        ])
