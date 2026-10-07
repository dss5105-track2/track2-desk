"""Lab: can a readable allocation rule beat earliest_finish on lateness? Exploration only.

    python 实验/lab_allocators.py

Data sets: official 120 orders; the two repo stress scenarios (due_7_14, acc_surge); and a family of
perturbed copies of the official orders (dates and sizes jittered) to see whether a gain survives
outside the exact 120 orders it was found on.
"""
from __future__ import annotations

import csv
import random
import sys
from datetime import date, timedelta
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
REPO = HERE.parent / "track2-desk-优化版"
if not REPO.exists():          # inside the repo, this folder is round2/; the code is the repo root
    REPO = HERE.parent.parent
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(REPO / "harness")); sys.path.insert(0, str(REPO / "scenarios"))

import simulate  # noqa: E402
from simulate import Simulator, eligible_workshops, random_choice  # noqa: E402
from kernel.allocator import Allocator, earliest_finish  # noqa: E402
import make_scenario  # noqa: E402

OFFICIAL = REPO / "data"
TMP = HERE / "_data"
SEEDS = list(range(5105, 5115))


# ------------------------------------------------------------------ data sets
def write_set(name, rows):
    d = TMP / name / "data"
    d.mkdir(parents=True, exist_ok=True)
    (d / "workshops.csv").write_bytes((OFFICIAL / "workshops.csv").read_bytes())
    with open(d / "orders.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)
    return d


def official_rows():
    with open(OFFICIAL / "orders.csv", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def perturbed(rows, rng, date_jitter=5, size_lo=0.7, size_hi=1.3):
    out = []
    d0 = date(2026, 1, 1)
    for r in rows:
        od = date.fromisoformat(r["order_date"]); due = date.fromisoformat(r["due_date"])
        slack = (due - od).days
        od2 = max(d0, od + timedelta(days=rng.randint(-date_jitter, date_jitter)))
        pcs = max(100, min(2000, int(round(int(r["pieces"]) * rng.uniform(size_lo, size_hi) / 100.0)) * 100))
        r2 = dict(r); r2.update({"order_date": od2.isoformat(), "due_date": (od2 + timedelta(days=slack)).isoformat(), "pieces": str(pcs)})
        out.append(r2)
    return out


def build_sets(n_perturbed=30):
    rows = official_rows()
    sets = {"official": OFFICIAL}
    sets["due_7_14"] = write_set("due_7_14", make_scenario.rescale_slack([dict(r) for r in rows], dict(min_slack_days=7, max_slack_days=14), random.Random(5105)))
    sets["acc_surge"] = write_set("acc_surge", make_scenario.add_orders([dict(r) for r in rows], dict(category="ACCESSORIES", extra_orders=20), random.Random(5105)))
    for k in range(n_perturbed):
        sets[f"perturbed_{k:02d}"] = write_set(f"perturbed_{k:02d}", perturbed(rows, random.Random(9000 + k)))
    return sets


# ------------------------------------------------------------------ candidate policies
def est(w, batch, queues, defective=False):
    work = batch["pieces"] / w.capacity
    return queues[w.workshop_id] + work * (1.5 if defective else 1.0) + w.lead_days


def on_time(w, batch, queues, defective=False):
    done = batch["sent_date"] + timedelta(days=round(est(w, batch, queues, defective)))
    return done <= batch["due_date"]


def protect_dual(batch, workshops, queues):
    """TOPS go to TOPS-only shops when one of them is on time; otherwise earliest finish."""
    ok = eligible_workshops(batch, workshops)
    if batch["category"] == "TOPS":
        single = [w for w in ok if len(w.makes) == 1 and on_time(w, batch, queues)]
        if single:
            return min(single, key=lambda w: est(w, batch, queues)).workshop_id
    return min(ok, key=lambda w: est(w, batch, queues)).workshop_id


def flexibility(w, workshops):
    """How much of the order book a shop could take: categories it makes, capped batch counts as less."""
    return len(w.makes) + (0 if w.max_batch is None else -0.5)


def specialist_first(safe=False, tie="finish"):
    """Among shops that make the date (optionally even if the batch is reworked), take the least
    flexible one; among equals the earliest finish. If none makes the date: earliest finish."""
    def pol(batch, workshops, queues):
        ok = eligible_workshops(batch, workshops)
        good = [w for w in ok if on_time(w, batch, queues, defective=safe)]
        if not good and safe:
            good = [w for w in ok if on_time(w, batch, queues)]
        if not good:
            return min(ok, key=lambda w: est(w, batch, queues)).workshop_id
        if tie == "finish":
            key = lambda w: (flexibility(w, workshops), est(w, batch, queues))
        else:   # slowest capacity that still makes it: keep the big shops for the big batches
            key = lambda w: (flexibility(w, workshops), w.capacity, est(w, batch, queues))
        return min(good, key=key).workshop_id
    return pol


def smallest_that_makes_it(batch, workshops, queues):
    ok = eligible_workshops(batch, workshops)
    good = [w for w in ok if on_time(w, batch, queues)]
    if not good:
        return min(ok, key=lambda w: est(w, batch, queues)).workshop_id
    return min(good, key=lambda w: (w.capacity, est(w, batch, queues))).workshop_id


POLICIES = {
    "random": random_choice,
    "earliest_finish": earliest_finish,
    "cfg:lateness": Allocator("lateness"),
    "protect_dual": protect_dual,
    "specialist_first": specialist_first(),
    "specialist_first_safe": specialist_first(safe=True),
    "specialist_first_slowcap": specialist_first(tie="cap"),
    "smallest_that_makes_it": smallest_that_makes_it,
}


def run_set(data_dir, shock=False, seeds=SEEDS, policies=POLICIES):
    simulate.DATA = Path(data_dir)
    acc = {}
    for seed in seeds:
        sim = Simulator(shock=shock, seed=seed)
        for name, pol in policies.items():
            if hasattr(pol, "reset"):
                pol.reset()
            m = Simulator.metrics(sim.run(pol, name))
            a = acc.setdefault(name, {})
            for k, v in m.items():
                a[k] = a.get(k, 0.0) + v / len(seeds)
    simulate.DATA = OFFICIAL
    return acc


def show(title, acc):
    print(f"\n== {title}")
    print(f"{'policy':<26}{'% late':>8}{'late d':>8}{'p90':>7}{'mean':>7}{'% def pcs':>10}{'share':>7}{'cost':>9}")
    for name, m in acc.items():
        print(f"{name:<26}{m['% late']:>8.2f}{m['late days']:>8.2f}{m['p90 days']:>7.1f}{m['mean days']:>7.1f}{m['% def pcs']:>10.2f}{m['max share']:>7.1f}{m['cost']:>9.0f}")


if __name__ == "__main__":
    sets = build_sets()
    for name in ("official", "due_7_14", "acc_surge"):
        show(name, run_set(sets[name]))
        show(name + " --shock", run_set(sets[name], shock=True))
    # perturbed family: mean over 30 data sets (3 seeds each to keep it quick)
    fam = {}
    wins = {}
    for k in range(30):
        acc = run_set(sets[f"perturbed_{k:02d}"], seeds=SEEDS[:3])
        for name, m in acc.items():
            f = fam.setdefault(name, {})
            for kk, v in m.items():
                f[kk] = f.get(kk, 0.0) + v / 30
            d = m["% late"] - acc["earliest_finish"]["% late"]
            w = wins.setdefault(name, [0, 0, 0])
            w[0 if d < -1e-9 else (1 if abs(d) <= 1e-9 else 2)] += 1
    show("perturbed family (30 sets x 3 seeds), mean", fam)
    print("\n% late vs earliest_finish across the 30 sets  [better, equal, worse]:")
    for name, w in wins.items():
        print(f"  {name:<26}{w}")
