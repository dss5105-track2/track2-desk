"""Run the three official baselines, the simple rule-based allocator (earliest_finish) and our
configurable allocator through the untouched shared simulator, and write the table to results/.

    python harness/run_baselines.py                # seed 5105, no shock
    python harness/run_baselines.py --shock        # seeds 5105..5114 averaged, as Tracks v4 asks
    python harness/run_baselines.py --shock --seeds 1               # one seed only
    python harness/run_baselines.py --seed 7 --objective hybrid

Metrics come from simulate.Simulator.metrics(), so they match the official report() exactly,
including the two v3 columns `late days` and `% def pcs`. With --shock the same seeds are also
run without the closure, and the table adds the robustness metric: the change in % late and
late days from the normal run to --shock, averaged over the seeds.

Every number quoted anywhere must come with: this command, the seeds, and the git commit.
"""
import argparse
import csv
import random
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "harness"))

from simulate import Simulator, print_table, random_choice, greedy_biggest, cheapest  # noqa: E402
from kernel.allocator import Allocator, earliest_finish, earliest_finish_with_rework, OBJECTIVES  # noqa: E402

KEYS = [("mean_days", "mean days", 2), ("p90_days", "p90 days", 2), ("pct_late", "% late", 1),
        ("late_days", "late days", 2), ("pct_defect", "% defect", 1), ("pct_def_pcs", "% def pcs", 1),
        ("cost", "cost", 0), ("max_share", "max share", 1)]


def summarise(name, out):
    m = Simulator.metrics(out)
    row = {"policy": name}
    for col, key, nd in KEYS:
        row[col] = round(m[key], nd) if nd else round(m[key])
    workshops = sorted({o["workshop"] for o in out})
    row["late_by_workshop"] = {w: sum(1 for o in out if o["workshop"] == w and o["late"]) for w in workshops}
    return row


def shock_target(sim):
    """Which workshop --shock closes for this seed (mirrors simulate.py v3: its own stream, seed + 6)."""
    return random.Random(sim.seed + 6).choice([w.workshop_id for w in sim.workshops.values() if w.status == "ACTIVE"])


def git_commit():
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, text=True).strip()
    except Exception:
        return "no-git"


def policies(objective=None):
    pols = [("random", random_choice), ("greedy_biggest", greedy_biggest), ("cheapest", cheapest),
            ("earliest_finish", earliest_finish), ("earliest_finish+rework", earliest_finish_with_rework)]
    for obj in ([objective] if objective else list(OBJECTIVES)):
        pols.append((f"cfg:{obj}", Allocator(obj)))
    return pols


def run_once(sim, pols):
    out = {}
    for name, pol in pols:
        if hasattr(pol, "reset"):
            pol.reset()
        out[name] = sim.run(pol, name)
    return out


def mean_metrics(per_seed):
    """per_seed: list of {policy: metrics dict}. Same averaging as simulate.average_over_seeds()."""
    names = list(per_seed[0])
    return {n: {k: sum(s[n][k] for s in per_seed) / len(per_seed) for k in per_seed[0][n]} for n in names}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--shock", action="store_true")
    ap.add_argument("--seed", type=int, default=5105, help="first seed")
    ap.add_argument("--seeds", type=int, default=None, metavar="N",
                    help="average over N seeds starting at --seed (default: 10 with --shock, else 1)")
    ap.add_argument("--objective", default=None, help="one of " + ", ".join(OBJECTIVES) + " (default: all)")
    ap.add_argument("--out", default=str(ROOT / "results"))
    args = ap.parse_args()

    n = args.seeds or (10 if args.shock else 1)
    seeds = list(range(args.seed, args.seed + n))
    pols = policies(args.objective)

    shocked, normal, targets, last_rows = [], [], [], []
    for seed in seeds:
        sim = Simulator(shock=args.shock, seed=seed)
        outs = run_once(sim, pols)
        shocked.append({name: Simulator.metrics(o) for name, o in outs.items()})
        last_rows = [summarise(name, o) for name, o in outs.items()]
        if args.shock:
            targets.append(shock_target(sim))
            base = Simulator(shock=False, seed=seed)
            normal.append({name: Simulator.metrics(o) for name, o in run_once(base, pols).items()})

    avg = mean_metrics(shocked)
    label = f"seed {seeds[0]}" if n == 1 else f"average over seeds {seeds[0]}..{seeds[-1]}"
    print(f"{label}{'  --shock' if args.shock else ''}")
    print_table(avg)

    delta = {}
    if args.shock:
        base_avg = mean_metrics(normal)
        for name in avg:
            delta[name] = (avg[name]["% late"] - base_avg[name]["% late"],
                           avg[name]["late days"] - base_avg[name]["late days"])
        print("\nclosed workshop per seed: " + ", ".join(f"{s}:{t}" for s, t in zip(seeds, targets)))
        print("robustness (shock minus normal, same seeds):")
        print(f"  {'policy':<24}{'d % late':>10}{'d late days':>13}{'normal % late':>15}")
        for name, (dl, dd) in delta.items():
            print(f"  {name:<24}{dl:>+9.1f}%{dd:>+13.2f}{base_avg[name]['% late']:>14.1f}%")

    outdir = Path(args.out); outdir.mkdir(exist_ok=True)
    tag = f"seed{seeds[0]}" if n == 1 else f"seeds{seeds[0]}-{seeds[-1]}"
    path = outdir / f"baselines_{tag}{'_shock' if args.shock else ''}.csv"
    commit = git_commit()
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["policy"] + [c for c, _, _ in KEYS] + (["d_pct_late", "d_late_days"] if args.shock else [])
                   + ["seeds", "shock", "commit"])
        for name, m in avg.items():
            vals = [round(m[k], nd) if nd else round(m[k]) for _, k, nd in KEYS]
            extra = [round(delta[name][0], 1), round(delta[name][1], 2)] if args.shock else []
            w.writerow([name] + vals + extra + [f"{seeds[0]}-{seeds[-1]}" if n > 1 else seeds[0], args.shock, commit])
    print(f"\nwritten {path}  (commit {commit})")
    if args.shock and n == 1:
        print("late batches by workshop (shock run):")
        for r in last_rows:
            print(f"  {r['policy']:<24} {r['late_by_workshop']}")


if __name__ == "__main__":
    main()
