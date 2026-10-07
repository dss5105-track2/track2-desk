"""The challenge inbox: 38 new chat messages about the same order book, written by Claude BEFORE any
change was made to the language layer in round 2, to test it on wording it was not built around.

    python 03_语言层评估/挑战集/make_challenge.py

This is NOT the team's held-out set (eval/heldout_matrix.md): that one is written by teammates who do
not touch the system. This set is AI-written and is reported separately, labelled as such.

Writes (same folder): challenge_requests.txt, challenge_labels.csv, challenge_parses.json.
Facts are computed by 01_标注/make_labels.py (independent of the system); labels follow 标注规则_v3.md.
Messages are processed in time order on the morning of 2026-04-01, with their own ledger.
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent / "01_标注"))
import make_labels as ML  # noqa: E402


def P(order=None, customer=None, product=None, pieces=None, due=None, forced=None, excl=(), scope="request", pref="none",
      qtype="allocation", ref=None, missing=()):
    """The hand-made parse of one message: only what the message itself states."""
    return {"order_id": order, "customer": customer, "product": product, "pieces": pieces, "due_date": due, "forced_workshop": forced,
            "excluded_workshops": list(excl), "constraint_scope": scope, "preference": pref, "question_type": qtype,
            "references_prior": ref, "missing_fields": list(missing)}


ALL3 = ("order_id", "pieces", "due_date")
# (id, time, sender, text, parse, label)
M = [
    ("C01", "07:50", "Chen", "Morning. ORD-082 can go out — 600 beanies for TrendCart, back by May 1.",
     P("ORD-082", "TrendCart", "Beanie", 600, "2026-05-01"), dict(kind="meetable", behaviour="extract", subtype="allocate", rule="E1")),
    ("C02", "07:55", "Mei", "Where are we sending the Cotton Club order?",
     P(customer="Cotton Club", missing=("order_id",)), dict(kind="ambiguous", behaviour="clarify", subtype="ambiguous_reference", rule="C1", lookup=dict(customer="Cotton Club"))),
    ("C03", "08:01", "Boss", "ORD-024 — 300 vests for Loom & Leaf, due Apr 15. Get it back as fast as you can, never mind the price.",
     P("ORD-024", "Loom & Leaf", "Vest", 300, "2026-04-15", pref="fastest"), dict(kind="constraint", behaviour="extract", subtype="allocate", rule="E2", pref="fastest")),
    ("C04", "08:06", "Ravi", "ORD-108 — 2000 scarves for Harbor Knits. Needs to be back Apr 3.",
     P("ORD-108", "Harbor Knits", "Scarf", 2000, "2026-04-03"), dict(kind="impossible", behaviour="extract", subtype="no_on_time_option", rule="E4")),
    ("C05", "08:10", "Ravi", "Pls place ORD-036: 1,000 scarves, UrbanThread, needed 26 Apr.",
     P("ORD-036", "UrbanThread", "Scarf", 1000, "2026-04-26"), dict(kind="meetable", behaviour="extract", subtype="allocate", rule="E1")),
    ("C06", "08:15", "Boss", "Maple & Co will send a repeat order this afternoon, numbers not final. Pencil in a workshop.",
     P(customer="Maple & Co", missing=ALL3), dict(kind="missing", behaviour="clarify", subtype="missing_fields", rule="C3")),
    ("C07", "08:19", "Priya", "ORD-109, 500 vests, Harbor Knits, due Apr 13. Tight budget on this — the cheapest workshop that still hits the 13th.",
     P("ORD-109", "Harbor Knits", "Vest", 500, "2026-04-13", pref="cheapest_on_time"), dict(kind="constraint", behaviour="extract", subtype="allocate", rule="E2", pref="cheapest_on_time")),
    ("C08", "08:24", "Chen", "Put ORD-053 with OldMill, they did a nice job last time.",
     P("ORD-053", forced="W7"), dict(kind="ineligible", behaviour="refuse", subtype="ineligible_suggestion", rule="F1", forced="W7")),
    ("C09", "08:28", "Mei", "ORD-035 is ready for a workshop. 300 beanies (Loom & Leaf), due April 29.",
     P("ORD-035", "Loom & Leaf", "Beanie", 300, "2026-04-29"), dict(kind="meetable", behaviour="extract", subtype="allocate", rule="E1")),
    ("C10", "08:33", "Chen", "The hoodies need a workshop today.",
     P(product="Hoodie", missing=("order_id",)), dict(kind="ambiguous", behaviour="clarify", subtype="ambiguous_reference", rule="C1", lookup=dict(product="Hoodie"))),
    ("C11", "08:37", "Mei", "ORD-005: 500 scarves for TrendCart due Apr 20. They complained about quality last time, so whoever has the fewest defects.",
     P("ORD-005", "TrendCart", "Scarf", 500, "2026-04-20", pref="lowest_defect"), dict(kind="constraint", behaviour="extract", subtype="allocate", rule="E2", pref="lowest_defect")),
    ("C12", "08:42", "Priya", "ORD-062, 2000 scarves, Bright Basics, due Apr 08. Where can it go?",
     P("ORD-062", "Bright Basics", "Scarf", 2000, "2026-04-08"), dict(kind="impossible", behaviour="extract", subtype="no_on_time_option", rule="E4")),
    ("C13", "08:46", "Ravi", "QuickStitch can take the beanies on ORD-041, right?",
     P("ORD-041", product="Beanie", forced="W1"), dict(kind="ineligible", behaviour="refuse", subtype="ineligible_suggestion", rule="F1", forced="W1")),
    ("C14", "08:51", "Priya", "Need a shop for ORD-010 today, 1000 cardigans, Cotton Club want them by Apr 25.",
     P("ORD-010", "Cotton Club", "Cardigan", 1000, "2026-04-25"), dict(kind="meetable", behaviour="extract", subtype="allocate", rule="E1")),
    ("C15", "08:55", "Chen", "ORD-066 — Northwind Apparel want it sooner than planned but haven't said when. Start looking.",
     P("ORD-066", "Northwind Apparel", missing=("due_date",)), dict(kind="missing", behaviour="clarify", subtype="missing_fields", rule="C3")),
    ("C16", "09:00", "Ravi", "ORD-063 — 100 cardigans, Apr 29. Anyone but BudgetWorks please.",
     P("ORD-063", product="Cardigan", pieces=100, due="2026-04-29", excl=("W3",)), dict(kind="constraint", behaviour="extract", subtype="allocate", rule="E3", excl=["W3"], scope="request", by="Ravi")),
    ("C17", "09:04", "Priya", "ORD-081 to FreshStart please — 1500 crewnecks.",
     P("ORD-081", product="Crewneck sweater", pieces=1500, forced="W8"), dict(kind="ineligible", behaviour="refuse", subtype="ineligible_suggestion", rule="F1", forced="W8")),
    ("C18", "09:09", "Boss", "Heads up: GiantWeave's truck is off the road, don't send them anything new until further notice. Meanwhile ORD-073 (400 hoodies, due Apr 20) needs a home.",
     P("ORD-073", product="Hoodie", pieces=400, due="2026-04-20", excl=("W5",), scope="session"),
     dict(kind="constraint", behaviour="extract", subtype="allocate", rule="E3", excl=["W5"], scope="session", by="Boss")),
    ("C19", "09:14", "Ravi", "Can you sort out that Northwind Apparel order from early March?",
     P(customer="Northwind Apparel", missing=("order_id",)), dict(kind="ambiguous", behaviour="clarify", subtype="ambiguous_reference", rule="C1", lookup=dict(customer="Northwind Apparel"))),
    ("C20", "09:18", "Chen", "Dispatch ORD-040 — 1.2k hoodies, Loom & Leaf, due Apr 21.",
     P("ORD-040", "Loom & Leaf", "Hoodie", 1200, "2026-04-21"), dict(kind="meetable", behaviour="extract", subtype="allocate", rule="E1")),
    ("C21", "09:23", "Mei", "Give ORD-017 to GiantWeave, they have the capacity.",
     P("ORD-017", forced="W5"), dict(kind="ineligible", behaviour="refuse", subtype="ineligible_suggestion", rule="F3", forced="W5")),
    ("C22", "09:27", "Mei", "ORD-020 has to go out: 1200 vests for TrendCart, due Mar 31.",
     P("ORD-020", "TrendCart", "Vest", 1200, "2026-03-31"), dict(kind="impossible", behaviour="extract", subtype="no_on_time_option", rule="E4")),
    ("C23", "09:32", "Chen", "How many batches did BudgetWorks deliver late last quarter?",
     P(qtype="information"), dict(kind="unanswerable", behaviour="decline-to-answer", subtype="not_in_data", rule="D1")),
    ("C24", "09:36", "Mei", "Some polo shirts for a new customer, a few hundred, date to be confirmed.",
     P(product="Polo shirt", missing=ALL3), dict(kind="missing", behaviour="clarify", subtype="missing_fields", rule="C3")),
    ("C25", "09:41", "Priya", "ORD-082 — 600 beanies for TrendCart — please get this placed today.",
     P("ORD-082", "TrendCart", "Beanie", 600, ref="C01"), dict(kind="state", behaviour="clarify", subtype="state_conflict", rule="S1")),
    ("C26", "09:45", "Priya", "Bright Basics are asking about their scarves — get them out the door please.",
     P(customer="Bright Basics", product="Scarf", missing=("order_id",)), dict(kind="ambiguous", behaviour="clarify", subtype="ambiguous_reference", rule="C1", lookup=dict(customer="Bright Basics", product="Scarf"))),
    ("C27", "09:50", "Ravi", "ORD-095 for Bright Basics has to go outside. 800 hoodies. Deadline is Apr 26.",
     P("ORD-095", "Bright Basics", "Hoodie", 800, "2026-04-26"), dict(kind="meetable", behaviour="extract", subtype="allocate", rule="E1")),
    ("C28", "09:54", "Boss", "Little Loom for ORD-015.",
     P("ORD-015", forced="W4"), dict(kind="ineligible", behaviour="refuse", subtype="ineligible_suggestion", rule="F1", forced="W4")),
    ("C29", "09:59", "Priya", "What's our margin on ORD-081?",
     P("ORD-081", qtype="information"), dict(kind="unanswerable", behaviour="decline-to-answer", subtype="not_in_data", rule="D1", info=True)),
    ("C30", "10:03", "Chen", "ORD-096 — 1000 beanies, TrendCart, due Apr 17. If two shops get it done sooner, split it.",
     P("ORD-096", "TrendCart", "Beanie", 1000, "2026-04-17", pref="split"), dict(kind="constraint", behaviour="extract", subtype="allocate", rule="E5", pref="split")),
    ("C31", "10:08", "Ravi", "ORD-057 needs to go outside, 600 cardigans for UrbanThread.",
     P("ORD-057", "UrbanThread", "Cardigan", 600), dict(kind="state", behaviour="clarify", subtype="state_conflict", rule="S1")),
    ("C32", "10:12", "Ravi", "About the Maple & Co repeat order from this morning: still waiting on quantities.",
     P(customer="Maple & Co", ref="C06", missing=ALL3), dict(kind="missing", behaviour="clarify", subtype="missing_fields", rule="C3")),
    ("C33", "10:17", "Boss", "ORD-061 — 800 scarves, Harbor Knits, ship by Apr 5.",
     P("ORD-061", "Harbor Knits", "Scarf", 800, "2026-04-05"), dict(kind="impossible", behaviour="extract", subtype="no_on_time_option", rule="E4")),
    ("C34", "10:21", "Chen", "ORD-029 to FreshStart? 1500 beanies.",
     P("ORD-029", product="Beanie", pieces=1500, forced="W8"), dict(kind="ineligible", behaviour="refuse", subtype="ineligible_suggestion", rule="F2", forced="W8")),
    ("C35", "10:26", "Boss", "The UrbanThread job should go out today.",
     P(customer="UrbanThread", missing=("order_id",)), dict(kind="ambiguous", behaviour="clarify", subtype="ambiguous_reference", rule="C1", lookup=dict(customer="UrbanThread"))),
    ("C36", "10:30", "Mei", "Who is the line supervisor at SteadyHands these days?",
     P(qtype="information"), dict(kind="unanswerable", behaviour="decline-to-answer", subtype="not_in_data", rule="D1")),
    ("C37", "10:35", "Ravi", "Any news on ORD-777?",
     P("ORD-777", qtype="status"), dict(kind="unanswerable", behaviour="decline-to-answer", subtype="not_in_data", rule="D2", info=True)),
    ("C38", "10:39", "Boss", "What did TrendCart pay per piece on their last beanie order?",
     P(customer="TrendCart", product="Beanie", qtype="information"), dict(kind="unanswerable", behaviour="decline-to-answer", subtype="not_in_data", rule="D1")),
]

REQ = {m[0]: {"time": m[1], "who": m[2], "text": m[3]} for m in M}
READING = {}
for cid, _, _, _, parse, lab in M:
    rd = dict(lab)
    rd["order"] = parse["order_id"]
    READING[cid] = rd


def must(cid, rd, f):
    ref = f.get("reference")
    name = ML.NAME
    if rd["subtype"] == "not_in_data":
        return "say it is not in the data (or the order does not exist); give no figure, name or workshop"
    if rd["subtype"] == "state_conflict":
        return "say the order is already dispatched in this session or already complete; ask before doing anything; do not allocate again"
    if rd["subtype"] == "ambiguous_reference":
        return f"list the {len(f.get('matching_orders', []))} matching in-progress orders and ask which; do not guess"
    if rd["subtype"] == "missing_fields":
        return "ask for what is missing (order number, pieces, due date); do not book capacity"
    if rd["behaviour"] == "refuse":
        why = f["forced"]["reason"] if not f["forced"]["eligible"] else "standing constraint set earlier in this inbox"
        alt = (f"alternative {ref['name']} back {ref['promised']} on time" if ref and ref["on_time"]
               else f"no on-time alternative: earliest {ref['name']} back {ref['promised']}, {ref['late']} days late")
        return f"refuse {name[rd['forced']]}: {why}; {alt}"
    if rd["subtype"] == "no_on_time_option":
        return f"say no workshop makes the date; earliest {ref['name']} back {ref['promised']}, {ref['late']} days late; give options; do not allocate silently"
    return f"recommend an eligible on-time workshop (reference: {ref['name']} back {ref['promised']}); honour the constraint; commit only after confirmation"


if __name__ == "__main__":
    morning, seq = ML.replay(False, REQ, READING), ML.replay(True, REQ, READING)
    rows = []
    for cid, t, who, text, parse, lab in M:
        rd, fm, fs = READING[cid], morning[cid], seq[cid]
        rm = fm.get("reference")
        # consistency of the intended label with the independently computed facts
        if rd["kind"] in ("meetable", "constraint"):
            assert fm["on_time"], (cid, "intended meetable but nobody is on time")
        if rd["kind"] == "impossible":
            assert not fm["on_time"], (cid, "intended impossible but", fm["on_time"])
        if rd["behaviour"] == "refuse" and rd["rule"] != "F3":
            assert not fm["forced"]["eligible"], cid
        if rd["rule"] == "F3":
            assert rd["forced"] in fm["session_excluded"], cid
        if rd["kind"] == "ambiguous":
            assert len(fm["matching_orders"]) >= 2, (cid, fm.get("matching_orders"))
        if rd["kind"] == "state":
            assert fs.get("order_status") == "COMPLETE" or fs.get("already_committed_by"), (cid, fs.get("order_status"), fs.get("already_committed_by"))
        rows.append({
            "request_id": cid, "time": t, "requester": who, "text": text, "official_behaviour": rd["behaviour"], "internal_subtype": rd["subtype"],
            "also_accepted_subtype": rd.get("also", ""), "instructor_kind": rd["kind"], "order_id": rd.get("order") or "", "rule": rd["rule"],
            "constraint": (f"exclude {','.join(rd['excl'])} ({rd['scope']}, by {rd['by']})" if rd.get("excl") else (rd.get("pref") or "")),
            "session_exclusions_in_force": ",".join(fm["session_excluded"]), "reply_must": must(cid, rd, fm),
            "on_time_workshops_morning": ",".join(fm.get("on_time", [])),
            "reference_workshop_morning": rm["workshop"] if rm else "", "reference_back_morning": rm["promised"] if rm else "",
            "reference_late_days_morning": rm["late"] if rm else "", "in_order_note": "", "matching_orders": " | ".join(fm.get("matching_orders", [])),
        })
    with open(HERE / "challenge_labels.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    (HERE / "challenge_requests.txt").write_text(
        "# Challenge inbox, morning of 2026-04-01. AI-written (Claude), round 2. Not the held-out set.\n"
        + "\n".join(f"{cid} [{t}] {who}: {text}" for cid, t, who, text, _, _ in M) + "\n", encoding="utf-8")
    parses = []
    for cid, t, who, text, parse, _ in M:
        parses.append({"request_id": cid, "timestamp": t, "requester": who, "raw_text": text, **parse, "parser": "manual"})
    (HERE / "challenge_parses.json").write_text(json.dumps(parses, ensure_ascii=False, indent=1), encoding="utf-8")
    from collections import Counter
    print("messages:", len(M), "| kinds:", dict(Counter(r["instructor_kind"] for r in rows)))
    print("behaviours:", dict(Counter(r["official_behaviour"] for r in rows)))
    for r in rows:
        print(f"{r['request_id']} {r['official_behaviour']:<18}{r['internal_subtype']:<22}{r['reference_workshop_morning']:<4}{r['reference_back_morning']:<11} on-time[{r['on_time_workshops_morning']}] excl[{r['session_exclusions_in_force']}]")
