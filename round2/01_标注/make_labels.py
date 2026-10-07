"""Proposed gold labels for the 30 v3 requests, with the facts recomputed independently of the system.

    python 01_标注/make_labels.py

This script does NOT import desk/ or kernel/. It reads the three data files directly, applies the
labelling rules in 标注规则_v3.md to the reading of each message recorded in READING below, and
recomputes every number (eligibility, estimates, dates) from the formula in the protocol:

    finish days = queue + pieces/capacity + 0.5 * defect_rate * pieces/capacity + pickup_lead_days
    promised    = 2026-04-01 + round(finish days)          on time  <=>  promised <= due date

Outputs (same folder): gold_labels_v3_proposed.csv, 分类_Claude.csv (same columns as the classmates'
template), facts_independent.json.
"""
from __future__ import annotations

import csv
import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
DATA = HERE.parent / "track2-desk-优化版" / "data"
if not DATA.exists():          # inside the repo, this folder is round2/; the data is in the repo root
    DATA = HERE.parent.parent / "data"
TODAY = date(2026, 4, 1)

W = {r["workshop_id"]: r for r in csv.DictReader(open(DATA / "workshops.csv", encoding="utf-8"))}
O = {r["order_id"]: r for r in csv.DictReader(open(DATA / "orders.csv", encoding="utf-8"))}
NAME = {k: v["name"] for k, v in W.items()}
REQ = {}
for line in open(DATA / "dispatch_requests.txt", encoding="utf-8"):
    m = re.match(r"(R\d\d) \[(\d\d:\d\d)\] ([^:]+): (.*)$", line.rstrip("\n"))
    if m:
        REQ[m.group(1)] = {"time": m.group(2), "who": m.group(3), "text": m.group(4)}

# ----------------------------------------------------------------------------------------------
# READING: what each message says, read by the labeller (not by the system's parser).
#   order      order id named in the message (None if none)
#   forced     workshop the requester wants            excl   workshops the requester rules out
#   scope      "session" if the exclusion is for "this week" (applies to later requests)
#   pref       fastest | cheapest_on_time | lowest_defect | split | None
#   kind       the instructor's seven kinds (data_dictionary.md)
#   behaviour / subtype / also   label, and a second subtype that is also acceptable
#   rule       which rule in 标注规则_v3.md decides it
# ----------------------------------------------------------------------------------------------
READING = {
    "R01": dict(order=None, kind="missing", behaviour="clarify", subtype="missing_fields", also="ambiguous_reference", rule="C2",
                lookup=dict(customer="Harbor Knits", product="Scarf")),
    "R02": dict(order=None, kind="unanswerable", behaviour="decline-to-answer", subtype="not_in_data", rule="D1"),
    "R03": dict(order=None, kind="ambiguous", behaviour="clarify", subtype="ambiguous_reference", rule="C1", lookup=dict(customer="TrendCart")),
    "R04": dict(order="ORD-041", kind="meetable", behaviour="extract", subtype="allocate", rule="E1"),
    "R05": dict(order="ORD-066", kind="missing", behaviour="clarify", subtype="missing_fields", rule="C3"),
    "R06": dict(order="ORD-096", kind="meetable", behaviour="extract", subtype="allocate", rule="E1"),
    "R07": dict(order="ORD-063", kind="meetable", behaviour="extract", subtype="allocate", rule="E1"),
    "R08": dict(order="ORD-073", forced="W8", kind="ineligible", behaviour="refuse", subtype="ineligible_suggestion", rule="F1"),
    "R09": dict(order="ORD-045", pref="fastest", kind="constraint", behaviour="extract", subtype="allocate", rule="E2"),
    "R10": dict(order=None, kind="missing", behaviour="clarify", subtype="missing_fields", rule="C3", lookup=dict(customer="Loom & Leaf")),
    "R11": dict(order="ORD-008", forced="W7", kind="ineligible", behaviour="refuse", subtype="ineligible_suggestion", rule="F1"),
    "R12": dict(order="ORD-053", excl=["W1"], scope="session", by="Boss", kind="constraint", behaviour="extract", subtype="allocate", rule="E3"),
    "R13": dict(order="ORD-120", info=True, kind="unanswerable", behaviour="decline-to-answer", subtype="not_in_data", rule="D1"),
    "R14": dict(order="ORD-103", forced="W1", kind="ineligible", behaviour="refuse", subtype="ineligible_suggestion", rule="F2"),
    "R15": dict(order=None, kind="ambiguous", behaviour="clarify", subtype="ambiguous_reference", also="missing_fields", rule="C1",
                lookup=dict(customer="Loom & Leaf")),
    "R16": dict(order="ORD-024", kind="meetable", behaviour="extract", subtype="allocate", rule="E1"),
    "R17": dict(order="ORD-017", kind="meetable", behaviour="extract", subtype="allocate", rule="E1"),
    "R18": dict(order="ORD-999", info=True, kind="unanswerable", behaviour="decline-to-answer", subtype="not_in_data", rule="D2"),
    "R19": dict(order=None, pref="fastest", kind="ambiguous", behaviour="clarify", subtype="ambiguous_reference", rule="C1", lookup=dict(last_week=True)),
    "R20": dict(order="ORD-103", kind="impossible", behaviour="extract", subtype="no_on_time_option", rule="E4"),
    "R21": dict(order="ORD-081", pref="cheapest_on_time", kind="constraint", behaviour="extract", subtype="allocate", rule="E2"),
    "R22": dict(order="ORD-040", kind="meetable", behaviour="extract", subtype="allocate", rule="E1"),
    "R23": dict(order="ORD-005", pref="split", kind="constraint", behaviour="extract", subtype="allocate", rule="E5"),
    "R24": dict(order="ORD-015", forced="W4", kind="ineligible", behaviour="refuse", subtype="ineligible_suggestion", rule="F1"),
    "R25": dict(order="ORD-109", excl=["W3"], scope="request", by="Mei", kind="constraint", behaviour="extract", subtype="allocate", rule="E3"),
    "R26": dict(order="ORD-010", kind="meetable", behaviour="extract", subtype="allocate", rule="E1"),
    "R27": dict(order="ORD-095", pref="lowest_defect", kind="constraint", behaviour="extract", subtype="allocate", rule="E2"),
    "R28": dict(order="ORD-002", kind="impossible", behaviour="extract", subtype="no_on_time_option", rule="E4"),
    "R29": dict(order=None, kind="ambiguous", behaviour="clarify", subtype="ambiguous_reference", rule="C1", lookup=dict(product="Vest")),
    "R30": dict(order="ORD-099", kind="impossible", behaviour="extract", subtype="no_on_time_option", rule="E4"),
}
KIND_ZH = {"meetable": "完整且能按时", "impossible": "完整但不可能按时", "constraint": "带约束", "ambiguous": "指代不清",
           "missing": "缺数字或日期", "ineligible": "点名的车间接不了", "unanswerable": "数据里没有答案"}


# ------------------------------------------------------------------ the three questions and the estimate
def eligibility(wid, cat, pcs):
    w = W[wid]
    if w["status"] != "ACTIVE":
        return False, f"status {w['status']}"
    if cat not in w["makes"].split("+"):
        return False, f"cannot make {cat} (makes {w['makes']})"
    if w["max_batch_pieces"] and pcs > int(w["max_batch_pieces"]):
        return False, f"batch {pcs} over its {w['max_batch_pieces']}-piece limit"
    return True, "eligible"


def estimate(wid, pcs, queue, due):
    w = W[wid]
    work = pcs / float(w["capacity_pieces_per_day"])
    rework = 0.5 * float(w["defect_rate"]) * work
    finish = queue + work + rework + int(w["pickup_lead_days"])
    promised = TODAY + timedelta(days=round(finish))
    return dict(workshop=wid, name=NAME[wid], finish=round(finish, 2), promised=promised.isoformat(), late=max(0, (promised - due).days),
                on_time=promised <= due, cost=round(pcs * float(w["cost_per_piece"])), defect=float(w["defect_rate"]), add_queue=work + rework)


def candidates(order, queues, exclude):
    cat, pcs, due = order["category"], int(order["pieces"]), date.fromisoformat(order["due_date"])
    out = []
    for wid in W:
        ok, _ = eligibility(wid, cat, pcs)
        if ok and wid not in exclude:
            out.append(estimate(wid, pcs, queues[wid], due))
    return sorted(out, key=lambda e: e["finish"])


def pick(cands, pref):
    on = [c for c in cands if c["on_time"]]
    if not on:
        return cands[0] if cands else None
    if pref == "cheapest_on_time":
        return min(on, key=lambda c: (c["cost"], c["finish"]))
    if pref == "lowest_defect":
        return min(on, key=lambda c: (c["defect"], c["finish"]))
    return on[0]            # none / fastest / split: earliest finish


def lookup_orders(spec):
    rows = [o for o in O.values() if o["status"] == "IN_PROGRESS"]
    if spec.get("customer"):
        rows = [o for o in rows if o["customer"] == spec["customer"]]
    if spec.get("product"):
        rows = [o for o in rows if o["product"] == spec["product"]]
    if spec.get("last_week"):     # 1 April 2026 is a Wednesday; "last week" = Mon 23 to Sun 29 March
        rows = [o for o in rows if date(2026, 3, 23) <= date.fromisoformat(o["order_date"]) <= date(2026, 3, 29)]
    return sorted(rows, key=lambda o: (-int(o["pieces"]), o["order_id"]))


def replay(sequential: bool, REQ=None, READING=None):
    """Per request: the facts with morning queues (sequential=False) or with a ledger that grows with
    every on-time allocation (sequential=True). Session exclusions carry over in both."""
    REQ = REQ if REQ is not None else globals()["REQ"]
    READING = READING if READING is not None else globals()["READING"]
    queues = {wid: float(w["current_queue_days"]) for wid, w in W.items()}
    session = {}
    out = {}
    for rid in sorted(REQ):
        rd = READING[rid]
        f = dict(session_excluded=sorted(session))
        order = O.get(rd["order"]) if rd.get("order") else None
        if rd.get("lookup"):
            f["matching_orders"] = [f"{o['order_id']} {o['customer']} {o['product']} {o['pieces']} due {o['due_date']}" for o in lookup_orders(rd["lookup"])]
        if rd.get("order") and order is None:
            f["order_missing"] = True
        if order is not None:
            f["order_status"] = order["status"]
            f["already_committed_by"] = next((r for r, x in out.items() if x.get("committed") and READING[r].get("order") == rd["order"]), None)
        if order is not None and not rd.get("info") and rd["behaviour"] != "clarify":
            excl = set(session) | set(rd.get("excl", []))
            cat, pcs, due = order["category"], int(order["pieces"]), date.fromisoformat(order["due_date"])
            cands = candidates(order, queues, excl)
            f.update(order=f"{order['order_id']} {order['customer']} {order['product']} {cat} {pcs} pcs due {due} stage {order['current_stage']}",
                     candidates=cands, on_time=[c["workshop"] for c in cands if c["on_time"]],
                     ineligible={wid: eligibility(wid, cat, pcs)[1] for wid in W if not eligibility(wid, cat, pcs)[0]})
            if rd.get("forced"):
                ok, why = eligibility(rd["forced"], cat, pcs)
                f["forced"] = dict(workshop=rd["forced"], eligible=ok, reason=why)
            best = pick(cands, rd.get("pref"))
            f["reference"] = best
            if sequential and best and best["on_time"] and rd["behaviour"] == "extract":
                queues[best["workshop"]] += best["add_queue"]
                f["committed"] = best["workshop"]
        if rd.get("scope") == "session":
            for wid in rd["excl"]:
                session[wid] = dict(by=rd["by"], source=rid)
        out[rid] = f
    return out


# ------------------------------------------------------------------ what the reply must contain
def must_do(rid, rd, f):
    ref = f.get("reference")
    if rd["subtype"] == "not_in_data":
        return {"R02": "say dispatch history is not held (data starts 2026-01-01, no workshop assignments recorded); do not name a workshop",
                "R13": "say no customer quote is held; cost_per_piece is what workshops charge us; do not give a figure",
                "R18": "say ORD-999 is not in the order book; ask to check the number; do not report progress"}[rid]
    if rd["behaviour"] == "clarify":
        n = len(f.get("matching_orders", []))
        return {"R01": f"ask the quantity ('usual quantities' is not defined in the data) and which of the {n} Harbor Knits scarf orders in progress is meant; do not allocate",
                "R03": f"list the {n} TrendCart orders in progress and ask which; do not guess",
                "R05": "ask for the confirmed new due date before estimating; may show candidates, must not book",
                "R10": "ask for order number, product, pieces and due date; do not book capacity",
                "R15": f"ask which Loom & Leaf order ({n} in progress) or whether this is the new rush from R10; do not guess",
                "R19": f"list last week's in-progress orders ({n}; largest first) and ask which; note 'quickest' as the preference",
                "R29": f"list the {n} vest orders in progress and ask which; do not guess"}[rid]
    if rd["behaviour"] == "refuse":
        why = f["forced"]["reason"]
        alt = (f"alternative {ref['name']} back {ref['promised']} on time" if ref and ref["on_time"]
               else f"no on-time alternative: earliest {ref['name']} back {ref['promised']}, {ref['late']} days late; lay out options")
        return f"refuse {NAME[rd['forced']]}: {why}; {alt}"
    if rd["subtype"] == "no_on_time_option":
        return (f"say no workshop makes the date, with the numbers; earliest {ref['name']} back {ref['promised']}, {ref['late']} days late; "
                "options: split, accept lateness, renegotiate, escalate; do not allocate silently")
    extra = {"fastest": " (fastest turnaround asked)", "cheapest_on_time": " (cheapest that still makes the date)", "lowest_defect": " (lowest defect rate among on-time)",
             "split": " (answer the split question: a single shop is on time, so no split needed)"}.get(rd.get("pref"), "")
    ex = ""
    if rd.get("excl"):
        ex = f"; honour and record the exclusion of {', '.join(NAME[w] for w in rd['excl'])} by {rd['by']}" + (" for the week" if rd["scope"] == "session" else "")
    return f"recommend {ref['name']} back {ref['promised']} on time{extra}{ex}; show candidates; commit only after confirmation"


if __name__ == "__main__":
    morning, seq = replay(False), replay(True)
    # sanity: what the message states must agree with the order book
    mism = []
    for rid, rd in READING.items():
        if rd.get("order") and rd["order"] in O:
            o, t = O[rd["order"]], REQ[rid]["text"]
            m = re.search(r"(\d[\d,]*) (\w+)", t.replace(rd["order"], ""))
            nums = [int(x.replace(",", "")) for x in re.findall(r"\b(\d{3,4})\b", t.replace(rd["order"], ""))]
            if nums and int(o["pieces"]) not in nums:
                mism.append((rid, "pieces", nums, o["pieces"]))
            for mon, d in re.findall(r"\b(Mar|Apr) (\d\d)\b", t):
                stated = date(2026, 3 if mon == "Mar" else 4, int(d)).isoformat()
                if stated != o["due_date"]:
                    mism.append((rid, "due", stated, o["due_date"]))
    print("chat vs order book mismatches:", mism or "none")

    counts = {}
    for rd in READING.values():
        counts[rd["kind"]] = counts.get(rd["kind"], 0) + 1
    print("kinds:", {KIND_ZH[k]: v for k, v in counts.items()})
    assert counts == {"meetable": 7, "impossible": 3, "constraint": 6, "ambiguous": 4, "missing": 3, "ineligible": 4, "unanswerable": 3}

    rows, tmpl = [], []
    for rid in sorted(REQ):
        rd, fm, fs = READING[rid], morning[rid], seq[rid]
        rm, rs = fm.get("reference"), fs.get("reference")
        # the label must be consistent with the independently computed facts (morning queues)
        if rd["behaviour"] == "extract":
            assert (rd["subtype"] == "allocate") == bool(fm["on_time"]), rid
        if rd["behaviour"] == "refuse":
            assert not fm["forced"]["eligible"], rid
        seq_note = ""
        if rs and rm and (rs["workshop"], rs["promised"]) != (rm["workshop"], rm["promised"]):
            seq_note = f"in order: {rs['name']} back {rs['promised']}" + ("" if rs["on_time"] else f", {rs['late']} days late (no on-time option left)")
        rows.append({
            "request_id": rid, "time": REQ[rid]["time"], "requester": REQ[rid]["who"], "text": REQ[rid]["text"],
            "official_behaviour": rd["behaviour"], "internal_subtype": rd["subtype"], "also_accepted_subtype": rd.get("also", ""),
            "instructor_kind": rd["kind"], "order_id": rd.get("order") or "", "rule": rd["rule"],
            "constraint": (f"exclude {','.join(rd['excl'])} ({rd['scope']}, by {rd['by']})" if rd.get("excl") else (rd.get("pref") or "")),
            "session_exclusions_in_force": ",".join(fm["session_excluded"]),
            "reply_must": must_do(rid, rd, fm),
            "on_time_workshops_morning": ",".join(fm.get("on_time", [])),
            "reference_workshop_morning": rm["workshop"] if rm else "", "reference_back_morning": rm["promised"] if rm else "",
            "reference_late_days_morning": rm["late"] if rm else "",
            "in_order_note": seq_note,
            "matching_orders": " | ".join(fm.get("matching_orders", [])),
        })
        if rd["behaviour"] != "extract":
            basis = rows[-1]["reply_must"]
        elif rm["on_time"]:
            basis = f"按时车间：{rows[-1]['on_time_workshops_morning']}；推荐 {rm['name']} {rm['promised']}"
        else:
            basis = f"无按时车间；最早 {rm['name']} {rm['promised']} 晚 {rm['late']} 天"
        tmpl.append([rid, REQ[rid]["time"], REQ[rid]["who"], REQ[rid]["text"], rd["behaviour"].replace("decline-to-answer", "decline"),
                     {"allocate": "allocate", "no_on_time_option": "no_on_time", "ambiguous_reference": "ambiguous", "missing_fields": "missing",
                      "ineligible_suggestion": "ineligible", "not_in_data": "not_in_data"}[rd["subtype"]], basis, "高" if not rd.get("also") else "中", "Claude"])

    with open(HERE / "gold_labels_v3_proposed.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    with open(HERE / "分类_Claude.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, quoting=csv.QUOTE_ALL)
        w.writerow(["编号", "时间", "发送人", "原文", "官方类别", "内部子类", "依据", "把握", "填写人"]); w.writerows(tmpl)
    (HERE / "facts_independent.json").write_text(json.dumps({"morning": morning, "in_order": seq}, ensure_ascii=False, indent=1), encoding="utf-8")

    for r in rows:
        print(f"{r['request_id']} {r['official_behaviour']:<18}{r['internal_subtype']:<22}{r['reference_workshop_morning']:<4}{r['reference_back_morning']:<11}"
              f"late {str(r['reference_late_days_morning']):<3} on-time[{r['on_time_workshops_morning']}]  {r['in_order_note']}")
    print("in-order commits:", [(rid, f["committed"]) for rid, f in seq.items() if f.get("committed")])
