"""use_slack against the specialist-first-earliest rule ("lateness"), head to head, same data, same seeds.

    python 实验/head_to_head.py     ->  ../02_分配器/head_to_head_use_slack_vs_lateness.csv

Both policies share steps 1-2 (rework-safe set, least flexible shop first) and differ only in the tie-break:
earliest finish (lateness) or latest safe finish (use_slack). Reported per seed on the official orders (normal and
--shock) and per data set on the three fresh families from validate_allocators.py, so the question "which one is
the better lateness policy" is answered on paired runs, not on means alone.
"""
from __future__ import annotations

import csv
import math
import sys
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import lab_allocators as L  # noqa: E402
import validate_allocators as V  # noqa: E402
from simulate import Simulator  # noqa: E402
from kernel.allocator import Allocator  # noqa: E402

OUT = HERE.parent / "02_分配器"
POL = {"lateness": Allocator("lateness"), "use_slack": Allocator("use_slack")}
KEYS = ["% late", "late days", "mean days", "p90 days", "cost"]


def one_run(data_dir, seed, shock=False):
    import simulate
    simulate.DATA = Path(data_dir)
    out = {}
    sim = Simulator(shock=shock, seed=seed)
    for name, pol in POL.items():
        pol.reset()
        out[name] = Simulator.metrics(sim.run(pol, name))
    simulate.DATA = L.OFFICIAL
    return out


def tally(pairs, metric):
    b = e = w = 0
    for a in pairs:
        d = a["use_slack"][metric] - a["lateness"][metric]
        if d < -1e-9:
            b += 1
        elif d > 1e-9:
            w += 1
        else:
            e += 1
    return b, e, w, V.sign_test_p(b, w)


def main():
    rows = []
    sets = L.build_sets(n_perturbed=0)
    blocks = []
    for title, shock in (("official 120 orders, 10 seeds", False), ("official --shock, 10 seeds", True)):
        pairs = [one_run(sets["official"], s, shock) for s in range(5105, 5115)]
        blocks.append((title, pairs))
    for title, make, n in V.FAMILIES:
        pairs = []
        for k in range(n):
            d = L.write_set(f"h2h_{title.split()[1]}_{k:03d}", make(k))
            # mean over the 3 validation seeds, one pair per data set
            acc = {p: {m: 0.0 for m in KEYS} for p in POL}
            for s in V.SEEDS:
                r = one_run(d, s)
                for p in POL:
                    for m in KEYS:
                        acc[p][m] += r[p][m] / len(V.SEEDS)
            pairs.append(acc)
        blocks.append((title, pairs))

    print(f"{'data':<44}{'policy':<10}{'% late':>8}{'late d':>8}{'mean':>7}{'p90':>7}{'cost':>9}   use_slack vs lateness on % late [better,equal,worse] p | late days [b,e,w] p")
    for title, pairs in blocks:
        n = len(pairs)
        means = {p: {m: sum(a[p][m] for a in pairs) / n for m in KEYS} for p in POL}
        bl, el, wl, pl = tally(pairs, "% late")
        bd, ed, wd, pd = tally(pairs, "late days")
        lo = {p: min(a[p]["% late"] for a in pairs) for p in POL}
        hi = {p: max(a[p]["% late"] for a in pairs) for p in POL}
        for p in POL:
            m = means[p]
            print(f"{title:<44}{p:<10}{m['% late']:>8.2f}{m['late days']:>8.3f}{m['mean days']:>7.1f}{m['p90 days']:>7.1f}{m['cost']:>9.0f}"
                  + (f"   [{bl},{el},{wl}] {pl:.4f} | [{bd},{ed},{wd}] {pd:.4f}" if p == "use_slack" else "")
                  + f"   range % late {lo[p]:.2f}-{hi[p]:.2f}")
            rows.append([title, p] + [round(m[k], 3) for k in KEYS] + [round(lo[p], 3), round(hi[p], 3)]
                        + ([bl, el, wl, round(pl, 5), bd, ed, wd, round(pd, 5)] if p == "use_slack" else [""] * 8))
    with open(OUT / "head_to_head_use_slack_vs_lateness.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["data", "policy", "pct_late", "late_days", "mean_days", "p90_days", "cost", "pct_late_min", "pct_late_max",
                    "pct_late_better", "pct_late_equal", "pct_late_worse", "sign_test_p", "late_days_better", "late_days_equal", "late_days_worse", "sign_test_p_late_days"])
        w.writerows(rows)
    print("wrote", OUT / "head_to_head_use_slack_vs_lateness.csv")


if __name__ == "__main__":
    main()
