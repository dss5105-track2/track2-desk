"""Week-1 acceptance tests for the deterministic kernel.

Run with either:
    python -m pytest tests/ -q
    python tests/test_kernel.py
The five hand-calculated cases come from the project handbook (section 11.2). They use
include_rework=False so the numbers are the plain queue + pieces/capacity + lead sums.
"""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kernel.register import load_workshops, check_eligibility, eligible_workshops, find_by_name  # noqa: E402
from kernel.estimator import estimate, estimate_all, split_estimate  # noqa: E402
from kernel.allocator import Allocator, earliest_finish  # noqa: E402
from kernel.ledger import Ledger  # noqa: E402
from kernel.orders import load_orders, state_checks, find_orders, TODAY  # noqa: E402

W = load_workshops()
O = load_orders()


def q0():
    return {wid: w.queue0 for wid, w in W.items()}


def test_case_r09_nimble_needle_3_2_days():
    o = O["ORD-045"]  # 150 vests, due 2026-04-09
    e = estimate(W["W6"], o.pieces, W["W6"].queue0, TODAY, o.due_date, include_rework=False)
    assert round(e.finish_days, 1) == 3.2
    assert e.on_time and e.promised_date == date(2026, 4, 4)


def test_case_r12_nimble_needle_8_2_days():
    o = O["ORD-053"]  # 800 polo shirts, due 2026-04-10
    e = estimate(W["W6"], o.pieces, W["W6"].queue0, TODAY, o.due_date, include_rework=False)
    assert round(e.finish_days, 1) == 8.2 and e.on_time


def test_case_r12_giantweave_9_0_days():
    o = O["ORD-053"]
    e = estimate(W["W5"], o.pieces, W["W5"].queue0, TODAY, o.due_date, include_rework=False)
    assert round(e.finish_days, 1) == 9.0
    assert e.promised_date == date(2026, 4, 10) and e.on_time   # exactly on the due date counts as on time


def test_case_r04_steadyhands_13_3_days_and_late():
    o = O["ORD-029"]  # 1500 beanies, due today
    e = estimate(W["W2"], o.pieces, W["W2"].queue0, TODAY, o.due_date, include_rework=False)
    assert round(e.finish_days, 1) == 13.3
    assert not e.on_time and e.late_days == 13


def test_case_r08_freshstart_ineligible_for_400():
    ok, why = check_eligibility(W["W8"], "TOPS", 400)
    assert not ok and "300" in why
    ok, _ = check_eligibility(W["W8"], "TOPS", 300)
    assert ok


def test_three_questions():
    assert check_eligibility(W["W7"], "TOPS", 100) == (False, "status=SUSPENDED")
    ok, why = check_eligibility(W["W1"], "ACCESSORIES", 100)
    assert not ok and "cannot make ACCESSORIES" in why
    ok, why = check_eligibility(W["W4"], "TOPS", 100)
    assert not ok and "cannot make TOPS" in why
    acc = {w.workshop_id for w in eligible_workshops(W, "ACCESSORIES", 2000)}
    assert acc == {"W2", "W4", "W6"}
    tops_small = {w.workshop_id for w in eligible_workshops(W, "TOPS", 150)}
    assert tops_small == {"W1", "W2", "W3", "W5", "W6", "W8"}


def test_exclusion_r12_avoid_quickstitch():
    o = O["ORD-053"]
    ests = estimate_all(W, o.category, o.pieces, q0(), TODAY, o.due_date, exclude=["W1"], include_rework=False)
    ids = [e.workshop_id for e in ests]
    assert "W1" not in ids and ids[0] == "W6"


def test_r21_cheapest_that_makes_apr_13_is_giantweave():
    o = O["ORD-081"]  # 1500 crewnecks, due 2026-04-13
    a = Allocator("lateness")
    rows = a.rank({"order_id": o.order_id, "category": o.category, "pieces": o.pieces,
                   "sent_date": TODAY, "due_date": o.due_date}, W, q0(), preference="cheapest_on_time")
    on_time = [r["estimate"].workshop_id for r in rows if r["estimate"].on_time]
    assert rows[0]["estimate"].workshop_id == "W5"        # GiantWeave, 1.1/piece
    assert "W3" not in on_time                            # BudgetWorks is cheaper but cannot make the date


def test_no_on_time_option_r06():
    o = O["ORD-061"]  # 800 scarves, due 2026-04-05, 4 days of slack
    ests = estimate_all(W, o.category, o.pieces, q0(), TODAY, o.due_date, include_rework=False)
    assert all(not e.on_time for e in ests)
    assert ests[0].workshop_id == "W6" and round(ests[0].finish_days, 1) == 8.2


def test_earliest_finish_never_picks_ineligible():
    for o in O.values():
        wid = earliest_finish({"order_id": o.order_id, "category": o.category, "pieces": o.pieces,
                               "sent_date": o.order_date, "due_date": o.due_date}, W, q0())
        assert check_eligibility(W[wid], o.category, o.pieces)[0]


def test_ledger_updates_queue_and_blocks_duplicates():
    L = Ledger(W, TODAY)
    o = O["ORD-045"]
    before = L.queues()["W6"]
    rec = L.commit(request_id="R09", order_id=o.order_id, workshop_id="W6", category=o.category, pieces=o.pieces,
                   sent_date=TODAY, due_date=o.due_date, requester="Boss", confirmed_by="dispatcher",
                   reason="fastest eligible")
    after = L.queues()["W6"]
    assert after > before and rec["audit_id"] == "A0001"
    try:
        L.commit(request_id="R99", order_id=o.order_id, workshop_id="W1", category=o.category, pieces=o.pieces,
                 sent_date=TODAY, due_date=o.due_date, requester="x", confirmed_by="y", reason="dup")
        assert False, "duplicate commit must be rejected"
    except ValueError:
        pass


def test_state_checks():
    assert "PACKING" in " ".join(state_checks(O["ORD-114"]))
    assert "already passed" in " ".join(state_checks(O["ORD-120"]))
    assert "due today" in " ".join(state_checks(O["ORD-029"]))
    assert state_checks(None) == ["order not found"]
    assert state_checks(O["ORD-045"]) == []
    assert len(find_orders(O, customer="TrendCart")) == 6


def test_find_by_name():
    assert find_by_name(W, "OldMill is free right now") == ["W7"]
    assert find_by_name(W, "keep it away from BudgetWorks") == ["W3"]
    assert find_by_name(W, "Little Loom does lovely work") == ["W4"]


def test_split_estimate_r23_gains_little():
    o = O["ORD-093"]  # 100 beanies
    s = split_estimate(W, o.category, o.pieces, q0(), TODAY, o.due_date)
    assert s["possible"] and s["gain_days"] < 1.0


def _batch(oid):
    o = O[oid]
    return {"order_id": oid, "category": o.category, "pieces": o.pieces, "sent_date": TODAY, "due_date": o.due_date}


def _commit(L, rid, oid, wid):
    o = O[oid]
    return L.commit(request_id=rid, order_id=oid, workshop_id=wid, category=o.category, pieces=o.pieces,
                    sent_date=TODAY, due_date=o.due_date, requester="test", confirmed_by="test", reason="test")


def test_protocol_ledger_changes_r12_and_r21():
    """eval/protocol.md: the gold answer depends on earlier commits and on the session ban."""
    L = Ledger(W, TODAY)
    a = Allocator("lateness")
    # R12 processed in isolation -> Nimble Needle
    assert a.rank(_batch("ORD-053"), W, L.queues(), exclude=["W1"])[0]["estimate"].workshop_id == "W6"
    # R09 commits 150 vests to Nimble Needle first
    rec = _commit(L, "R09", "ORD-045", "W6")
    assert abs(rec["queue_after"] - 2.18) < 0.01
    r12 = a.rank(_batch("ORD-053"), W, L.queues(), exclude=["W1"])
    assert r12[0]["estimate"].workshop_id == "W5"                       # GiantWeave now earliest
    nn = next(r["estimate"] for r in r12 if r["estimate"].workshop_id == "W6")
    assert nn.on_time and nn.promised_date == date(2026, 4, 10)         # still on time after round()
    _commit(L, "R12", "ORD-053", "W5")
    # R21 with Boss's session ban: nobody makes Apr 13
    r21 = a.rank(_batch("ORD-081"), W, L.queues(), exclude=["W1"], preference="cheapest_on_time")
    assert not any(r["estimate"].on_time for r in r21)
    assert r21[0]["estimate"].workshop_id == "W5" and r21[0]["estimate"].late_days == 1
    # interpretation B (ban only for R12): QuickStitch makes it
    r21b = a.rank(_batch("ORD-081"), W, L.queues(), preference="cheapest_on_time")
    assert r21b[0]["estimate"].workshop_id == "W1" and r21b[0]["estimate"].on_time


def test_r25_ban_changes_winner():
    L = Ledger(W, TODAY)
    a = Allocator("lateness")
    _commit(L, "R09", "ORD-045", "W6")
    _commit(L, "R12", "ORD-053", "W5")
    with_ban = a.rank(_batch("ORD-109"), W, L.queues(), exclude=["W1", "W3"])
    without_ban = a.rank(_batch("ORD-109"), W, L.queues(), exclude=["W3"])
    assert with_ban[0]["estimate"].workshop_id == "W6"
    assert without_ban[0]["estimate"].workshop_id == "W1"


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
