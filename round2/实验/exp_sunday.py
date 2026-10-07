"""Arguing with the harness, with evidence: what if workshops rest on Sundays?

    python 实验/exp_sunday.py     ->  ../05_模拟器假设/sunday_closed.csv

The Factory Primer says workshops work Monday to Saturday. simulate.py v3 states its assumption:
seven days a week. This script keeps everything else in the shared simulator identical (same orders,
same defect draws, same shock) and changes one thing: no work is done on Sundays. Transport still
takes calendar days. The allocators are NOT told; they keep estimating with seven-day weeks, as today.

A second variant tells our estimator about Sundays (work days x 7/6) to see how much of the damage is
the calendar itself and how much is the estimate being wrong about it.
"""
from __future__ import annotations

import csv
import math
import random
import sys
from datetime import timedelta
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
REPO = HERE.parent / "track2-desk-优化版"
if not REPO.exists():          # inside the repo, this folder is round2/; the code is the repo root
    REPO = HERE.parent.parent
OUT = HERE.parent / "05_模拟器假设"
OUT.mkdir(exist_ok=True)
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(REPO / "harness"))

from simulate import Simulator, eligible_workshops, random_choice  # noqa: E402
from kernel.allocator import Allocator, earliest_finish  # noqa: E402

SEEDS = list(range(5105, 5115))


class SundaySimulator(Simulator):
    """simulate.Simulator.run() with one change: a workshop does no work on Sundays."""

    def _is_sunday(self, day_number: float, day0) -> bool:
        return (day0 + timedelta(days=int(math.floor(day_number)))).weekday() == 6

    def _finish(self, start: float, work_days: float, day0) -> float:
        # start + work, pushed back one day for every Sunday the job would otherwise run through.
        # Written so that with no Sundays it returns start + work_days bit for bit, like simulate.py.
        t = float(start)
        if work_days <= 0:
            return t
        if self._is_sunday(t, day0):
            t = math.floor(t) + 1.0
        f = t + float(work_days)
        d = math.floor(t) + 1
        while d < f:
            if self._is_sunday(d, day0):
                f += 1.0
            d += 1
        return f

    def run(self, allocator, name):
        rng = random.Random(self.seed)
        day0 = self.batches[0]["sent_date"]
        queue_free = {w_id: w.queue0 for w_id, w in self.workshops.items()}
        shock_target, shock_start, shock_end = None, 30, 44
        if self.shock:
            shock_target = random.Random(self.seed + 6).choice([w.workshop_id for w in self.workshops.values() if w.status == "ACTIVE"])
        outcomes = []
        for batch in self.batches:
            day = (batch["sent_date"] - day0).days
            queues = {w: max(0.0, queue_free[w] - day) for w in self.workshops}
            choice = allocator(dict(batch), self.workshops, queues)
            ok = {w.workshop_id for w in eligible_workshops(batch, self.workshops)}
            if choice not in ok:
                raise ValueError(f"{name}: {choice} cannot take {batch['order_id']}")
            w = self.workshops[choice]
            start = max(day, queue_free[choice])
            work_days = batch["pieces"] / w.capacity
            defective = rng.random() < w.defect_rate
            if defective:
                work_days *= 1.5
            if shock_target == choice and shock_start <= start < shock_end:
                start = float(shock_end)                                  # closed: work waits until it reopens
            finish = self._finish(start, work_days, day0)                 # <- the only change: Sundays are skipped
            if shock_target == choice and start < shock_start < finish:
                finish = self._finish(finish + (shock_end - shock_start), 0.0, day0)     # caught mid-job: pauses for the closure
            queue_free[choice] = finish
            done_day = finish + w.lead_days
            done_date = day0 + timedelta(days=round(done_day))
            outcomes.append({"workshop": choice, "pieces": batch["pieces"], "turnaround": done_day - day, "late": done_date > batch["due_date"],
                             "days_late": max(0, (done_date - batch["due_date"]).days), "defective": defective, "cost": batch["pieces"] * w.cost})
        self.results[name] = outcomes
        return outcomes


class SundayAware:
    """Our lateness rule, with the estimate stretched for a six-day week (work and queue x 7/6)."""

    def __init__(self, objective="lateness"):
        self.inner = Allocator(objective)

    def reset(self):
        self.inner.reset()

    def __call__(self, batch, workshops, queues):
        import copy
        stretched = {}
        for wid, w in workshops.items():
            w2 = copy.copy(w)
            w2.capacity = w.capacity * 6.0 / 7.0          # six working days in seven
            stretched[wid] = w2
        return self.inner(batch, stretched, {k: v for k, v in queues.items()})


def policies():
    return [("random", random_choice), ("earliest_finish", earliest_finish), ("lateness_v1", Allocator("lateness_v1")),
            ("lateness (v2 rule)", Allocator("lateness")), ("lateness, Sunday-aware estimate", SundayAware("lateness")),
            ("use_slack", Allocator("use_slack")), ("hybrid", Allocator("hybrid"))]


def run(sim_cls, shock):
    acc = {}
    for seed in SEEDS:
        sim = sim_cls(shock=shock, seed=seed)
        for name, pol in policies():
            if hasattr(pol, "reset"):
                pol.reset()
            m = Simulator.metrics(sim.run(pol, name))
            a = acc.setdefault(name, {})
            for k, v in m.items():
                a[k] = a.get(k, 0.0) + v / len(SEEDS)
    return acc


if __name__ == "__main__":
    # sanity: with the Sunday rule switched off the subclass must reproduce the official simulator exactly
    class NoSunday(SundaySimulator):
        def _is_sunday(self, day_number, day0):
            return False
    for shock in (False, True):
        a, b = run(Simulator, shock), run(NoSunday, shock)
        for name in a:
            for k in a[name]:
                assert abs(a[name][k] - b[name][k]) < 1e-9, (shock, name, k, a[name][k], b[name][k])
    print("sanity: subclass with Sundays worked reproduces simulate.py exactly (normal and shock)")

    rows = []
    for label, cls in (("seven-day week (official)", Simulator), ("Sundays off", SundaySimulator)):
        for shock in (False, True):
            acc = run(cls, shock)
            for name, m in acc.items():
                rows.append([label, shock, name, round(m["% late"], 2), round(m["late days"], 3), round(m["mean days"], 2), round(m["p90 days"], 2),
                             round(m["% def pcs"], 2), round(m["cost"])])
    with open(OUT / "sunday_closed.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["calendar", "shock", "policy", "pct_late", "late_days", "mean_days", "p90_days", "pct_def_pcs", "cost"])
        w.writerows(rows)
    print(f"{'calendar':<27}{'shock':<7}{'policy':<34}{'% late':>8}{'late d':>8}{'mean':>7}{'p90':>7}")
    for r in rows:
        print(f"{r[0]:<27}{str(r[1]):<7}{r[2]:<34}{r[3]:>8.2f}{r[4]:>8.3f}{r[5]:>7.1f}{r[6]:>7.1f}")
