"""Round 2 tests: the specialist-first lateness rule, the rework-safe promise, standing-constraint
timing, the split answer, and the rule parser against the manual parses.

    python tests/test_round2.py      or      python -m pytest tests/ -q
"""
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "harness"))

from desk.pipeline import Desk, inbox_lines  # noqa: E402
from kernel.allocator import Allocator, OBJECTIVES, flexibility  # noqa: E402
from kernel.estimator import estimate  # noqa: E402
from kernel.orders import load_orders, TODAY  # noqa: E402
from kernel.register import load_workshops  # noqa: E402
from llm.llm_client import RuleBasedParser  # noqa: E402

W = load_workshops()
O = load_orders()


def q0():
    return {wid: w.queue0 for wid, w in W.items()}


def batch(oid):
    o = O[oid]
    return {"order_id": oid, "category": o.category, "pieces": o.pieces, "sent_date": TODAY, "due_date": o.due_date}


def top(objective, oid, **kw):
    return Allocator(objective).rank(batch(oid), W, q0(), **kw)


def loaded(objective="lateness"):
    desk = Desk(objective=objective)
    for ln in inbox_lines():
        desk.propose(ln)
    return desk


# ------------------------------------------------------------------ estimator
def test_estimate_reports_the_date_if_reworked():
    e = estimate(W["W6"], 800, 1.0, TODAY, date(2026, 4, 10))
    assert e.on_time and e.promised_date == date(2026, 4, 9)
    assert round(e.worst_finish_days, 2) == 11.23                 # 1.0 + 1.5 * 800/130 + 1
    assert e.worst_date == date(2026, 4, 12) and not e.safe


# ------------------------------------------------------------------ the rule
def test_flexibility_orders_specialists_first():
    assert flexibility(W["W8"]) < flexibility(W["W1"]) < flexibility(W["W2"])     # capped < single category < both
    assert flexibility(W["W4"]) == flexibility(W["W5"]) == 1


def test_accessory_batch_goes_to_the_accessory_only_shop_when_safe():
    rows = top("lateness", "ORD-041")                              # 600 beanies, due 21 Apr
    best = rows[0]["estimate"]
    assert best.workshop_id == "W4" and best.safe and rows[0]["tier"] == 0
    fastest = min((r["estimate"] for r in rows), key=lambda e: e.finish_days)
    assert fastest.workshop_id == "W6"                             # the rule did not take the fastest shop


def test_small_tops_batch_goes_to_the_capped_shop():
    assert top("lateness", "ORD-063")[0]["estimate"].workshop_id == "W8"       # 100 cardigans, FreshStart


def test_no_safe_shop_falls_back_to_on_time_specialist():
    rows = top("lateness", "ORD-053", exclude=["W1"])              # 800 polos, due 10 Apr
    assert not any(r["estimate"].safe for r in rows)
    assert rows[0]["tier"] == 1 and rows[0]["estimate"].workshop_id == "W5" and rows[0]["estimate"].on_time


def test_nothing_on_time_falls_back_to_least_late():
    rows = top("lateness", "ORD-099")                              # 1500 polos, due 5 Apr
    assert rows[0]["tier"] == 2
    assert rows[0]["estimate"].late_days == min(r["estimate"].late_days for r in rows)


def test_use_slack_takes_the_latest_safe_finish():
    a, b = top("lateness", "ORD-040")[0]["estimate"], top("use_slack", "ORD-040")[0]["estimate"]   # 1200 hoodies, due 21 Apr
    assert a.safe and b.safe and b.finish_days > a.finish_days
    assert (a.workshop_id, b.workshop_id) == ("W1", "W3")


def test_chat_preference_still_overrides_the_rule():
    assert top("lateness", "ORD-045", preference="fastest")[0]["estimate"].workshop_id == "W6"


def test_rule_objectives_never_pick_an_ineligible_workshop():
    from simulate import Simulator                                 # raises on an ineligible choice
    for obj in ("lateness", "use_slack"):
        for shock in (False, True):
            out = Simulator(shock=shock, seed=5105).run(Allocator(obj), obj)
            assert len(out) == 120


def test_every_objective_runs_through_the_simulator():
    from simulate import Simulator
    for obj in OBJECTIVES:
        assert len(Simulator(seed=5105).run(Allocator(obj), obj)) == 120


def test_lateness_rule_is_no_worse_than_earliest_finish_on_the_official_orders():
    from simulate import Simulator
    from kernel.allocator import earliest_finish
    for seed in range(5105, 5115):
        sim = Simulator(seed=seed)
        ef, v2 = Simulator.metrics(sim.run(earliest_finish, "ef")), Simulator.metrics(sim.run(Allocator("lateness"), "v2"))
        assert v2["% late"] <= ef["% late"] + 1e-9 and v2["late days"] <= ef["late days"] + 1e-9


# ------------------------------------------------------------------ the desk
def test_explanation_gives_reason_rework_date_and_fastest_alternative():
    d = loaded().decisions["R04"]
    assert d["recommended"] == "W4"
    assert "it only makes ACCESSORIES" in d["explanation"] and "if the batch is reworked" in d["explanation"]
    assert "Fastest: Nimble Needle" in d["explanation"]
    assert d["number_check"]["ok"]


def test_every_number_in_every_reply_is_traced():
    for objective in ("lateness", "lateness_v1", "use_slack", "hybrid"):
        desk = loaded(objective)
        assert all(d["number_check"]["ok"] for d in desk.decisions.values()), objective
        replay = Desk(objective=objective)
        for ln in inbox_lines():
            replay.handle(ln)
        assert all(d["number_check"]["ok"] for d in replay.decisions.values()), objective


def test_standing_constraint_set_later_is_labelled():
    desk = loaded()
    desk.refresh_all()
    early, later = desk.decisions["R04"], desk.decisions["R17"]    # 08:08 and 09:14; Boss's ban is R12 at 08:48
    assert any("was set later" in f for f in early["flags"])
    assert not any("was set later" in f for f in later["flags"])
    r08 = desk.decisions["R08"]                                    # 08:29: QuickStitch was allowed when it arrived
    assert r08["as_received"]["recommended"] == "W1" and r08["recommended"] != "W1"
    assert "after this request arrived" in r08["explanation"] or any("set after this request arrived" in e["reason"] for e in r08["eligibility"])


def test_in_order_replay_does_not_apply_a_constraint_backwards():
    desk = Desk()
    for ln in inbox_lines():
        desk.handle(ln)
    assert desk.decisions["R08"]["recommended"] == "W1"            # refused FreshStart at 08:29; QuickStitch still allowed
    assert "Not considered" not in desk.decisions["R04"]["explanation"]   # 08:08: no constraint existed yet


def test_split_question_gets_an_answer():
    d = loaded().decisions["R23"]
    assert d["subtype"] == "allocate" and "No split needed" in d["explanation"]
    assert any(t["tool"] == "split_estimate" for t in d["tool_calls"])


def test_counts_match_the_instructors_mix_with_morning_queues():
    from collections import Counter
    c = Counter(d["subtype"] for d in loaded().decisions.values())
    assert c == {"allocate": 13, "no_on_time_option": 3, "ambiguous_reference": 4, "missing_fields": 3,
                 "ineligible_suggestion": 4, "not_in_data": 3}


# ------------------------------------------------------------------ the rule parser
def test_rule_parser_matches_the_manual_parses():
    gold = {g["request_id"]: g for g in json.loads((ROOT / "language" / "requests_gold.json").read_text(encoding="utf-8"))}
    fields = ["order_id", "customer", "product", "pieces", "due_date", "forced_workshop", "excluded_workshops", "constraint_scope",
              "preference", "question_type", "references_prior", "missing_fields"]
    parse, hist, bad = RuleBasedParser().parse, [], []
    for ln in inbox_lines():
        r = parse(ln, list(hist))
        hist.append(r)
        for f in fields:
            a, b = r.get(f), gold[r["request_id"]].get(f)
            if a != b and not (a in (None, []) and b in (None, [])):
                bad.append((r["request_id"], f, a, b))
    assert not bad, bad


def test_same_customer_is_not_a_reference():
    parse, hist = RuleBasedParser().parse, []
    out = {}
    for ln in inbox_lines():
        r = parse(ln, list(hist)); hist.append(r); out[r["request_id"]] = r
    assert out["R21"]["references_prior"] is None and out["R23"]["references_prior"] is None
    assert out["R20"]["references_prior"] == "R14" and out["R15"]["references_prior"] == "R10"


# ------------------------------------------------------------------ grounding: the model proposes, the text decides
def _ground(text, **fields):
    from llm.llm_client import empty_request, ground
    r = empty_request()
    r.update(fields)
    return ground(r, text, None)


def test_grounding_drops_a_workshop_the_message_never_names():
    r = _ground("New rush coming in from Loom & Leaf — details to follow, but book capacity somewhere good.", forced_workshop="W4")
    assert r["forced_workshop"] is None and r["customer"] == "Loom & Leaf"
    assert any("forced_workshop" in c for c in r["grounding"])


def test_grounding_fills_a_named_workshop_the_model_missed():
    r = _ground("Send ORD-073 (400 hoodies) to FreshStart, their quote was good.", order_id="ORD-073", pieces=400)
    assert r["forced_workshop"] == "W8" and r["product"] == "Hoodie"


def test_grounding_rejects_today_as_a_due_date_and_an_unsupported_quantity():
    r = _ground("Need scarves for Harbor Knits sent out today, usual quantities.", due_date="2026-04-01", pieces=500)
    assert r["due_date"] is None and r["pieces"] is None and "order_id" in r["missing_fields"]


def test_grounding_keeps_quantities_written_with_commas_or_k():
    assert _ground("ORD-036: 1,000 scarves, due Apr 26.", order_id="ORD-036", pieces=1000, due_date="2026-04-26")["pieces"] == 1000
    assert _ground("Dispatch ORD-040 — 1.2k hoodies, due Apr 21.", order_id="ORD-040", pieces=1200, due_date="2026-04-21")["pieces"] == 1200


def test_grounding_settles_how_long_an_exclusion_lasts():
    text = "ORD-053 — 800 polo shirts for UrbanThread, due Apr 10. Boss says nothing new to QuickStitch this week, they're swamped."
    r = _ground(text, order_id="ORD-053", excluded_workshops=["W1"], constraint_scope="request", pieces=800, due_date="2026-04-10")
    assert r["constraint_scope"] == "session" and r["excluded_workshops"] == ["W1"] and r["forced_workshop"] is None
    one_off = _ground("ORD-109 — 500 vests, due Apr 13. …and keep it away from BudgetWorks, the last batch came back rough.", order_id="ORD-109")
    assert one_off["excluded_workshops"] == ["W3"] and one_off["constraint_scope"] == "request"


def test_grounding_takes_a_stated_preference_and_the_only_date():
    assert _ground("That big reorder from last week — send it to whoever is quickest.")["preference"] == "fastest"
    r = _ground("Loom & Leaf confirmed the reorder: ORD-024, 300 vests. Needs to ship Apr 15, so it has to go out today.", order_id="ORD-024", pieces=300)
    assert r["due_date"] == "2026-04-15"
    pending = _ground("ORD-066 due date just moved up — will confirm the new date after the call, but line something up.", order_id="ORD-066", question_type="status")
    assert pending["due_date"] is None and pending["missing_fields"] == ["due_date"] and pending["question_type"] == "allocation"


def test_grounding_keeps_a_missing_date_only_when_the_message_talks_about_timing():
    named = _ground("OldMill is free right now — give them ORD-008.", order_id="ORD-008", forced_workshop="W7", missing_fields=["due_date"])
    assert named["missing_fields"] == [] and named["forced_workshop"] == "W7"
    asked = _ground("ORD-008: the customer wants it earlier but has not said when.", order_id="ORD-008", missing_fields=["due_date"])
    assert asked["missing_fields"] == ["due_date"]


def test_grounding_leaves_a_real_status_question_alone():
    assert _ground("Any movement on ORD-999? Customer is chasing.", order_id="ORD-999", question_type="status")["question_type"] == "status"


def test_bulk_confirm_leaves_tight_requests_to_the_dispatcher():
    desk = loaded()
    plan = desk.bulk_plan()
    out = desk.confirm_all()
    assert [x["request_id"] for x in out["confirmed"]] == plan["confirm"] and plan["confirm"]
    for x in out["confirmed"]:
        rec = next(r for r in desk.ledger.records if r["audit_id"] == x["audit_id"])
        assert rec["estimate"]["safe"] and rec["estimate"]["on_time"]
    assert any(h["reason"].startswith("tight") for h in out["skipped"])
    assert desk.actions[-1]["action"] == "confirm_all"


def test_new_work_is_asked_for_details_not_matched_to_an_old_order():
    desk = Desk()
    d = desk.propose("C06 [08:15] Boss: Maple & Co will send a repeat order this afternoon, numbers not final. Pencil in a workshop.")
    assert d["subtype"] == "missing_fields" and "piece count" in d["explanation"]


def test_a_request_for_an_order_already_dispatched_is_not_dispatched_twice():
    desk = Desk()
    desk.handle("C01 [07:50] Chen: ORD-082 can go out — 600 beanies for TrendCart, back by May 1.")
    d = desk.handle("C25 [09:41] Priya: ORD-082 — 600 beanies for TrendCart — please get this placed today.")
    assert d["subtype"] == "state_conflict" and len(desk.ledger.records) == 1


def test_every_reply_stays_traced_after_a_refresh_and_a_bulk_confirm():
    desk = loaded()
    desk.refresh_all()                                             # a later standing constraint adds its time to earlier replies
    assert [d["request_id"] for d in desk.decisions.values() if not d["number_check"]["ok"]] == []
    desk.confirm_all()
    assert [d["request_id"] for d in desk.decisions.values() if not d["number_check"]["ok"]] == []


if __name__ == "__main__":
    import inspect
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and inspect.isfunction(fn):
            try:
                fn()
                print("PASS", name)
            except AssertionError as ex:
                failed += 1
                print("FAIL", name, ex)
    print("failed:", failed)
    sys.exit(1 if failed else 0)
