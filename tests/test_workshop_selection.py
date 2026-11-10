"""A checkbox prepares one candidate; only an explicit dispatch action books it."""
from copy import deepcopy
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "harness")]

from app.workshop_selection import candidate_from_rows, candidate_widget_key, dispatch_label, reply_draft  # noqa: E402
from desk.pipeline import Desk, inbox_lines  # noqa: E402


def request():
    desk = Desk()
    for line in inbox_lines():
        desk.propose(line)
    desk.refresh_all()
    return desk, desk.decisions["R12"]


@pytest.mark.parametrize("rows", [[], [-1], [100], [0, 1], ["1"]])
def test_invalid_or_multiple_selection_does_not_choose_a_workshop(rows):
    _, decision = request()
    assert candidate_from_rows(decision, rows) is None


def test_selecting_one_candidate_updates_draft_without_changing_decision_or_ledger():
    desk, decision = request()
    before, ledger = deepcopy(decision), deepcopy(desk.ledger.records)
    selected = candidate_from_rows(decision, [1])
    draft = reply_draft(decision, selected)
    assert selected == decision["candidates"][1]
    assert selected["name"] in draft and selected["promised_date"] in draft
    assert selected["worst_date"] in draft and decision["batch"]["due_date"] in draft
    assert f"Cost {selected['cost']:.0f}" in draft
    assert "Awaiting dispatcher confirmation" in draft
    assert decision == before and desk.ledger.records == ledger


def test_default_and_preferred_row_keep_the_original_explanation():
    _, decision = request()
    preferred = next(c for c in decision["candidates"] if c["workshop_id"] == decision["recommended"])
    assert reply_draft(decision, None) == decision["explanation"]
    assert reply_draft(decision, preferred) == decision["explanation"]


def test_late_alternative_keeps_delay_acceptance_in_button_and_draft():
    _, decision = request()
    late = next(c for c in decision["candidates"] if not c["on_time"])
    assert dispatch_label(late).startswith("Accept delay")
    assert late["name"] in dispatch_label(late)
    assert "delay must be accepted" in reply_draft(decision, late)
    assert dispatch_label(None) == "Send to selected workshop"


def test_changed_estimates_or_ranking_reset_row_selection_identity():
    _, decision = request()
    original = candidate_widget_key(decision)
    changed = deepcopy(decision)
    changed["candidates"].reverse()
    assert candidate_widget_key(changed) != original
    changed = deepcopy(decision)
    changed["candidates"][0]["promised_date"] = "2026-04-20"
    assert candidate_widget_key(changed) != original
    changed = deepcopy(decision)
    changed["recommended"] = changed["candidates"][1]["workshop_id"]
    assert candidate_widget_key(changed) != original
