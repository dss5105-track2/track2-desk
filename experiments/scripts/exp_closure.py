"""Does spotting a closure from the queue help? Same orders and seeds, with and without the watch.

    python experiments/scripts/exp_closure.py   ->  ../simulator_assumptions/closure_detection.csv

Seeds 5105-5114 are the reported set. Seeds 6000-6049 were not used while the detector was written.
A false alarm is a flag in a run without a closure. simulate.py is unchanged.
"Perfect knowledge" is told the closed workshop and sends it nothing on days 30-44: the most any detector could gain.
"""
from __future__ import annotations

import csv
import random
import sys
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
OUT = HERE.parent / "simulator_assumptions"
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "harness"))
from simulate import Simulator  # noqa: E402
from kernel.allocator import Allocator, earliest_finish  # noqa: E402
from kernel.closure import ClosureAwareAllocator  # noqa: E402

CLOSE_START, CLOSE_END = 30, 44     # harness/simulate.py
SETS = {"reported 5105-5114": range(5105, 5115), "unseen 6000-6049": range(6000, 6050)}


class PerfectKnowledge:
    """Told which workshop closes and when."""

    def __init__(self, closed):
        self.allocator, self.closed, self.day0 = Allocator("use_slack"), closed, None

    def __call__(self, batch, workshops, queues):
        self.day0 = self.day0 or batch["sent_date"]
        day = (batch["sent_date"] - self.day0).days
        exclude = [self.closed] if self.closed and CLOSE_START <= day < CLOSE_END else []
        return self.allocator.choose(batch, workshops, queues, exclude=exclude) or self.allocator.choose(batch, workshops, queues)


def closed_shop(sim, seed):
    return random.Random(seed + 6).choice([w.workshop_id for w in sim.workshops.values() if w.status == "ACTIVE"])


def run(make, seeds, shock):
    late, days, flags, hit, right, early, reach = 0.0, 0.0, 0, 0, 0, 0, 0
    for seed in seeds:
        sim = Simulator(shock=shock, seed=seed)
        closed = closed_shop(sim, seed) if shock else None
        pol = make(closed)
        m = Simulator.metrics(sim.run(pol, "x"))
        late += m["% late"]
        days += m["late days"]
        events = pol.watch.events if isinstance(pol, ClosureAwareAllocator) else []
        flags += len(events)
        hit += bool(events)
        right += sum(e["workshop_id"] == closed for e in events)
        early += sum(e["day"] < CLOSE_START for e in events)
        reach += sum(e["day"] + e["excess"] > CLOSE_START for e in events)
    n = len(seeds)
    return {"pct_late": round(late / n, 3), "late_days": round(days / n, 3), "flags": flags, "flags_on_closed_shop": right, "flags_before_closure": early,
            "no_new_work_reaches_closure": reach, "runs_flagged": hit, "runs": n}


def main():
    policies = {"earliest_finish": lambda closed: earliest_finish, "use_slack": lambda closed: Allocator("use_slack"),
                "use_slack + closure watch": lambda closed: ClosureAwareAllocator(Allocator("use_slack")),
                "use_slack + perfect knowledge": PerfectKnowledge}
    rows = []
    for label, seeds in SETS.items():
        for shock in (False, True):
            for name, make in policies.items():
                rows.append({"seeds": label, "shock": shock, "policy": name, **run(make, seeds, shock)})
    with open(OUT / "closure_detection.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    for r in rows:
        print(r)


if __name__ == "__main__":
    main()
