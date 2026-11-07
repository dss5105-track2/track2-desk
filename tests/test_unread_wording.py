"""Messages the rule parser used to act on wrongly or without a word: cancellations, dates and quantities it cannot read,
order numbers without a hyphen, and short status questions."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "harness")]

from desk.pipeline import Desk  # noqa: E402


def card(text, desk=None):
    desk = desk or Desk()
    return desk.new_message("Ravi", text)


# ---------------------------------------------------------------- cancelling is not dispatching
@pytest.mark.parametrize("text", ["Cancel ORD-053", "ORD-053 customer cancelled", "Undo the ORD-053 dispatch",
                                  "ORD-053 is called off", "We no longer need ORD-053"])
def test_a_cancellation_gets_a_question_and_no_recommendation(text):
    desk = Desk()
    d = card(text, desk)
    assert d["official_behaviour"] == "clarify" and d["recommended"] is None and not d["candidates"]
    assert "cancel" in d["explanation"].lower() and d["request_id"] not in desk.bulk_plan()["confirm"]


def test_a_cancellation_of_a_dispatched_order_points_to_the_dispatch():
    desk = Desk()
    first = card("ORD-053 needs a shop", desk)
    desk.confirm(first["request_id"], first["recommended"])
    d = card("Cancel ORD-053", desk)
    assert d["recommended"] is None and "already dispatched" in d["explanation"]


def test_a_request_that_mentions_no_cancellation_is_unchanged():
    assert card("ORD-053 needs a shop, don't let it slip")["recommended"] is not None


# ---------------------------------------------------------------- dates and quantities it cannot read are said, not dropped
def test_an_iso_date_is_read():
    d = card("ORD-053 due 2026-04-12")
    assert d["batch"]["due_date"] == "2026-04-12"


@pytest.mark.parametrize("text, said", [("ORD-053 due next Friday", "next Friday"), ("ORD-053 due end of month", "end of month"),
                                        ("ORD-053 by tomorrow", "tomorrow"), ("ORD-053 due 12/4", "12/4")])
def test_an_unread_date_is_named_on_the_card(text, said):
    d = card(text)
    assert d["batch"]["due_date"] == "2026-04-10"
    assert any(said in f and "could not read" in f for f in d["flags"])


@pytest.mark.parametrize("text, said", [("ORD-053, 1,000 pcs", "1,000 pcs"), ("ORD-053 eight hundred polos", "eight hundred")])
def test_an_unread_quantity_is_named_on_the_card(text, said):
    d = card(text)
    assert d["batch"]["pieces"] == 800 and any(said in f and "could not read" in f for f in d["flags"])


def test_a_read_date_and_quantity_add_no_note():
    d = card("ORD-053 - 500 polo shirts, due Apr 12")
    assert not any("could not read" in f for f in d["flags"])


# ---------------------------------------------------------------- order numbers
@pytest.mark.parametrize("text", ["ORD053 needs a shop", "ORD 053 needs a shop", "ord-053 needs a shop"])
def test_an_order_number_without_a_hyphen_is_read(text):
    assert card(text)["order_id"] == "ORD-053"


def test_a_new_quantity_is_not_read_as_a_range_of_orders():
    d = card("Change ORD-053 to 600 pieces")
    assert not any("may name more orders" in f for f in d["flags"])


def test_a_real_range_is_still_flagged():
    d = card("ORD-050 to ORD-053 need shops")
    assert any("may name more orders" in f for f in d["flags"])


# ---------------------------------------------------------------- short status questions
@pytest.mark.parametrize("text", ["ORD-041 done?", "any update on ORD-041", "Any updates on ORD-041?", "ORD-041 finished yet?",
                                  "news on ORD-041?"])
def test_short_status_questions_get_no_recommendation(text):
    d = card(text)
    assert d["subtype"] == "not_in_data" and d["recommended"] is None


@pytest.mark.parametrize("text", ["ORD-041 needs a shop?", "ORD-041 ready to ship?", "ORD-041 to Little Loom?"])
def test_short_dispatch_questions_still_dispatch(text):
    assert card(text)["recommended"] is not None
