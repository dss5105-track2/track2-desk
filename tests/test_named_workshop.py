"""A message names a workshop that can take the batch, but another is recommended: the card says so, and why.
The recommendation itself does not change; the dispatcher can still send it to the named workshop."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "harness")]

import pytest  # noqa: E402

from desk.pipeline import Desk  # noqa: E402


def card(text):
    return Desk().new_message("Ravi", text)


def candidate(d, wid):
    return next(c for c in d["candidates"] if c["workshop_id"] == wid)


def ranking(order):
    """Candidates for an order with no workshop named, best first."""
    return card(f"{order} needs a shop")["candidates"]


def test_a_named_workshop_that_would_be_late_is_explained():
    d = card("Send ORD-053 to BudgetWorks")
    named = candidate(d, "W3")
    assert d["recommended"] != "W3" and not named["on_time"]
    note = next(f for f in d["flags"] if "asked for BudgetWorks" in f)
    assert named["promised_date"] in note and "late" in note
    assert "You asked for BudgetWorks" in d["explanation"] and d["number_check"]["ok"]


def test_a_named_workshop_that_is_on_time_but_ranked_lower_is_explained():
    order = "ORD-066"
    lower = next(c for c in ranking(order)[1:] if c["on_time"])
    d = card(f"Send {order} to {lower['name']}")
    assert d["recommended"] != lower["workshop_id"]
    note = next(f for f in d["flags"] if f"asked for {lower['name']}" in f)
    assert "also be on time" in note and lower["promised_date"] in note and "use_slack" in note
    assert d["number_check"]["ok"]


def test_the_recommendation_does_not_change():
    plain, named = card("ORD-053 needs a shop"), card("Send ORD-053 to BudgetWorks")
    assert named["recommended"] == plain["recommended"] and named["subtype"] == plain["subtype"]


def test_a_named_workshop_that_is_recommended_adds_nothing():
    best = ranking("ORD-066")[0]
    d = card(f"Send ORD-066 to {best['name']}")
    assert d["recommended"] == best["workshop_id"] and not any("asked for" in f for f in d["flags"])


def test_the_note_never_tells_the_dispatcher_to_send_it_there():
    d = card("Send ORD-053 to BudgetWorks")
    assert not any("send it to" in f.lower() for f in d["flags"])


@pytest.mark.parametrize("text", ["Don’t give BudgetWorks anything new, and ORD-053 needs a shop",
                                  "Don‘t use BudgetWorks. ORD-053 needs a shop",
                                  "No more work to BudgetWorks; ORD-053 needs a shop",
                                  "ORD-053 needs a shop, avoid BudgetWorks"])
def test_no_note_when_the_message_may_be_saying_not_to_use_it(text):
    d = card(text)
    assert not any(f.startswith("asked for") for f in d["flags"]) and "You asked for" not in d["explanation"]


def test_a_named_workshop_that_cannot_take_it_reads_as_before():
    d = card("Send ORD-035 to QuickStitch")
    assert d["subtype"] == "ineligible_suggestion" and not any("asked for" in f for f in d["flags"])


def test_no_on_time_option_with_a_named_later_workshop():
    desk = Desk()
    for line in (ROOT / "data/dispatch_requests.txt").read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.startswith("#"):
            desk.propose(line)
    late = next(d for d in desk.decisions.values() if d["subtype"] == "no_on_time_option" and len(d["candidates"]) > 1)
    other = late["candidates"][1]
    d = Desk().new_message("Ravi", f"Send {late['order_id']} to {other['name']}")
    assert d["subtype"] == "no_on_time_option" and d["recommended"] != other["workshop_id"]
    note = next(f for f in d["flags"] if f"asked for {other['name']}" in f)
    assert other["promised_date"] in note and "earliest" in note and d["number_check"]["ok"]
