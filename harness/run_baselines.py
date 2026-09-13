"""Run the three official baselines, the ten-line heuristic and our configurable allocator
through the untouched shared simulator, and write the table to results/.

    python harness/run_baselines.py                # seed 5105, no shock
    python harness/run_baselines.py --shock        # closes one workshop for days 30-44
    python harness/run_baselines.py --seed 7 --objective hybrid

Every number quoted anywhere must come with: this command, the seed, and the git commit.
"""
import argparse
import csv
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "harness"))

from simulate import Simulator, random_choice, greedy_biggest, cheapest  # noqa: E402
from kernel.allocator import Allocator, earliest_finish, earliest_finish_with_rework, OBJECTIVES  # noqa: E402


def summarise(name, out):
    days = sorted(o["turnaround"] for o in out)
    n = len(out)
    by_w = {}
    for o in out:
        by_w[o["workshop"]] = by_w.get(o["workshop"], 0) + o["pieces"]
    pieces = sum(o["pieces"] for o in out)
    return {
        "policy": name,
        "mean_days": round(sum(days) / n, 2),
        "p90_days": round(days[int(0.9 * n)], 2),
        "pct_late": round(100 * sum(o["late"] for o in out) / n, 1),
        "pct_defect": round(100 * sum(o["defective"] for o in out) / n, 1),
        "cost": round(sum(o["cost"] for o in out)),
        "max_share": round(100 * max(by_w.values()) / pieces, 1),
        "late_by_workshop": {w: sum(1 for o in out if o["workshop"] == w and o["late"]) for w in sorted(by_w)},
    }


def git_commit():
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, text=True).strip()
    except Exception:
        return "no-git"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--shock", action="store_true")
    ap.add_argument("--seed", type=int, default=5105)
    ap.add_argument("--objective", default=None, help="one of " + ", ".join(OBJECTIVES) + " (default: all)")
    ap.add_argument("--out", default=str(ROOT / "results"))
    args = ap.parse_args()

    sim = Simulator(shock=args.shock, seed=args.seed)
    policies = [("random", random_choice), ("greedy_biggest", greedy_biggest), ("cheapest", cheapest),
                ("earliest_finish", earliest_finish), ("earliest_finish+rework", earliest_finish_with_rework)]
    objectives = [args.objective] if args.objective else list(OBJECTIVES)
    for obj in objectives:
        policies.append((f"cfg:{obj}", Allocator(obj)))

    rows = []
    for name, pol in policies:
        if hasattr(pol, "reset"):
            pol.reset()
        out = sim.run(pol, name)
        rows.append(summarise(name, out))
    sim.report()

    outdir = Path(args.out); outdir.mkdir(exist_ok=True)
    tag = f"seed{args.seed}{'_shock' if args.shock else ''}"
    path = outdir / f"baselines_{tag}.csv"
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["policy", "mean_days", "p90_days", "pct_late", "pct_defect", "cost", "max_share", "seed", "shock", "commit"])
        for r in rows:
            w.writerow([r["policy"], r["mean_days"], r["p90_days"], r["pct_late"], r["pct_defect"], r["cost"], r["max_share"],
                        args.seed, args.shock, git_commit()])
    print(f"\nwritten {path}  (commit {git_commit()})")
    if args.shock:
        print("late batches by workshop (shock run):")
        for r in rows:
            print(f"  {r['policy']:<24} {r['late_by_workshop']}")


if __name__ == "__main__":
    main()
