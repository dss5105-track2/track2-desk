"""Spotting a workshop that has stopped, from its queue alone.

The simulator does not announce a closure. The only trace is that a workshop's queue comes back longer than
anything we sent it can explain. After each dispatch we keep the worst case the queue could reach (the batch
reworked, which takes 1.5 times the work). A queue above that worst case cannot be a defect, so it is flagged.
"""
from __future__ import annotations

from typing import Dict, List, Optional

REWORK_FACTOR = 1.5     # harness/simulate.py: half a defective batch is redone
TOLERANCE_DAYS = 0.5    # a jump smaller than this is not worth an alarm


class QueueWatch:
    """Compares each observed queue with the worst case expected from what was dispatched."""

    def __init__(self, tolerance: float = TOLERANCE_DAYS):
        self.tolerance = tolerance
        self.worst_free: Dict[str, float] = {}      # workshop -> latest day its current work can finish, closures aside
        self.stopped_until: Dict[str, float] = {}   # workshop -> day the unexplained part of its queue runs out
        self.events: List[dict] = []

    def observe(self, day: float, queues: Dict[str, float]) -> List[str]:
        """Record today's queues. Returns the workshops newly flagged."""
        flagged = []
        for wid, queue in queues.items():
            if wid in self.worst_free:
                expected = max(0.0, self.worst_free[wid] - day)
                excess = queue - expected
                if excess > self.tolerance:
                    self.stopped_until[wid] = day + excess
                    self.events.append({"day": day, "workshop_id": wid, "queue": queue, "expected": expected, "excess": excess})
                    flagged.append(wid)
            self.worst_free[wid] = day + queue
        return flagged

    def dispatched(self, wid: str, work_days: float) -> None:
        self.worst_free[wid] += work_days * REWORK_FACTOR

    def stopped(self, day: float) -> List[str]:
        return sorted(wid for wid, until in self.stopped_until.items() if day < until)


class ClosureAwareAllocator:
    """An Allocator for the simulator that sends no new work to a workshop flagged as stopped,
    unless no other workshop can take the batch. There is no human in a simulator run, so a flag acts at once."""

    def __init__(self, allocator, tolerance: float = TOLERANCE_DAYS):
        self.allocator = allocator
        self.tolerance = tolerance
        self.reset()

    def reset(self) -> None:
        self.allocator.reset()
        self.watch = QueueWatch(self.tolerance)
        self.day0 = None

    def __call__(self, batch: dict, workshops, queues: Dict[str, float]) -> str:
        if self.day0 is None:
            self.day0 = batch["sent_date"]
        day = (batch["sent_date"] - self.day0).days
        self.watch.observe(day, queues)
        choice: Optional[str] = self.allocator.choose(batch, workshops, queues, exclude=self.watch.stopped(day))
        if choice is None:
            choice = self.allocator.choose(batch, workshops, queues)
        if choice is None:
            raise ValueError(f"no eligible workshop for {batch['order_id']}")
        self.watch.dispatched(choice, batch["pieces"] / workshops[choice].capacity)
        return choice
