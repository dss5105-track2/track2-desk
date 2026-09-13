"""Generate the numeric part of the gold answers by replaying the protocol with the kernel.

    python eval/compute_gold_facts.py                       # protocol as frozen (R12 ban is session-wide)
    python eval/compute_gold_facts.py --ban-scope request   # sensitivity: ban applies to R12 only

Inputs:  language/requests_gold.json   (manual parses)
         eval/gold_labels.csv          (behaviour labels; falls back to eval/draft/gold_labels_draft.csv)
Output:  eval/gold_facts[_<scope>].csv  one row per request with candidates, recommendation and numbers

Rules (eval/protocol.md):
  * send date is 2026-04-01 for every request; requests processed in timestamp order
  * session-scoped exclusions apply to every later request
  * chat pieces / due date are used when given, otherwise the orders.csv values
  * only internal_subtype == allocate commits to the ledger
Every number that later appears in a gold explanation must come from this file.
"""
import argparse
import csv
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from kernel.register import load_workshops, eligibility_table  # noqa: E402
from kernel.estimator import estimate_all, split_estimate  # noqa: E402
from kernel.allocator import Allocator  # noqa: E402
from kernel.ledger import Ledger  # noqa: E402
from kernel.orders import load_orders, state_checks, TODAY  # noqa: E402


def load_labels():
    for p in (ROOT / "eval" / "gold_labels.csv", ROOT / "eval" / "draft" / "gold_labels_draft.csv"):
        if p.exists():
            with open(p, encoding="utf-8") as f:
                return {r["request_id"]: r for r in csv.DictReader(f)}, p
    raise SystemExit("no gold labels file found")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ban-scope", choices=["session", "request"], default="session")
    args = ap.parse_args()

    W = load_workshops(); O = load_orders()
    reqs = json.loads((ROOT / "language" / "requests_gold.json").read_text(encoding="utf-8"))
    reqs.sort(key=lambda r: r["timestamp"])
    labels, label_path = load_labels()
    L = Ledger(W, TODAY)
    alloc = Allocator("lateness")
    session_excl = {}          # workshop_id -> (requester, request_id)
    rows = []

    for r in reqs:
        rid = r["request_id"]
        lab = labels.get(rid, {})
        sub = lab.get("internal_subtype", "")
        o = O.get(r["order_id"]) if r["order_id"] else None
        excl = set(r["excluded_workshops"]) | set(session_excl)
        row = {"request_id": rid, "timestamp": r["timestamp"], "official_behaviour": lab.get("official_behaviour", ""),
               "internal_subtype": sub, "order_id": r["order_id"] or "", "state_flags": " | ".join(state_checks(o, TODAY, L)) if r["order_id"] else "",
               "active_exclusions": ",".join(sorted(excl)), "recommended": "", "promised_date": "", "finish_days": "",
               "late_days": "", "cost": "", "on_time_candidates": "", "all_candidates": "", "forced_verdict": "", "committed": ""}

        if o is not None and sub in {"allocate", "no_on_time_option", "ineligible_suggestion"}:
            pieces = r["pieces"] or o.pieces
            due = date.fromisoformat(r["due_date"]) if r["due_date"] else o.due_date
            batch = {"order_id": o.order_id, "category": o.category, "pieces": pieces, "sent_date": TODAY, "due_date": due}
            if r["forced_workshop"]:
                fw = r["forced_workshop"]
                verdict = next(x for x in eligibility_table(W, o.category, pieces) if x["workshop_id"] == fw)
                row["forced_verdict"] = f"{fw} {verdict['reason']}"
            pref = r["preference"] if r["preference"] in ("fastest", "cheapest_on_time", "lowest_defect") else None
            ranked = alloc.rank(batch, W, L.queues(), exclude=excl, preference=pref)
            ests = [x["estimate"] for x in ranked]
            row["all_candidates"] = "; ".join(f"{e.workshop_id} {e.finish_days:.2f}d {e.promised_date} late{e.late_days}" for e in ests)
            row["on_time_candidates"] = ",".join(e.workshop_id for e in ests if e.on_time)
            if ests:
                best = ests[0]
                row.update(recommended=best.workshop_id, promised_date=best.promised_date.isoformat(),
                           finish_days=f"{best.finish_days:.2f}", late_days=best.late_days, cost=f"{best.cost:.0f}")
            if r["preference"] == "split":
                s = split_estimate(W, o.category, pieces, L.queues(), TODAY, due, exclude=excl)
                row["all_candidates"] += f" || split gain {s.get('gain_days', 0):.2f}d plan {s.get('plan')}"
            if sub == "allocate" and ests:
                rec = L.commit(request_id=rid, order_id=o.order_id, workshop_id=ests[0].workshop_id, category=o.category,
                               pieces=pieces, sent_date=TODAY, due_date=due, requester=r["requester"], confirmed_by="gold",
                               reason="gold replay", constraints={"exclude": sorted(excl)})
                row["committed"] = f"{rec['audit_id']} queue {rec['queue_before']:.2f}->{rec['queue_after']:.2f}"

        if r["constraint_scope"] == "session" and args.ban_scope == "session":
            for wid in r["excluded_workshops"]:
                session_excl[wid] = (r["requester"], rid)
        rows.append(row)

    out = ROOT / "eval" / f"gold_facts{'' if args.ban_scope == 'session' else '_' + args.ban_scope}.csv"
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)
    for row in rows:
        print(f"{row['request_id']} {row['internal_subtype']:<22} {row['recommended']:<3} {row['promised_date']:<10} "
              f"late={row['late_days']!s:<3} excl={row['active_exclusions']:<6} {row['committed']}")
    print(f"\nlabels from {label_path}\nwritten {out}")


if __name__ == "__main__":
    main()
