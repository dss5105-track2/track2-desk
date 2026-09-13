"""Run the untouched simulator on a scenario directory produced by make_scenario.py.

    python scenarios/run_scenario.py scenarios/out/due_7_14 --seeds 5105 1 2 3
    python scenarios/run_scenario.py scenarios/out/due_7_14 --shock --force-target W6

`--force-target` monkeypatches the shock draw so the closed workshop can be chosen
explicitly (the official seed always closes W2). Say so in the report.
"""
import argparse
import csv
import random as _random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "harness"))

import simulate  # noqa: E402
from simulate import random_choice, greedy_biggest, cheapest  # noqa: E402
from kernel.allocator import Allocator, earliest_finish, OBJECTIVES  # noqa: E402
from run_baselines import summarise  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("scenario_dir")
    ap.add_argument("--seeds", type=int, nargs="+", default=[5105])
    ap.add_argument("--shock", action="store_true")
    ap.add_argument("--force-target", default=None)
    args = ap.parse_args()

    simulate.DATA = Path(args.scenario_dir).resolve() / "data"   # load_* read DATA at call time
    rows = []
    for seed in args.seeds:
        sim = simulate.Simulator(shock=args.shock, seed=seed)
        if args.shock and args.force_target:
            # first draw of the run's RNG is the target; pin it by wrapping Random.choice
            forced = args.force_target
            orig_choice = _random.Random.choice
            def choice(self, seq, _forced=forced, _orig=orig_choice):
                if forced in seq and all(isinstance(x, str) and x.startswith("W") for x in seq):
                    _orig(self, seq)          # consume the draw so the defect stream is unchanged
                    return _forced
                return _orig(self, seq)
            _random.Random.choice = choice
        try:
            pols = [("random", random_choice), ("greedy_biggest", greedy_biggest), ("cheapest", cheapest),
                    ("earliest_finish", earliest_finish)] + [(f"cfg:{o}", Allocator(o)) for o in OBJECTIVES]
            for name, pol in pols:
                r = summarise(name, sim.run(pol, name)); r["seed"] = seed; rows.append(r)
            sim.report()
        finally:
            if args.shock and args.force_target:
                _random.Random.choice = orig_choice

    out = Path(args.scenario_dir) / f"results_{'shock_' if args.shock else ''}{'_'.join(map(str, args.seeds))}.csv"
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["policy", "seed", "mean_days", "p90_days", "pct_late", "pct_defect", "cost", "max_share"])
        w.writeheader()
        for r in rows:
            w.writerow({k: r[k] for k in w.fieldnames})
    print(f"written {out}")


if __name__ == "__main__":
    main()
