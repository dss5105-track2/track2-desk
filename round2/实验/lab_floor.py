"""Two exact checks by exhaustive search (hindsight, no policy could do better):

 A. Simulator, official 120 orders, no defects: the fewest accessory orders that can be late when the
    three accessory-capable shops (W2, W4, W6) are used for accessories only. A lower bound on late
    orders for ANY allocator, because TOPS work on those shops can only make it worse.
 B. Chat inbox processed in order (morning of 1 April): can all 13 'meetable' requests be on time,
    given Boss's QuickStitch ban from R12 on and each requester's own constraint?

    python 实验/lab_floor.py
"""
from __future__ import annotations

import csv
import sys
from datetime import date, timedelta
from pathlib import Path

sys.dont_write_bytecode = True
sys.setrecursionlimit(10000)
HERE = Path(__file__).resolve().parent
DATA = HERE.parent / "track2-desk-优化版" / "data"
if not DATA.exists():          # inside the repo, this folder is round2/; the data is in the repo root
    DATA = HERE.parent.parent / "data"
W = {r["workshop_id"]: r for r in csv.DictReader(open(DATA / "workshops.csv", encoding="utf-8"))}
ORD = list(csv.DictReader(open(DATA / "orders.csv", encoding="utf-8")))
cap = {k: float(v["capacity_pieces_per_day"]) for k, v in W.items()}
lead = {k: int(v["pickup_lead_days"]) for k, v in W.items()}
q0 = {k: float(v["current_queue_days"]) for k, v in W.items()}
dfr = {k: float(v["defect_rate"]) for k, v in W.items()}


# ------------------------------------------------------------------ A. accessories lower bound in the simulator
def check_a():
    acc = sorted([o for o in ORD if o["category"] == "ACCESSORIES"], key=lambda o: o["order_date"])
    day0 = min(date.fromisoformat(o["order_date"]) for o in ORD)
    jobs = [((date.fromisoformat(o["order_date"]) - day0).days, int(o["pieces"]), (date.fromisoformat(o["due_date"]) - day0).days, o["order_id"]) for o in acc]
    shops = ["W2", "W4", "W6"]
    best = {"late": len(jobs) + 1, "assign": None}
    seen = [dict() for _ in jobs]          # per depth: pareto set of (late, free times)
    nodes = [0]

    def dominated(i, late, free):
        key = tuple(round(x, 3) for x in free)
        for (l2, f2) in seen[i].get("s", []):
            if l2 <= late and all(a <= b + 1e-9 for a, b in zip(f2, free)):
                return True
        seen[i].setdefault("s", []).append((late, free))
        if len(seen[i]["s"]) > 4000:       # keep the list bounded: drop entries dominated by the new one
            seen[i]["s"] = [(l2, f2) for (l2, f2) in seen[i]["s"] if not (late <= l2 and all(a <= b + 1e-9 for a, b in zip(free, f2)))] + [(late, free)]
        return False

    def dfs(i, free, late, assign):
        nodes[0] += 1
        if late >= best["late"]:
            return
        if i == len(jobs):
            best["late"], best["assign"] = late, list(assign)
            return
        if dominated(i, late, free):
            return
        day, pcs, due, oid = jobs[i]
        opts = []
        for k, s in enumerate(shops):
            start = max(day, free[k])
            fin = start + pcs / cap[s]
            done = round(fin + lead[s])                 # simulator: done_date = day0 + round(done_day)
            opts.append((done > due, fin, k))
        for is_late, fin, k in sorted(opts):
            nf = list(free); nf[k] = fin
            dfs(i + 1, tuple(nf), late + int(is_late), assign + [shops[k]])

    dfs(0, tuple(q0[s] for s in shops), 0, [])
    print(f"A. accessory orders: {len(jobs)}; fewest late with hindsight and no defects: {best['late']}  (search nodes {nodes[0]})")
    if best["assign"]:
        late_ids = []
        free = {s: q0[s] for s in shops}
        for (day, pcs, due, oid), s in zip(jobs, best["assign"]):
            fin = max(day, free[s]) + pcs / cap[s]; free[s] = fin
            if round(fin + lead[s]) > due:
                late_ids.append(oid)
        print("   late in the best assignment:", late_ids)
    return best["late"]


# ------------------------------------------------------------------ B. inbox in order
INBOX = [  # (request, order, excluded by the requester, preference) for the 13 meetable requests, in time order
    ("R04", "ORD-041", [], None), ("R06", "ORD-096", [], None), ("R07", "ORD-063", [], None), ("R09", "ORD-045", [], "fastest"),
    ("R12", "ORD-053", ["W1"], None), ("R16", "ORD-024", ["W1"], None), ("R17", "ORD-017", ["W1"], None), ("R21", "ORD-081", ["W1"], "cheapest"),
    ("R22", "ORD-040", ["W1"], None), ("R23", "ORD-005", ["W1"], None), ("R25", "ORD-109", ["W1", "W3"], None), ("R26", "ORD-010", ["W1"], None),
    ("R27", "ORD-095", ["W1"], "lowest_defect"),
]
TODAY = date(2026, 4, 1)
OB = {o["order_id"]: o for o in ORD}


def elig(wid, cat, pcs):
    w = W[wid]
    return w["status"] == "ACTIVE" and cat in w["makes"].split("+") and not (w["max_batch_pieces"] and pcs > int(w["max_batch_pieces"]))


def check_b(respect_preferences: bool):
    best = {"on": -1, "assign": None}

    def dfs(i, queue, on, assign):
        if on + (len(INBOX) - i) <= best["on"]:
            return
        if i == len(INBOX):
            best["on"], best["assign"] = on, list(assign)
            return
        rid, oid, excl, pref = INBOX[i]
        o = OB[oid]; pcs = int(o["pieces"]); due = date.fromisoformat(o["due_date"])
        cands = []
        for wid in W:
            if elig(wid, o["category"], pcs) and wid not in excl:
                work = pcs / cap[wid]; rew = 0.5 * dfr[wid] * work
                fin = queue[wid] + work + rew + lead[wid]
                ok = TODAY + timedelta(days=round(fin)) <= due
                cands.append((wid, ok, fin, work + rew, pcs * float(W[wid]["cost_per_piece"]), dfr[wid]))
        on_time = [c for c in cands if c[1]]
        if respect_preferences and pref and on_time:      # the requester's preference fixes the pick among on-time shops
            keyf = {"fastest": lambda c: c[2], "cheapest": lambda c: (c[4], c[2]), "lowest_defect": lambda c: (c[5], c[2])}[pref]
            on_time = [min(on_time, key=keyf)]
        for c in on_time:
            q2 = dict(queue); q2[c[0]] += c[3]
            dfs(i + 1, q2, on + 1, assign + [(rid, c[0])])
        dfs(i + 1, queue, on, assign + [(rid, None)])      # leave it late: nothing is committed

    dfs(0, dict(q0), 0, [])
    print(f"B. inbox in order, preferences {'respected' if respect_preferences else 'ignored'}: at most {best['on']} of {len(INBOX)} on time")
    print("   one best assignment:", best["assign"])


if __name__ == "__main__":
    check_a()
    check_b(True)
    check_b(False)
