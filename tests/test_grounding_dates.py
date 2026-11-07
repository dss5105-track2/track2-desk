"""Dates a model reads from a message are checked against the text: an ISO date written there is kept,
and a date written only in numbers ("12/4") is not guessed. No API call: the model's answer is given by hand."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "harness")]

from desk.pipeline import Desk  # noqa: E402
from llm.llm_client import empty_request, ground  # noqa: E402


def model_says(text, due):
    r = empty_request()
    r.update(order_id="ORD-053", question_type="allocation", due_date=due)
    return ground(r, text)["due_date"]


def test_an_iso_date_in_the_text_is_kept():
    assert model_says("ORD-053 due 2026-04-12", "2026-04-12") == "2026-04-12"


@pytest.mark.parametrize("due", ["2026-12-04", "2026-04-12"])
def test_a_date_written_only_in_numbers_is_not_guessed(due):
    assert model_says("ORD-053 due 12/4", due) is None


def test_a_named_month_is_still_kept():
    assert model_says("ORD-053 due Apr 12", "2026-04-12") == "2026-04-12"


def test_a_date_not_in_the_text_is_still_dropped():
    assert model_says("ORD-053 needs a shop", "2026-04-12") is None


def fake_model(due):
    """A parser that answers like a model would, then goes through the same grounding."""
    def parse(line, prior=None):
        from llm.llm_client import RuleBasedParser
        r = RuleBasedParser().parse(line, prior)
        r["due_date"], r["parser"] = due, "llm:fake"
        return ground(r, r["raw_text"], prior)
    return parse


def test_the_card_names_an_ambiguous_date_the_model_tried_to_read():
    d = Desk(parser=fake_model("2026-12-04")).new_message("Ravi", "ORD-053 due 12/4")
    assert d["batch"]["due_date"] == "2026-04-10" and any("12/4" in f and "could not read" in f for f in d["flags"])
