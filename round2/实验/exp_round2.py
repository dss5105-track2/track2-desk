"""Round-2 results on the official v3 data with the code in track2-desk-优化版 (branch claude/round2).

    python 实验/exp_round2.py     ->  ../02_分配器/official_*.csv, promise_*.csv, inbox_in_order.csv
"""
from __future__ import annotations

import csv
import random
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
REPO = HERE.parent / "track2-desk-优化版"
if not REPO.exists():          # inside the repo, this folder is round2/; the code is the repo root
    REPO = HERE.parent.parent
OUT = HERE.parent / "02_分配器"
OUT.mkdir(exist_ok=True)
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(REPO / "harness"))

from simulate import Simulator, random_choice, greedy_biggest, cheapest  # noqa: E402
from kernel.allocator import Allocator, earliest_finish  # noqa: E402
from desk.pipeline import Desk, inbox_lines  # noqa: E402

SEEDS = list(range(5105, 5115))
METRICS = ["% late", "late days", "mean days", "p90 days", "% def pcs", "max share", "cost"]
COMMIT = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=REPO, text=True).strip()
DIRTY = bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=REPO, text=True).strip())


def policies():
    return [("random", random_choice), ("greedy_biggest", greedy_biggest), ("cheapest", cheapest), ("earliest_finish", earliest_finish),
            ("lateness_v1", Allocator("lateness_v1")), ("lateness", Allocator("lateness")), ("use_slack", Allocator("use_slack")),
            ("hybrid", Allocator("hybrid")), ("defects", Allocator("defects")), ("fairness", Allocator("fairness")), ("cost", Allocator("cost"))]


def run(sim, name, pol):
    if hasattr(pol, "reset"):
        pol.reset()
    return sim.run(pol, name)


def official():
    per = {False: {}, True: {}}
    for shock in (False, True):
        for seed in SEEDS:
            sim = Simulator(shock=shock, seed=seed)
            for name, pol in policies():
                per[shock].setdefault(name, []).append(Simulator.metrics(run(sim, name, pol)))
    rows = []
    for name, _ in policies():
        n, s = per[False][name], per[True][name]
        mean = lambda ms, k: sum(m[k] for m in ms) / len(ms)
        rows.append([name] + [round(mean(n, k), 3) for k in METRICS] + [round(mean(s, "% late"), 3), round(mean(s, "late days"), 3),
                    round(mean(s, "% late") - mean(n, "% late"), 3), round(mean(s, "late days") - mean(n, "late days"), 3)])
    with open(OUT / "official_10seeds.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["policy", "pct_late", "late_days", "mean_days", "p90_days", "pct_def_pcs", "max_share", "cost",
                    "shock_pct_late", "shock_late_days", "shock_minus_normal_pct_late", "shock_minus_normal_late_days"])
        w.writerows(rows)
    print(f"{'policy':<18}{'% late':>8}{'late d':>8}{'mean':>7}{'p90':>7}{'def%':>7}{'share':>7}{'cost':>9} | shock {'% late':>7}{'late d':>8}")
    for r in rows:
        print(f"{r[0]:<18}{r[1]:>8.2f}{r[2]:>8.3f}{r[3]:>7.1f}{r[4]:>7.1f}{r[5]:>7.2f}{r[6]:>7.1f}{r[7]:>9.0f} | {r[8]:>13.2f}{r[9]:>8.3f}")


class Recorder:
    """Records the dates the allocator's own estimate would have promised."""

    def __init__(self, inner):
        self.inner, self.rows = inner, []

    def reset(self):
        self.rows = []
        self.inner.reset()

    def __call__(self, batch, workshops, queues):
        wid = self.inner(batch, workshops, queues)
        w = workshops[wid]
        work = batch["pieces"] / w.capacity
        q = queues[wid]
        self.rows.append({"wid": wid, "expected": q + work * (1 + 0.5 * w.defect_rate) + w.lead_days, "worst": q + 1.5 * work + w.lead_days})
        return wid


def promises():
    out = []
    for obj in ("lateness_v1", "lateness"):
        for shock in (False, True):
            kept_e = kept_w = n = 0
            gap = []
            for seed in SEEDS:
                sim = Simulator(shock=shock, seed=seed)
                rec = Recorder(Allocator(obj))
                res = run(sim, obj, rec)
                for r, o in zip(rec.rows, res):
                    n += 1
                    kept_e += round(o["turnaround"]) <= round(r["expected"])
                    kept_w += round(o["turnaround"]) <= round(r["worst"])
                    gap.append(round(r["worst"]) - round(r["expected"]))
            out.append([obj, shock, n, round(100 * kept_e / n, 2), round(100 * kept_w / n, 2), round(sum(gap) / len(gap), 2)])
    with open(OUT / "promise_two_dates.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["objective", "shock", "batches", "expected_date_kept_pct", "date_if_reworked_kept_pct", "mean_days_between_the_two_dates"])
        w.writerows(out)
    for r in out:
        print("promise", r)


def inbox():
    meet = ["R04", "R06", "R07", "R09", "R12", "R16", "R17", "R21", "R22", "R23", "R25", "R26", "R27"]
    rows = []
    for obj in ("lateness_v1", "lateness", "use_slack", "hybrid"):
        d = Desk(objective=obj)
        for ln in inbox_lines():
            d.handle(ln)
        late = []
        for r in meet:
            dec = d.decisions[r]
            if dec["subtype"] != "allocate":
                c = next(c for c in dec["candidates"] if c["workshop_id"] == dec["recommended"])
                late.append(f"{r} +{c['late_days']}d")
        rows.append([obj, 13 - len(late), "; ".join(late), all(x["number_check"]["ok"] for x in d.decisions.values()),
                     " ".join(f"{x['request_id']}>{x['workshop_id']}" for x in d.ledger.records)])
    with open(OUT / "inbox_in_order.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["objective", "meetable_requests_on_time_of_13", "late", "all_numbers_traced", "ledger"])
        w.writerows(rows)
    for r in rows:
        print("inbox", r[:4])


if __name__ == "__main__":
    print("repo", COMMIT, "(+ uncommitted changes)" if DIRTY else "")
    official()
    promises()
    inbox()
    (OUT / "RUN_INFO.txt").write_text(f"repo: track2-desk-优化版, branch claude/round2, commit {COMMIT}{' + uncommitted changes' if DIRTY else ''}\n"
                                      f"seeds: {SEEDS[0]}..{SEEDS[-1]}\nsimulator: harness/simulate.py v3 (untouched)\n", encoding="utf-8")
