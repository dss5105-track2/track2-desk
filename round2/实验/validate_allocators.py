"""Validation of the candidate lateness rules on data that played no part in choosing them.

    python 实验/validate_allocators.py     ->  ../02_分配器/validation_*.csv

Candidates were explored on: the official 120 orders, the repo scenarios due_7_14 and acc_surge, and
30 perturbed sets (seeds 9000-9029). They are validated here on three fresh families (seeds 20000+,
different jitter and stress parameters). Baseline for every comparison: earliest_finish.
"""
from __future__ import annotations

import csv
import math
import random
import sys
from datetime import date, timedelta
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import lab_allocators as L  # noqa: E402
from lab_allocators import eligible_workshops, earliest_finish, est, on_time  # noqa: E402
import make_scenario  # noqa: E402

OUT = HERE.parent / "02_分配器"
OUT.mkdir(exist_ok=True)


# ------------------------------------------------------------------ the candidate rules (final form)
def _safe_set(batch, workshops, queues):
    ok = eligible_workshops(batch, workshops)
    good = [w for w in ok if on_time(w, batch, queues, defective=True)] or [w for w in ok if on_time(w, batch, queues)]
    return ok, good


def _borrow(w, batch, workshops):
    """Share of another category's total daily capacity that this shop represents (0 for a specialist)."""
    cap = {}
    for x in workshops.values():
        if x.status == "ACTIVE":
            for c in x.makes:
                cap[c] = cap.get(c, 0) + x.capacity
    return max((w.capacity / cap[c] for c in w.makes if c != batch["category"]), default=0.0)


def specialist_first_safe(batch, workshops, queues):
    ok, good = _safe_set(batch, workshops, queues)
    if not good:
        return min(ok, key=lambda w: est(w, batch, queues)).workshop_id
    return min(good, key=lambda w: (len(w.makes) + (0 if w.max_batch is None else -0.5), est(w, batch, queues))).workshop_id


def reserve_scarce(batch, workshops, queues):
    """Make the date safely; then borrow as little as possible from another category; then a batch-capped
    shop before an uncapped one; then earliest finish."""
    ok, good = _safe_set(batch, workshops, queues)
    if not good:
        return min(ok, key=lambda w: est(w, batch, queues)).workshop_id
    return min(good, key=lambda w: (round(_borrow(w, batch, workshops), 3), 0 if w.max_batch is not None else 1, est(w, batch, queues))).workshop_id


def just_in_time(batch, workshops, queues):
    """Same, but among equals take the LATEST safe finish (use the slack, keep fast shops free)."""
    ok, good = _safe_set(batch, workshops, queues)
    if not good:
        return min(ok, key=lambda w: est(w, batch, queues)).workshop_id
    return min(good, key=lambda w: (len(w.makes) + (0 if w.max_batch is None else -0.5), -est(w, batch, queues))).workshop_id


LAB_POLICIES = {"earliest_finish": earliest_finish, "specialist_first_safe": specialist_first_safe, "reserve_scarce": reserve_scarce, "just_in_time": just_in_time}

# What is reported: the rules as shipped in kernel/allocator.py (the lab functions above are the
# exploration versions; "lateness" is specialist_first_safe with the kernel's estimate, "use_slack" is
# just_in_time, "lateness_v1" is the round-1 weight setting that ties earliest_finish).
from kernel.allocator import Allocator  # noqa: E402

POLICIES = {"earliest_finish": earliest_finish, "lateness (v2 rule)": Allocator("lateness"), "use_slack": Allocator("use_slack"),
            "lateness_v1": Allocator("lateness_v1")}


# ------------------------------------------------------------------ fresh families
def fam_perturbed(k):
    return L.perturbed(L.official_rows(), random.Random(20000 + k), date_jitter=7, size_lo=0.6, size_hi=1.4)


def fam_tight(k):
    rows = L.perturbed(L.official_rows(), random.Random(21000 + k), date_jitter=7, size_lo=0.6, size_hi=1.4)
    return make_scenario.rescale_slack(rows, dict(min_slack_days=10, max_slack_days=21), random.Random(21000 + k))


def fam_acc(k):
    rows = L.perturbed(L.official_rows(), random.Random(22000 + k), date_jitter=7, size_lo=0.6, size_hi=1.4)
    return make_scenario.add_orders(rows, dict(category="ACCESSORIES", extra_orders=10), random.Random(22000 + k))


FAMILIES = [("fresh perturbed (100 sets)", fam_perturbed, 100), ("fresh tight due dates 10-21 days (50 sets)", fam_tight, 50),
            ("fresh +10 accessory orders (50 sets)", fam_acc, 50)]
SEEDS = [5105, 5106, 5107]
KEYS = ["% late", "late days", "mean days", "p90 days", "% def pcs", "max share", "cost"]


def sign_test_p(better, worse):
    n = better + worse
    if n == 0:
        return 1.0
    k = max(better, worse)
    p = sum(math.comb(n, i) for i in range(k, n + 1)) / 2 ** n * 2
    return min(1.0, p)


def main():
    rows_out, wins_out = [], []
    for title, make, n in FAMILIES:
        agg = {p: {k: 0.0 for k in KEYS} for p in POLICIES}
        wl = {p: {"late": [0, 0, 0], "days": [0, 0, 0]} for p in POLICIES}
        for k in range(n):
            d = L.write_set(f"val_{title.split()[1]}_{k:03d}", make(k))
            acc = L.run_set(d, seeds=SEEDS, policies=POLICIES)
            for p, m in acc.items():
                for kk in KEYS:
                    agg[p][kk] += m[kk] / n
                for key, metric in (("late", "% late"), ("days", "late days")):
                    diff = m[metric] - acc["earliest_finish"][metric]
                    wl[p][key][0 if diff < -1e-9 else (1 if abs(diff) <= 1e-9 else 2)] += 1
        print(f"\n== {title}, {len(SEEDS)} seeds each")
        print(f"{'policy':<24}{'% late':>8}{'late d':>8}{'mean':>7}{'p90':>7}{'def pcs':>9}{'share':>7}{'cost':>9}   % late vs EF [better,equal,worse]  p")
        for p in POLICIES:
            a, w = agg[p], wl[p]["late"]
            pv = sign_test_p(w[0], w[2])
            print(f"{p:<24}{a['% late']:>8.2f}{a['late days']:>8.3f}{a['mean days']:>7.1f}{a['p90 days']:>7.1f}{a['% def pcs']:>9.2f}{a['max share']:>7.1f}{a['cost']:>9.0f}   {w}  {pv:.4f}")
            rows_out.append([title, p] + [round(a[k], 3) for k in KEYS])
            wins_out.append([title, p] + wl[p]["late"] + [round(pv, 5)] + wl[p]["days"] + [round(sign_test_p(wl[p]["days"][0], wl[p]["days"][2]), 5)])
    # the data used while exploring, for the record (10 seeds)
    sets = L.build_sets(n_perturbed=0)
    for name, shock in (("official", False), ("official", True), ("due_7_14", False), ("acc_surge", False)):
        acc = L.run_set(sets[name], shock=shock, policies=POLICIES)
        title = f"{name}{' --shock' if shock else ''} (used while exploring)"
        L.show(title, acc)
        for p, m in acc.items():
            rows_out.append([title, p] + [round(m[k], 3) for k in KEYS])
    with open(OUT / "validation_means.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f); w.writerow(["data", "policy"] + ["pct_late", "late_days", "mean_days", "p90_days", "pct_def_pcs", "max_share", "cost"]); w.writerows(rows_out)
    with open(OUT / "validation_wins_vs_earliest_finish.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["data", "policy", "pct_late_better", "pct_late_equal", "pct_late_worse", "sign_test_p", "late_days_better", "late_days_equal", "late_days_worse", "sign_test_p_late_days"])
        w.writerows(wins_out)


if __name__ == "__main__":
    main()
