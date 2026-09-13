"""Write a scenario data directory from a JSON config. The official data is never modified.

    python scenarios/make_scenario.py scenarios/due_7_14.json
"""
import csv
import json
import random
import shutil
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OFFICIAL = ROOT / "data"


def load_orders_rows():
    with open(OFFICIAL / "orders.csv", encoding="utf-8") as f:
        return list(csv.DictReader(f)), f.name


def rescale_slack(rows, cfg, rng):
    lo, hi = cfg["min_slack_days"], cfg["max_slack_days"]
    slacks = [(date.fromisoformat(r["due_date"]) - date.fromisoformat(r["order_date"])).days for r in rows]
    smin, smax = min(slacks), max(slacks)
    out = []
    for r, s in zip(rows, slacks):
        # linear map [smin, smax] -> [lo, hi], keeping the relative urgency of each order
        new_slack = lo + (s - smin) * (hi - lo) / max(1, (smax - smin))
        r2 = dict(r)
        r2["due_date"] = (date.fromisoformat(r["order_date"]) + timedelta(days=round(new_slack))).isoformat()
        out.append(r2)
    return out


def add_orders(rows, cfg, rng):
    pool = [r for r in rows if r["category"] == cfg["category"]]
    d0 = min(date.fromisoformat(r["order_date"]) for r in rows)
    d1 = max(date.fromisoformat(r["order_date"]) for r in rows)
    span = (d1 - d0).days
    existing = {r["order_id"] for r in rows}
    out = list(rows)
    n = 0
    while n < cfg["extra_orders"]:
        src = rng.choice(pool)
        oid = f"ORD-{200 + n:03d}"
        if oid in existing:
            n += 1
            continue
        od = d0 + timedelta(days=rng.randint(0, span))
        slack = (date.fromisoformat(src["due_date"]) - date.fromisoformat(src["order_date"])).days
        r2 = dict(src)
        r2.update({"order_id": oid, "order_date": od.isoformat(), "due_date": (od + timedelta(days=slack)).isoformat(),
                   "status": "IN_PROGRESS", "current_stage": "KNITTING", "last_activity_date": od.isoformat(),
                   "completed_date": "", "days_late": ""})
        out.append(r2)
        n += 1
    return out


TRANSFORMS = {"rescale_slack": rescale_slack, "add_orders": add_orders}


def main(cfg_path):
    cfg = json.loads(Path(cfg_path).read_text(encoding="utf-8"))
    rng = random.Random(cfg.get("seed", 0))
    rows, _ = load_orders_rows()
    new_rows = TRANSFORMS[cfg["transform"]](rows, cfg, rng)
    outdir = ROOT / "scenarios" / "out" / cfg["name"] / "data"
    outdir.mkdir(parents=True, exist_ok=True)
    shutil.copy(OFFICIAL / "workshops.csv", outdir / "workshops.csv")
    with open(outdir / "orders.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(new_rows)
    (outdir.parent / "scenario.json").write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    print(f"wrote {outdir} ({len(new_rows)} orders)")


if __name__ == "__main__":
    main(sys.argv[1])
