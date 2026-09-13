"""Delivery-date estimator: queue + processing + expected rework + transport.

Mirrors harness/simulate.py exactly where the simulator is deterministic:
    work_days   = pieces / capacity
    done_day    = start + work_days + lead_days
    done_date   = sent_date + round(done_day)         (Python round: half-to-even)
    late        = done_date > due_date
The only stochastic part of the simulator is the defect draw (probability defect_rate,
work_days * 1.5 if it happens). We cannot know the draw, so we report its expectation:
    rework_days = defect_rate * 0.5 * work_days
and expose it as a separate component so the explanation can say so.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import date, timedelta
from typing import Dict, Iterable, List

from .register import eligible_workshops


@dataclass
class Estimate:
    workshop_id: str
    name: str
    queue_days: float
    work_days: float
    rework_days: float
    lead_days: float
    finish_days: float          # queue + work + rework + lead, counted from sent_date
    promised_date: date         # sent_date + round(finish_days)
    late_days: int              # max(0, promised - due)
    on_time: bool
    cost: float
    defect_rate: float

    def as_dict(self) -> dict:
        d = asdict(self)
        d["promised_date"] = self.promised_date.isoformat()
        return d


def estimate(w, pieces: int, queue_days: float, sent_date: date, due_date: date,
             include_rework: bool = True) -> Estimate:
    work = pieces / w.capacity
    rework = 0.5 * w.defect_rate * work if include_rework else 0.0
    finish = queue_days + work + rework + w.lead_days
    promised = sent_date + timedelta(days=round(finish))
    late = max(0, (promised - due_date).days)
    return Estimate(
        workshop_id=w.workshop_id, name=w.name,
        queue_days=queue_days, work_days=work, rework_days=rework, lead_days=float(w.lead_days),
        finish_days=finish, promised_date=promised, late_days=late, on_time=promised <= due_date,
        cost=pieces * w.cost, defect_rate=w.defect_rate,
    )


def estimate_all(workshops, category: str, pieces: int, queues: Dict[str, float],
                 sent_date: date, due_date: date, exclude: Iterable[str] = (),
                 include_rework: bool = True) -> List[Estimate]:
    """One Estimate per eligible workshop, earliest finish first."""
    out = []
    for w in eligible_workshops(workshops, category, pieces, exclude):
        q = queues.get(w.workshop_id, getattr(w, "queue0", 0.0))
        out.append(estimate(w, pieces, q, sent_date, due_date, include_rework))
    out.sort(key=lambda e: e.finish_days)
    return out


def split_estimate(workshops, category: str, pieces: int, queues: Dict[str, float],
                   sent_date: date, due_date: date, exclude: Iterable[str] = ()) -> dict:
    """What a 2-way split could achieve, for the 'split it across two shops' requests.

    Greedy: give each of the two earliest-finishing shops the share that equalises finish.
    The official simulator cannot split; this is only for the chat answer and must say so.
    """
    ests = estimate_all(workshops, category, pieces, queues, sent_date, due_date, exclude, include_rework=False)
    if len(ests) < 2:
        return {"possible": False, "reason": "fewer than two eligible workshops"}
    a, b = ests[0], ests[1]
    wa = workshops[a.workshop_id]; wb = workshops[b.workshop_id]
    fixed_a = a.queue_days + wa.lead_days
    fixed_b = b.queue_days + wb.lead_days
    # solve fixed_a + x/cap_a = fixed_b + (pieces-x)/cap_b for x
    x = (fixed_b - fixed_a + pieces / wb.capacity) / (1 / wa.capacity + 1 / wb.capacity)
    x = max(0, min(pieces, int(round(x))))
    fa = fixed_a + x / wa.capacity
    fb = fixed_b + (pieces - x) / wb.capacity
    finish = max(fa, fb)
    return {
        "possible": True,
        "plan": [{"workshop_id": a.workshop_id, "pieces": x, "finish_days": fa},
                 {"workshop_id": b.workshop_id, "pieces": pieces - x, "finish_days": fb}],
        "finish_days": finish,
        "single_best_finish_days": a.finish_days,
        "gain_days": a.finish_days - finish,
        "promised_date": (sent_date + timedelta(days=round(finish))).isoformat(),
        "note": "official simulator does not support splitting; chat-layer estimate only",
    }
