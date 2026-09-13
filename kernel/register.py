"""Workshop register: load the profile cards and answer the dispatcher's three questions.

The attribute names deliberately match the Workshop dataclass in harness/simulate.py,
so every function here accepts either our Workshop or the simulator's.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


@dataclass(frozen=True)
class Workshop:
    workshop_id: str
    name: str
    capacity: int          # pieces per day
    lead_days: int         # pickup + delivery overhead
    defect_rate: float
    cost: float            # per piece
    makes: frozenset       # {"TOPS"}, {"ACCESSORIES"} or both
    status: str            # ACTIVE / SUSPENDED
    max_batch: Optional[int]
    queue0: float          # days of work already held on the data-dictionary "today"
    notes: str


def load_workshops(path: Path = DATA_DIR / "workshops.csv") -> Dict[str, Workshop]:
    out: Dict[str, Workshop] = {}
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            out[r["workshop_id"]] = Workshop(
                workshop_id=r["workshop_id"],
                name=r["name"],
                capacity=int(r["capacity_pieces_per_day"]),
                lead_days=int(r["pickup_lead_days"]),
                defect_rate=float(r["defect_rate"]),
                cost=float(r["cost_per_piece"]),
                makes=frozenset(r["makes"].split("+")),
                status=r["status"],
                max_batch=int(r["max_batch_pieces"]) if r["max_batch_pieces"] else None,
                queue0=float(r["current_queue_days"]),
                notes=r["notes"],
            )
    return out


def _norm(s: str) -> str:
    return "".join(ch for ch in s.lower() if ch.isalnum())


def find_by_name(workshops: Dict[str, "Workshop"], text: str) -> List[str]:
    """Return workshop_ids whose name (or id) appears in free text, e.g. 'OldMill', 'Little Loom'."""
    t = _norm(text)
    hits = []
    for w in workshops.values():
        if _norm(w.name) in t or _norm(w.workshop_id) in t.split():
            hits.append(w.workshop_id)
    return hits


def check_eligibility(w, category: str, pieces: int) -> Tuple[bool, str]:
    """The three questions, with the reason a dispatcher would give."""
    if w.status != "ACTIVE":
        return False, f"status={w.status}"
    if category not in w.makes:
        return False, f"cannot make {category} (equipped for {'+'.join(sorted(w.makes))})"
    if w.max_batch is not None and pieces > w.max_batch:
        return False, f"batch of {pieces} exceeds its {w.max_batch}-piece limit"
    return True, "eligible"


def eligible_workshops(workshops, category: str, pieces: int, exclude: Iterable[str] = ()) -> List:
    """Same rule as simulate.eligible_workshops(), plus user-imposed exclusions."""
    ex = set(exclude)
    return [
        w for w in workshops.values()
        if w.workshop_id not in ex and check_eligibility(w, category, pieces)[0]
    ]


def eligibility_table(workshops, category: str, pieces: int, exclude: Iterable[str] = ()) -> List[dict]:
    """Every workshop with its verdict and reason. This is what the UI shows in the candidate table."""
    ex = set(exclude)
    rows = []
    for w in workshops.values():
        ok, why = check_eligibility(w, category, pieces)
        if w.workshop_id in ex:
            ok, why = False, "excluded by request"
        rows.append({"workshop_id": w.workshop_id, "name": w.name, "eligible": ok, "reason": why})
    return rows
