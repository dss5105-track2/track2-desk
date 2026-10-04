"""Multi-seed runner: the defect draws are random, so one seed is one sample.

    python harness/run_seeds.py --seeds 5105 1 2 3 4 5 6 7 8 9
    python harness/run_seeds.py --shock --seeds 5105 1 2 3 4 5

Prints min / mean / max of % late and P90 per policy and writes results/seeds_*.csv.
Note: with --shock the closed workshop depends on the seed (simulate.py v3 draws it from its
own stream, seed + 6); the per-seed target is recorded in the CSV. For the averaged table
the track asks for, use run_baselines.py --shock (seeds 5105..5114).
"""
import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "harness"))

from simulate import Simulator, random_choice, greedy_biggest, cheapest  # noqa: E402
from kernel.allocator import Allocator, earliest_finish, OBJECTIVES  # noqa: E402
from run_baselines import summarise, shock_target  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, nargs="+", default=[5105, 1, 2, 3, 4, 5])
    ap.add_argument("--shock", action="store_true")
    ap.add_argument("--objectives", nargs="*", default=list(OBJECTIVES))
    args = ap.parse_args()

    table = []
    for seed in args.seeds:
        sim = Simulator(shock=args.shock, seed=seed)
        target = shock_target(sim) if args.shock else ""
        pols = [("random", random_choice), ("greedy_biggest", greedy_biggest), ("cheapest", cheapest),
                ("earliest_finish", earliest_finish)] + [(f"cfg:{o}", Allocator(o)) for o in args.objectives]
        for name, pol in pols:
            r = summarise(name, sim.run(pol, name))
            r["seed"] = seed; r["shock_target"] = target
            table.append(r)

    outdir = ROOT / "results"; outdir.mkdir(exist_ok=True)
    path = outdir / f"seeds_{'shock_' if args.shock else ''}{'_'.join(map(str, args.seeds))}.csv"
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["policy", "seed", "shock_target", "mean_days", "p90_days", "pct_late", "late_days",
                                          "pct_defect", "pct_def_pcs", "cost", "max_share"])
        w.writeheader()
        for r in table:
            w.writerow({k: r[k] for k in w.fieldnames})

    print(f"{'policy':<24}{'late min':>10}{'late mean':>11}{'late max':>10}{'p90 min':>9}{'p90 mean':>10}{'p90 max':>9}")
    for name in dict.fromkeys(r["policy"] for r in table):
        rs = [r for r in table if r["policy"] == name]
        late = [r["pct_late"] for r in rs]; p90 = [r["p90_days"] for r in rs]
        print(f"{name:<24}{min(late):>9.1f}%{sum(late)/len(late):>10.1f}%{max(late):>9.1f}%{min(p90):>9.1f}{sum(p90)/len(p90):>10.1f}{max(p90):>9.1f}")
    print(f"\nwritten {path}")


if __name__ == "__main__":
    main()
