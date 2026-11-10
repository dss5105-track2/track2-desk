"""Read-only presentation of a dispatcher's proposed workshop choice."""
from __future__ import annotations

import hashlib
import json


def candidate_widget_key(decision: dict) -> str:
    # Any fresh estimate or ranking invalidates an old row index.
    payload = {key: decision.get(key) for key in ("status", "recommended", "candidates", "batch")}
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()[:16]
    return f"candidate_{decision['request_id']}_{digest}"


def candidate_from_rows(decision: dict, rows):
    if len(rows) != 1 or not isinstance(rows[0], int):
        return None
    index = rows[0]
    return decision["candidates"][index] if 0 <= index < len(decision["candidates"]) else None


def dispatch_label(candidate: dict | None, *, preferred: bool = False) -> str:
    if candidate is None:
        return "Send to selected workshop"
    if not candidate["on_time"]:
        return f"Accept delay · send to {candidate['name']}"
    return f"{'Confirm' if preferred else 'Send to'} {candidate['name']}"


def reply_draft(decision: dict, candidate: dict | None) -> str:
    if candidate is None or candidate["workshop_id"] == decision["recommended"]:
        return decision["explanation"]
    batch = decision["batch"]
    timing = "on time" if candidate["on_time"] else f"{candidate['late_days']} days late; delay must be accepted"
    rework = candidate["worst_date"] + (" (late)" if not candidate["safe"] else "")
    return (f"Proposed dispatch for {decision['order_id']} ({batch['pieces']} pcs): {candidate['name']}. "
            f"Estimated back {candidate['promised_date']}, due {batch['due_date']} — {timing}. "
            f"If reworked: {rework}. Cost {candidate['cost']:.0f}. "
            "Awaiting dispatcher confirmation; nothing has been dispatched by this selection.")
