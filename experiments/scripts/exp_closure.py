"""Does spotting a closure from the queue help? Same orders and seeds, with and without the watch.

    python experiments/scripts/exp_closure.py   ->  ../simulator_assumptions/closure_detection.csv

Seeds 5105-5114 are the reported set. Seeds 6000-6049 were not used while the detector was written.
A false alarm is a flag in a run without a closure. simulate.py is unchanged.
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

SETS = {"reported 5105-5114": range(5105, 5115), "unseen 6000-6049": range(6000, 6050)}


def run(make, seeds, shock):
    late, days, flags, hit, right = 0.0, 0.0, 0, 0, 0
    for seed in seeds:
        sim = Simulator(shock=shock, seed=seed)
        pol = make()
        m = Simulator.metrics(sim.run(pol, "x"))
        late += m["% late"]
        days += m["late days"]
        events = pol.watch.events if isinstance(pol, ClosureAwareAllocator) else []
        flags += len(events)
        hit += bool(events)
        if shock:
            closed = random.Random(seed + 6).choice([w.workshop_id for w in sim.workshops.values() if w.status == "ACTIVE"])
            right += sum(e["workshop_id"] == closed for e in events)
    n = len(seeds)
    return {"pct_late": round(late / n, 3), "late_days": round(days / n, 3), "flags": flags, "flags_on_closed_shop": right, "runs_flagged": hit, "runs": n}


def main():
    policies = {"earliest_finish": lambda: earliest_finish, "use_slack": lambda: Allocator("use_slack"),
                "use_slack + closure watch": lambda: ClosureAwareAllocator(Allocator("use_slack"))}
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
