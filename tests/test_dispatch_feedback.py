"""UI regression coverage for the issues observed in human testing tasks 5–7."""
import json
from copy import deepcopy
from pathlib import Path
import sys

import pytest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "harness")]

from app.dispatch_feedback import (  # noqa: E402
    change_tables, collect_change_report, order_labels, risk_label, take_change_report,
)
from desk.pipeline import Desk, inbox_lines  # noqa: E402


def morning(confirm=False):
    desk = Desk()
    for line in inbox_lines():
        desk.propose(line)
    if confirm:
        desk.confirm_all()
        desk.confirm("R12", desk.decisions["R12"]["recommended"], accept_late=True)
    desk.last_change = None  # previous notices have already been read in this fixture
    return desk


def app(desk, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("DESK_LLM_API_KEY", raising=False)
    at = AppTest.from_file(str(ROOT / "app" / "streamlit_app.py"), default_timeout=60)
    at.session_state["desk"] = desk
    at.session_state["use_llm"] = False
    at.session_state["llm_client"] = None
    at.session_state["selected"] = None
    at.run()
    assert not at.exception
    return at


def inbox(at):
    return next(frame.value for frame in at.dataframe if "Customer" in frame.value.columns)


def rerun(at):
    # Streamlit 1.50 AppTest represents single-select segmented controls as a
    # multi-value ButtonGroup. Supply the current selection as a one-item list.
    for widget in at.get("button_group"):
        if isinstance(widget.value, str):
            widget.set_value([widget.value])
    at.run()
    assert not at.exception


def notice_text(at):
    return "\n".join(element.value for kind in (at.info, at.warning) for element in kind
                     if "open request" in element.value and "updated." in element.value)


def test_reports_are_copied_consumed_once_and_not_replayed():
    desk, state = morning(), {}
    original = desk.lift_constraint("W1")["changes"]
    collect_change_report(desk, state)
    saved = deepcopy(state["last_change_report"])
    assert desk.last_change is None
    assert take_change_report(state) == saved
    assert take_change_report(state) is None
    original["open_changed"].clear()
    assert state["last_change_report"] == saved
    collect_change_report(desk, state)
    assert take_change_report(state) is None


def test_markers_survive_inspection_but_clear_after_next_action_or_reset():
    desk, state = morning(), {}
    desk.lift_constraint("W1")
    collect_change_report(desk, state)
    ids = state["changed_request_ids"]
    assert ids
    take_change_report(state)
    desk.refresh_all()
    collect_change_report(desk, state)
    assert state["changed_request_ids"] == ids
    desk.new_message("Chen", "ORD-066 needs a workshop.")
    collect_change_report(desk, state)
    assert state["changed_request_ids"] == ()
    collect_change_report(Desk(), state)
    assert "last_change_report" not in state


def test_report_tables_keep_names_risks_and_ledger_unchanged():
    desk = morning(confirm=True)
    ledger = deepcopy(desk.ledger.records)
    report = desk.lift_constraint("W1")["changes"]
    changed, dispatched = change_tables(report, desk.name)
    assert len(changed) == len(report["open_changed"]) > 0
    for shown, raw in zip(changed, report["open_changed"]):
        wid = raw["after"]["recommended"]
        assert shown["After workshop"] == (desk.name(wid) if wid else "No recommendation")
    r12 = next(row for row in dispatched if row["Request"] == "R12")
    assert "Late if reworked" in r12["Risks"]
    assert "Sat 11 Apr" in r12["Risks"] and "Fri 10 Apr" in r12["Risks"]
    assert desk.ledger.records == ledger


def test_report_handles_a_change_to_no_recommendation():
    report = {"open_changed": [{"request_id": "H1", "order_id": None,
              "before": {"subtype": "allocate", "recommended": "W1"},
              "after": {"subtype": "needs_reply", "recommended": None}}], "dispatched": []}
    changed, _ = change_tables(report, lambda wid: "QuickStitch")
    assert changed[0]["Order"] == "" and changed[0]["After workshop"] == "No recommendation"


@pytest.mark.parametrize("order_id", [None, "", "ORD-999"])
def test_missing_order_has_blank_customer_and_product(order_id):
    assert order_labels(order_id, Desk().O) == ("", "")


def test_customer_product_come_from_the_order_book():
    desk = Desk()
    assert order_labels("ORD-053", desk.O) == (desk.O["ORD-053"].customer, desk.O["ORD-053"].product)


def test_unfamiliar_risk_text_is_not_lost():
    text = "GiantWeave is stopped; move the batch under Workshops"
    assert risk_label(text) == text


def test_lift_notice_and_markers_have_separate_lifetimes(monkeypatch):
    desk = morning(confirm=True)
    ledger = deepcopy(desk.ledger.records)
    at = app(desk, monkeypatch)
    at.button(key="lift_W1").click()
    rerun(at)
    assert not at.exception
    report = at.session_state["last_change_report"]
    assert "lifted the constraint on QuickStitch" == report["cause"]
    assert desk.last_change is None
    text = notice_text(at)
    assert "Already-dispatched batches are not changed automatically" in text
    assert "R12" in text and "Sat 11 Apr" in text and "Reassign" in text
    assert at.session_state["changed_request_ids"]
    assert any(inbox(at)["Update"])
    assert desk.ledger.records == ledger

    rerun(at)  # passive rerun: the notice is gone, the changed-row markers remain
    assert not at.exception and notice_text(at) == ""
    assert at.session_state["changed_request_ids"]
    at.text_area(key="dispatch_message").set_value("ORD-066 needs a workshop.")
    next(button for button in at.button if button.label == "Send").click()
    rerun(at)
    assert not at.exception
    assert at.session_state["changed_request_ids"] == ()
    assert notice_text(at) == ""
    assert desk.ledger.records == ledger


def test_a_ban_message_reports_and_refreshes_the_same_cards(monkeypatch):
    desk = morning()
    at = app(desk, monkeypatch)
    at.text_area(key="dispatch_message").set_value("Nothing new to GiantWeave this week.")
    next(button for button in at.button if button.label == "Send").click()
    rerun(at)
    assert not at.exception
    report = at.session_state["last_change_report"]
    assert "GiantWeave" in report["cause"] and report["open_changed"]
    assert desk.last_change is None and notice_text(at)
    for row in report["open_changed"]:
        assert row["after"]["recommended"] == desk.decisions[row["request_id"]]["recommended"]


def test_stop_and_reopen_each_produce_feedback_without_moving_batches(monkeypatch):
    desk = morning(confirm=True)
    ledger = deepcopy(desk.ledger.records)
    at = app(desk, monkeypatch)
    at.button(key="nav_workshops").click()
    rerun(at)
    next(widget for widget in at.selectbox if widget.label == "Workshop").select("W5")
    next(button for button in at.button if button.label == "Mark as stopped").click()
    rerun(at)
    assert not at.exception
    assert at.session_state["last_change_report"]["cause"] == "marked GiantWeave as stopped"
    assert at.session_state["page"] == "workshops"
    assert "R12" in notice_text(at)
    assert not any("re-ranked" in item.value for item in at.success)
    assert "pending_change_report" not in at.session_state
    # AppTest 1.50 retains the selectbox from before its options changed.
    # Set the next valid selection explicitly before serializing another run.
    at.selectbox(key="stop_workshop").select("W1")
    at.button(key="nav_dispatch").click()
    rerun(at)
    assert notice_text(at) == ""
    assert at.session_state["changed_request_ids"]
    at.button(key="nav_workshops").click()
    rerun(at)
    at.button(key="reopen_W5").click()
    rerun(at)
    assert not at.exception
    assert at.session_state["last_change_report"]["cause"] == "reopened GiantWeave"
    assert at.session_state["page"] == "workshops"
    assert "Reopened GiantWeave" in notice_text(at)
    assert desk.last_change is None and desk.ledger.records == ledger


@pytest.mark.parametrize("page", ["workshops", "audit", "simulator", "evaluation"])
def test_sidebar_change_is_shown_on_current_page_and_not_replayed_in_dispatch(page, monkeypatch):
    desk = morning(confirm=True)
    ledger = deepcopy(desk.ledger.records)
    at = app(desk, monkeypatch)
    at.button(key=f"nav_{page}").click()
    rerun(at)
    at.button(key="lift_W1").click()
    rerun(at)
    assert at.session_state["page"] == page
    assert "Lifted the constraint on QuickStitch" in notice_text(at)
    assert "R12" in notice_text(at) and "Reassign" in notice_text(at)
    assert not any("re-ranked" in item.value for item in at.success)
    ids = at.session_state["changed_request_ids"]
    assert ids and desk.last_change is None
    assert "pending_change_report" not in at.session_state
    at.button(key="nav_dispatch").click()
    rerun(at)
    assert notice_text(at) == ""
    assert at.session_state["changed_request_ids"] == ids
    assert any(inbox(at)["Update"])
    assert desk.ledger.records == ledger


def test_inbox_exposes_customer_product_refused_hint_and_tight_warning(monkeypatch):
    desk = morning()
    at = app(desk, monkeypatch)
    rows = inbox(at)
    for _, row in rows.iterrows():
        assert (row["Customer"], row["Product"]) == order_labels(row["Order"], desk.O)
    assert any("⚠ tight" in value for value in rows["Decision"])
    assert not any(widget.label == "Or choose" for widget in at.selectbox)
    selected = at.session_state["selected"]
    assert at.button(key=f"altb_{selected}").disabled
    assert not any("Refused requests" in caption.value for caption in at.caption)
    at.session_state["group"] = "decide"
    rerun(at)
    assert any("Refused requests → Needs a decision" in caption.value for caption in at.caption)


def test_navigation_keeps_dispatch_state_and_hides_unrelated_controls(monkeypatch):
    desk = morning(confirm=True)
    at = app(desk, monkeypatch)
    ledger = deepcopy(desk.ledger.records)
    assert at.text_area(key="dispatch_message")
    for page, heading in [("audit", "Ledger"), ("workshops", "Workshop register"),
                          ("simulator", "Shared simulator · 120 orders replayed"), ("evaluation", "Evaluation")]:
        at.button(key=f"nav_{page}").click()
        rerun(at)
        assert not at.text_area
        assert any(element.value == heading for element in at.subheader)
        at.button(key="nav_dispatch").click()
        rerun(at)
        assert at.text_area(key="dispatch_message")
        assert desk.ledger.records == ledger


def test_compact_notice_has_one_details_section_and_no_empty_dispatched_section(monkeypatch):
    desk = morning()
    at = app(desk, monkeypatch)
    at.button(key="lift_W1").click()
    rerun(at)
    assert "updated." in notice_text(at)
    assert "dispatched" not in notice_text(at).lower()
    assert len([exp for exp in at.expander if exp.label == "View changes"]) == 1
    assert not any("Lifted the constraint" in item.value for item in at.success)


def test_order_table_expansion_keeps_selection_and_never_dispatches(monkeypatch):
    desk = morning()
    at = app(desk, monkeypatch)
    selected = at.session_state["selected"]
    ledger = deepcopy(desk.ledger.records)
    for _ in range(3):
        assert at.button(key="toggle_order_table").label == "Expand table"
        at.button(key="toggle_order_table").click()
        rerun(at)
        assert at.session_state["orders_expanded"] is True
        assert at.button(key="toggle_order_table").label == "Close expanded table"
        assert at.session_state["selected"] == selected
        assert desk.ledger.records == ledger
        at.button(key="toggle_order_table").click()
        rerun(at)
        assert at.session_state["orders_expanded"] is False
        assert at.session_state["selected"] == selected
        assert desk.ledger.records == ledger


def test_left_alignment_preserves_numeric_types_and_display_formats(monkeypatch):
    desk = morning()
    before = deepcopy(desk.ledger.records)
    at = app(desk, monkeypatch)
    queues = next(frame for frame in at.dataframe if {"Workshop", "Queue", "Sent"} <= set(frame.value.columns))
    candidates = next(frame for frame in at.dataframe if {"Workshop", "Cost", "Days"} <= set(frame.value.columns))
    assert queues.value["Queue"].dtype.kind == "f"
    assert queues.value["Sent"].dtype.kind in "iu"
    assert candidates.value["Cost"].dtype.kind in "iu"
    assert candidates.value["Days"].dtype.kind == "f"
    config = json.loads(queues.proto.columns)
    assert config["Queue"]["type_config"]["format"] == "%.1f"
    assert config["Sent"]["type_config"]["format"] == "%d"
    for frame in at.dataframe:
        config = json.loads(frame.proto.columns)
        assert all(config[str(name)]["alignment"] == "left" for name in frame.value.columns)
    assert desk.ledger.records == before
