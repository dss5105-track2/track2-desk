"""Session ledger: the queue state that every later request must see, plus the audit record.

Protocol (eval/protocol.md):
  * queues start from workshops.csv current_queue_days on "today"
  * only a confirmed commit changes a queue
  * a record is written for every commit and can be reviewed six weeks later
Queue bookkeeping mirrors simulate.py: start = max(day, queue_free); queue_free = start + work.
We add the expected rework to the queue because that is our best estimate; the simulator
adds 1.5x work only when the defect draw hits.
"""
from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from .estimator import estimate
from .register import check_eligibility


class Ledger:
    def __init__(self, workshops, today: date):
        self.workshops = workshops
        self.today = today
        self.queue_free: Dict[str, float] = {wid: float(w.queue0) for wid, w in workshops.items()}
        self.records: List[dict] = []
        self.seq = 0

    def day(self, on: Optional[date] = None) -> int:
        return ((on or self.today) - self.today).days

    def queues(self, on: Optional[date] = None) -> Dict[str, float]:
        d = self.day(on)
        return {wid: max(0.0, qf - d) for wid, qf in self.queue_free.items()}

    def already_committed(self, order_id: str) -> Optional[dict]:
        for r in self.records:
            if r["order_id"] == order_id and r["status"] == "committed":
                return r
        return None

    def commit(self, *, request_id: str, order_id: str, workshop_id: str, category: str, pieces: int,
               sent_date: date, due_date: date, requester: str, confirmed_by: str, reason: str,
               constraints: Optional[dict] = None, candidates: Optional[list] = None,
               objective: Optional[dict] = None, model_version: str = "n/a", tool_version: str = "kernel-0.1") -> dict:
        w = self.workshops[workshop_id]
        ok, why = check_eligibility(w, category, pieces)
        if not ok:
            raise ValueError(f"{workshop_id} cannot take {order_id}: {why}")
        prior = self.already_committed(order_id)
        if prior is not None:
            raise ValueError(f"{order_id} already committed to {prior['workshop_id']} by {prior['request_id']}")
        before = self.queues(sent_date)
        est = estimate(w, pieces, before[workshop_id], sent_date, due_date)
        d = self.day(sent_date)
        start = max(float(d), self.queue_free[workshop_id])
        self.queue_free[workshop_id] = start + est.work_days + est.rework_days
        self.seq += 1
        rec = {
            "audit_id": f"A{self.seq:04d}",
            "written_at": datetime.now().isoformat(timespec="seconds"),
            "request_id": request_id,
            "requester": requester,
            "confirmed_by": confirmed_by,
            "order_id": order_id,
            "category": category,
            "pieces": pieces,
            "sent_date": sent_date.isoformat(),
            "due_date": due_date.isoformat(),
            "constraints": constraints or {},
            "objective": objective or {},
            "candidates": candidates or [],
            "workshop_id": workshop_id,
            "estimate": est.as_dict(),
            "reason": reason,
            "queue_before": before[workshop_id],
            "queue_after": self.queues(sent_date)[workshop_id],
            "tool_version": tool_version,
            "model_version": model_version,
            "status": "committed",
        }
        self.records.append(rec)
        return rec

    def reassign(self, audit_id: str, new_workshop_id: str, confirmed_by: str, reason: str) -> dict:
        """Undo a commit and re-commit elsewhere. The only way to correct a wrong dispatch."""
        old = next(r for r in self.records if r["audit_id"] == audit_id)
        old["status"] = "reassigned"
        # rebuild queues from scratch: replay all committed records in order
        self.queue_free = {wid: float(w.queue0) for wid, w in self.workshops.items()}
        live = [r for r in self.records if r["status"] == "committed"]
        self.records = [r for r in self.records if r["status"] != "committed"]
        for r in live:
            self.commit(request_id=r["request_id"], order_id=r["order_id"], workshop_id=r["workshop_id"],
                        category=r["category"], pieces=r["pieces"], sent_date=date.fromisoformat(r["sent_date"]),
                        due_date=date.fromisoformat(r["due_date"]), requester=r["requester"],
                        confirmed_by=r["confirmed_by"], reason=r["reason"], constraints=r["constraints"],
                        candidates=r["candidates"], objective=r["objective"])
        return self.commit(request_id=old["request_id"], order_id=old["order_id"], workshop_id=new_workshop_id,
                           category=old["category"], pieces=old["pieces"], sent_date=date.fromisoformat(old["sent_date"]),
                           due_date=date.fromisoformat(old["due_date"]), requester=old["requester"],
                           confirmed_by=confirmed_by, reason=reason, constraints=old["constraints"],
                           candidates=old["candidates"], objective=old["objective"])

    def save(self, path: Path) -> None:
        path.write_text(json.dumps(self.records, ensure_ascii=False, indent=2), encoding="utf-8")
