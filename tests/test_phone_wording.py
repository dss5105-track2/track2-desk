"""Wording the rule parser used to misread: curly apostrophes from phone keyboards, 'no more work to X',
and a message that is only a status question."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "harness")]

from desk.pipeline import Desk  # noqa: E402


def card(text):
    return Desk().new_message("Boss", text)


# ---------------------------------------------------------------- ruling a workshop out
@pytest.mark.parametrize("text", ["Don’t send anything new to QuickStitch, and ORD-053 needs a shop",
                                  "Don‘t give QuickStitch more new orders, and please send out ORD-053",
                                  "Don't send anything new to QuickStitch, and ORD-053 needs a shop",
                                  "No more work to QuickStitch; ORD-053 needs a shop",
                                  "No new orders for QuickStitch. ORD-053 needs a shop"])
def test_ruling_a_workshop_out_is_never_read_as_asking_for_it(text):
    d = card(text)
    assert d["parsed"]["forced_workshop"] != "W1" and "W1" in d["parsed"]["excluded_workshops"] and d["recommended"] != "W1"


def test_curly_quotes_read_like_straight_ones():
    straight, curly = card("Don't use BudgetWorks for ORD-066"), card("Don’t use BudgetWorks for ORD-066")
    assert (curly["parsed"]["excluded_workshops"], curly["recommended"]) == (straight["parsed"]["excluded_workshops"], straight["recommended"])


def test_a_request_with_a_curly_apostrophe_still_asks_for_the_shop():
    d = card("ORD-066 to BudgetWorks, it’s urgent")
    assert d["parsed"]["forced_workshop"] == "W3"


# ---------------------------------------------------------------- a message that only asks how an order is doing
@pytest.mark.parametrize("text", ["Is ORD-041 done?", "Has ORD-041 shipped?", "Where is ORD-041?", "When will ORD-041 be back?",
                                  "Is ORD-041 on track?", "Did ORD-041 go out?", "Who has ORD-041?", "Are ORD-041 and ORD-045 done?",
                                  "Where’s ORD-041?"])
def test_a_status_question_alone_gets_no_recommendation(text):
    desk = Desk()
    d = desk.new_message("Ravi", text)
    assert len(desk.decisions) == 1 and d["subtype"] == "not_in_data" and d["recommended"] is None
    assert d["request_id"] not in desk.bulk_plan()["confirm"]


@pytest.mark.parametrize("text", ["Who should take ORD-041?", "Which shop for ORD-041?", "Can you find a shop for ORD-041?",
                                  "ORD-041 needs a shop?", "Can ORD-041 go to Little Loom?", "Is ORD-041 ready to ship?"])
def test_a_question_asking_for_a_dispatch_is_still_a_dispatch(text):
    d = card(text)
    assert d["subtype"] != "not_in_data" and d["recommended"] is not None


def test_two_orders_in_a_status_question_name_the_other():
    d = card("Are ORD-041 and ORD-045 done?")
    assert any("ORD-045" in f for f in d["flags"])


def test_a_curly_dont_before_several_orders_is_not_split_into_dispatches():
    desk = Desk()
    d = desk.new_message("Boss", "Don’t send ORD-053 and ORD-066 today")
    assert len(desk.decisions) == 1 and d["recommended"] is None
