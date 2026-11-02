"""Harder cases for a workshop stopping: wording that used to mislead the desk, and what a stop does to other work."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "harness"))

from desk.pipeline import Desk  # noqa: E402


def message(text, sender="Ravi"):
    return Desk().new_message(sender, text)


# ---------------------------------------------------------------- what the stop clause must not change
def test_a_reopening_date_is_not_the_due_date():
    d = message("ORD-053 for UrbanThread. GiantWeave has shut until May 30.")
    assert d["batch"]["due_date"] == "2026-04-10" and d["stop_mentions"] == ["W5"]


def test_a_reopening_date_does_not_turn_a_report_into_a_question():
    d = message("GiantWeave has shut until Apr 20.")
    assert d["subtype"] == "closure_report" and d["reported_workshop"] == "W5"


def test_a_workshop_named_in_a_stop_clause_is_not_the_one_asked_for():
    d = message("QuickStitch has shut, send ORD-053 to Little Loom.")
    assert d["subtype"] == "ineligible_suggestion" and d["refused_workshop"] == "W4" and d["stop_mentions"] == ["W1"]


def test_an_order_in_the_same_clause_is_kept():
    d = message("ORD-053 GiantWeave has shut until May 30.")
    assert d["order_id"] == "ORD-053" and d["batch"]["due_date"] == "2026-04-10" and d["stop_mentions"] == ["W5"]


def test_a_ban_in_the_same_message_is_still_recorded():
    desk = Desk()
    d = desk.new_message("Boss", "Boss says nothing new to QuickStitch this week. GiantWeave has shut.")
    assert d["subtype"] != "closure_report" and d["stop_mentions"] == ["W5"]
    assert list(desk.session_excl) == ["W1"] and desk.stopped == {}


# ---------------------------------------------------------------- wording
@pytest.mark.parametrize("text", ["GiantWeave closed this morning.", "GiantWeave closed this week.", "GiantWeave closed the factory."])
def test_closed_with_a_time_or_place_is_a_stop(text):
    d = message(text)
    assert d["subtype"] == "closure_report" and d["reported_workshop"] == "W5"


def test_closed_in_an_order_message_keeps_the_shop_out():
    d = message("ORD-053 for UrbanThread. GiantWeave closed this week.")
    assert d["stop_mentions"] == ["W5"] and all(c["workshop_id"] != "W5" for c in d["candidates"])


@pytest.mark.parametrize("text", ["GiantWeave closed the deal with us.", "GiantWeave closed the ORD-012 ticket.",
                                  "Send ORD-053 to GiantWeave, it is no longer out of service."])
def test_not_a_stop(text):
    d = message(text)
    assert d["subtype"] != "closure_report" and not d["stop_mentions"]


def test_something_else_closing_is_not_a_stop():
    d = message("Little Loom says the customs office closed.")
    assert d["subtype"] != "closure_report" and not d["stop_mentions"]


def test_a_time_clause_is_not_a_stop():
    d = message("ORD-066 needs to go out before QuickStitch closes tonight.")
    assert d["subtype"] != "closure_report" and not d["stop_mentions"]


def test_a_message_that_asks_for_a_shop_is_not_only_a_report():
    d = message("That big reorder needs a shop, GiantWeave has shut.")
    assert d["subtype"] != "closure_report" and d["stop_mentions"] == ["W5"]


def test_a_question_is_read_as_a_question_whatever_the_rest_says():
    assert not message("Is GiantWeave shut?")["stop_mentions"]
    assert message("Is GiantWeave shut?")["subtype"] != "closure_report"


# ---------------------------------------------------------------- a wrong reading can be undone
def test_a_mention_can_be_dismissed():
    desk = Desk()
    d = desk.new_message("Ravi", "ORD-053 - 800 polo shirts for UrbanThread, due Apr 10. GiantWeave has shut.")
    assert all(c["workshop_id"] != "W5" for c in d["candidates"])
    desk.dismiss_stop_mention(d["request_id"], "W5")
    after = desk.decisions[d["request_id"]]
    assert after["stop_mentions"] == [] and any(c["workshop_id"] == "W5" for c in after["candidates"])
    assert desk.pending_stops() == {}


def test_dismissing_restores_a_workshop_the_message_asked_for():
    desk = Desk()
    d = desk.new_message("Ravi", "Send ORD-053 to GiantWeave, GiantWeave has shut.")
    assert d["parsed"]["forced_workshop"] is None
    desk.dismiss_stop_mention(d["request_id"], "W5")
    assert desk.decisions[d["request_id"]]["parsed"]["forced_workshop"] == "W5"


def test_reopening_also_ends_what_a_message_ruled_out():
    desk = Desk()
    d = desk.new_message("Ravi", "ORD-053 - 800 polo shirts for UrbanThread, due Apr 10. GiantWeave has shut.")
    desk.mark_stopped("W5", source=d["request_id"])
    desk.reopen("W5")
    assert any(c["workshop_id"] == "W5" for c in desk.decisions[d["request_id"]]["candidates"])


def test_a_ban_stated_in_the_request_survives_a_dismissal():
    desk = Desk()
    d = desk.new_message("Ravi", "ORD-053 - 800 polo shirts for UrbanThread, due Apr 10. Not GiantWeave. GiantWeave has shut.")
    desk.dismiss_stop_mention(d["request_id"], "W5")
    assert all(c["workshop_id"] != "W5" for c in desk.decisions[d["request_id"]]["candidates"])


def test_a_mention_does_not_become_a_standing_ban():
    desk = Desk()
    desk.new_message("Boss", "ORD-053 - 800 polo shirts for UrbanThread, due Apr 10. GiantWeave has shut this week.")
    assert desk.session_excl == {} and desk.stopped == {}


# ---------------------------------------------------------------- an unconfirmed report and other work
def test_one_click_confirm_holds_back_work_for_a_reported_shop():
    desk = Desk()
    d = desk.new_message("Boss", "ORD-066 - 1000 polo shirts, due Apr 20")
    wid = d["recommended"]
    report = desk.new_message("Ravi", f"{desk.name(wid)} has shut.")
    plan = desk.bulk_plan()
    assert d["request_id"] not in plan["confirm"]
    assert any(h["request_id"] == d["request_id"] and h["reason"].startswith("reported stopped") for h in plan["held"])
    assert desk.confirm_all()["confirmed"] == [] and desk.ledger.records == []
    assert any("reported as stopped" in f for f in desk.decisions[d["request_id"]]["flags"])
    desk.mark(report["request_id"], "dismissed")
    assert d["request_id"] in desk.bulk_plan()["confirm"]


def test_a_follow_up_keeps_the_shop_a_message_ruled_out():
    desk = Desk()
    d = desk.new_message("Ravi", "Send the Vest for TrendCart out, GiantWeave has shut")
    new = desk.follow_up(d["request_id"], "ORD-120")
    new = desk.decisions[new["request_id"]]
    assert new["stop_mentions"] == ["W5"] and all(c["workshop_id"] != "W5" for c in new["candidates"])


def test_no_eligible_workshop_stays_open():
    desk = Desk()
    for wid in ("W2", "W4", "W6"):
        desk.mark_stopped(wid)
    d = desk.new_message("Ravi", "ORD-103")
    assert desk.is_open(d) and d["candidates"] == []


def test_the_recorded_tool_call_shows_stopped_shops_were_left_out():
    desk = Desk()
    desk.new_message("Boss", "ORD-053 - 800 polo shirts for UrbanThread, due Apr 10. Boss says nothing new to QuickStitch this week.")
    desk.mark_stopped("W6")
    d = desk.new_message("Boss", "ORD-002 - 1000 crewneck sweaters, due Mar 29")
    calls = [t for t in d["tool_calls"] if isinstance(t.get("input"), dict) and t["input"].get("note") == "session ban lifted"]
    assert calls and "W6" in calls[0]["input"]["exclude"]
    assert all(c["workshop_id"] != "W6" for c in calls[0]["output"])


# ---------------------------------------------------------------- moving a batch keeps the records straight
def two_batches(desk):
    a = desk.new_message("Boss", "ORD-066 - 1000 polo shirts, due Apr 20")
    desk.confirm(a["request_id"], a["recommended"])
    b = desk.new_message("Boss", "ORD-053 - 800 polo shirts for UrbanThread, due Apr 10.")
    desk.confirm(b["request_id"], a["recommended"], accept_late=True)
    return desk.decisions[a["request_id"]], desk.decisions[b["request_id"]]


def test_a_move_keeps_the_audit_trail_of_other_batches():
    desk = Desk()
    a, b = two_batches(desk)
    other = desk.ledger.already_committed("ORD-053")
    before = (other["audit_id"], other["written_at"], other["model_version"])
    target = next(c["workshop_id"] for c in a["candidates"] if c["workshop_id"] != a["confirmed_workshop"])
    desk.reassign(desk.ledger.already_committed("ORD-066")["audit_id"], target, reason="test")
    after = desk.ledger.already_committed("ORD-053")
    assert (after["audit_id"], after["written_at"], after["model_version"]) == before
    assert before[2] != "n/a"
    assert desk.ledger.already_committed("ORD-066")["model_version"] != "n/a"


def test_a_move_updates_the_dates_of_batches_it_frees_up():
    desk = Desk()
    a, b = two_batches(desk)
    target = next(c["workshop_id"] for c in a["candidates"] if c["workshop_id"] != a["confirmed_workshop"])
    desk.reassign(desk.ledger.already_committed("ORD-066")["audit_id"], target, reason="test")
    rec = desk.ledger.already_committed("ORD-053")
    assert desk.decisions[b["request_id"]]["final_estimate"]["promised_date"] == rec["estimate"]["promised_date"]


def test_a_move_moves_the_load_too():
    desk = Desk()
    a, _ = two_batches(desk)
    source = a["confirmed_workshop"]
    target = next(c["workshop_id"] for c in a["candidates"] if c["workshop_id"] != source)
    load = desk.alloc.load[source]
    desk.reassign(desk.ledger.already_committed("ORD-066")["audit_id"], target, reason="test")
    assert desk.alloc.load[source] == load - 1000 and desk.alloc.load[target] == 1000


def test_a_stale_audit_id_is_a_clean_refusal():
    with pytest.raises(ValueError):
        Desk().reassign("A9999", "W5")


def test_confirming_a_closure_needs_a_report():
    desk = Desk()
    d = desk.new_message("Boss", "ORD-066 - 1000 polo shirts, due Apr 20")
    with pytest.raises(ValueError):
        desk.confirm_closure(d["request_id"])
    assert desk.is_open(desk.decisions[d["request_id"]])
