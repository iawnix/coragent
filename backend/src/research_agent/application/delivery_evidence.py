"""Record delivery evidence without putting research projection on its send path."""
from __future__ import annotations

import json
from pathlib import Path

from research_agent.foundation.transactions import TransactionCoordinator
from research_agent.application.job_state import persist_event, project_events


def record_delivery_evidence(root: Path, receipt: dict, *, title: str = "Email delivery",
                             receipt_ref: str | None = None, identity=None) -> str | None:
    """Persist one delivery fact and return any pending research projection error."""
    root = Path(root)
    if not (root / "research/journal.json").is_file():
        return None
    with TransactionCoordinator(root).locked():
        event_id = persist_event(
            root, kind="delivery", title=title, content=json.dumps(receipt, ensure_ascii=False),
            data=receipt, references=[receipt_ref] if receipt_ref else [], identity=identity,
        )
        failures = project_events(root)
    pending = next((item for item in failures if item["event_id"] == event_id), None)
    return pending["error"] if pending else None
