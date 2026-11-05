"""One message, two problems: a repeat dispatch or finished order, and a workshop that cannot take it.
The dispatcher sees both and decides. Neither hides the other, and nothing is committed by itself."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "harness")]

import desk.pipeline as pipeline  # noqa: E402
from desk.pipeline import Desk  # noqa: E402


def already_sent(order="ORD-035"):
    desk = Desk()
    d = desk.new_message("Ravi", f"{order} needs a shop")
    desk.confirm(d["request_id"], d["recommended"], accept_late=True)
    return desk


def assert_both(d, shop, why):
    assert d["subtype"] == "state_conflict" and d["official_behaviour"] == "clarify"
    assert "already dispatched" in d["explanation"] and shop in d["explanation"] and why in d["explanation"]
    assert d["refused_workshop"] is not None and d["recommended"] is None and d["number_check"]["ok"]


def test_repeat_and_a_shop_that_cannot_make_it():
    d = already_sent().new_message("Ravi", "Send ORD-035 to QuickStitch")
    assert_both(d, "QuickStitch", "cannot make ACCESSORIES")


def test_repeat_and_a_batch_over_the_limit():
    desk = already_sent("ORD-010")
    small = next(w for w in desk.W.values() if "TOPS" in w.makes and w.max_batch and w.max_batch < 1000)
    d = desk.new_message("Ravi", f"Send ORD-010 to {small.name}")
    assert_both(d, small.name, f"{small.max_batch}-piece limit")


def test_repeat_and_a_banned_shop():
    desk = already_sent("ORD-010")
    desk.new_message("Boss", "Nothing new to QuickStitch this week.")
    d = desk.new_message("Ravi", "Send ORD-010 to QuickStitch")
    assert_both(d, "QuickStitch", "said nothing new goes to it")


def test_repeat_and_a_stopped_shop():
    desk = already_sent("ORD-010")
    desk.mark_stopped("W1")
    d = desk.new_message("Ravi", "Send ORD-010 to QuickStitch")
    assert_both(d, "QuickStitch", "reported as stopped")


def test_repeat_and_a_shop_this_message_says_has_stopped():
    d = already_sent("ORD-010").new_message("Ravi", "Send ORD-010 to QuickStitch, QuickStitch has shut.")
    assert d["subtype"] == "state_conflict" and "already dispatched" in d["explanation"]
    assert "QuickStitch" in d["explanation"] and "reported as stopped" in d["explanation"] and d["recommended"] is None


def test_finished_order_and_a_shop_that_cannot_make_it():
    d = Desk().new_message("Ravi", "Send ORD-110 to QuickStitch")
    assert d["subtype"] == "state_conflict" and "COMPLETE" in d["explanation"] and "cannot make ACCESSORIES" in d["explanation"]


def test_every_state_conflict_is_named(monkeypatch):
    monkeypatch.setattr(pipeline, "state_checks", lambda *a, **k: ["order already COMPLETE on 2026-04-01", "already dispatched to W1 by H01 (A0001)"])
    d = Desk().new_message("Ravi", "ORD-053 needs a shop")
    assert "COMPLETE" in d["explanation"] and "already dispatched" in d["explanation"]


def test_a_shop_that_can_take_it_adds_nothing():
    d = already_sent("ORD-010").new_message("Ravi", "Send ORD-010 to SteadyHands")
    assert d["subtype"] == "state_conflict" and "can't take" not in d["explanation"] and d["refused_workshop"] is None


def test_a_repeat_with_no_shop_reads_as_before():
    d = already_sent("ORD-010").new_message("Ravi", "ORD-010 needs a shop")
    assert d["explanation"].startswith("Before I place ORD-010: already dispatched") and d["explanation"].endswith("Do you still want it sent outside?")


def test_a_refusal_without_a_repeat_reads_as_before():
    d = Desk().new_message("Ravi", "Send ORD-035 to QuickStitch")
    assert d["subtype"] == "ineligible_suggestion" and d["explanation"].startswith("QuickStitch can't take ORD-035: cannot make ACCESSORIES") and d["recommended"]


def test_it_cannot_be_committed_or_bulk_confirmed():
    desk = already_sent()
    d = desk.new_message("Ravi", "Send ORD-035 to QuickStitch")
    assert d["request_id"] not in desk.bulk_plan()["confirm"]
    with pytest.raises(ValueError):
        desk.confirm(d["request_id"], "W2")


def test_each_order_in_one_message_is_checked_alone():
    desk = already_sent("ORD-035")
    desk.new_message("Ravi", "Send ORD-035 and ORD-041 to QuickStitch")
    ds = {d["order_id"]: d for d in desk.decisions.values() if d["status"] != "dispatched" and d["parsed"].get("source_message")}
    assert ds["ORD-035"]["subtype"] == "state_conflict" and "cannot make ACCESSORIES" in ds["ORD-035"]["explanation"]
    assert ds["ORD-041"]["subtype"] == "ineligible_suggestion"
