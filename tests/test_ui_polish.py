"""Interface polish found while rehearsing the demo: inbox progress, sidebar buttons, links between the orders of one message."""
from pathlib import Path
import sys

from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "harness")]

from desk.pipeline import Desk  # noqa: E402


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


def rerun(at):
    for widget in at.get("button_group"):        # Streamlit 1.50 AppTest: single-select segmented control as a list
        if isinstance(widget.value, str):
            widget.set_value([widget.value])
    at.run()
    assert not at.exception


def test_loading_the_inbox_still_reads_all_thirty_messages(monkeypatch):
    desk = Desk()
    at = app(desk, monkeypatch)
    next(b for b in at.button if b.label == "Load morning inbox").click()
    rerun(at)
    assert sum(1 for k in desk.decisions if k.startswith("R")) == 30
    assert not at.get("progress"), "the progress bar is removed once the inbox is read"


def test_the_other_order_of_a_message_opens_with_one_click(monkeypatch):
    desk = Desk()
    at = app(desk, monkeypatch)
    nd = desk.new_message("Boss", "ORD-066 and ORD-035 need shops")
    at.session_state["selected"] = nd["request_id"]
    rerun(at)
    assert at.session_state["selected"] == "H01"
    link = next(b for b in at.button if b.key == "sib_H01_H02")
    assert link.label.startswith("H02") and "ORD-035" in link.label
    link.click()
    rerun(at)
    assert at.session_state["selected"] == "H02"
    assert any(b.key == "sib_H02_H01" for b in at.button), "the second card links back to the first"
    assert not any(r["status"] == "committed" for r in desk.ledger.records), "opening a card never dispatches"


def test_a_link_beats_a_stale_row_selection(monkeypatch):
    desk = Desk()
    at = app(desk, monkeypatch)
    desk.new_message("Boss", "ORD-066 and ORD-035 need shops")
    at.session_state["selected"] = "H01"
    rerun(at)
    before = at.session_state["jump_n"] if "jump_n" in at.session_state else 0
    next(b for b in at.button if b.key == "sib_H01_H02").click()
    rerun(at)
    assert at.session_state["jump_n"] == before + 1
    assert at.session_state["selected"] == "H02"


def test_sidebar_buttons_keep_their_words():
    css = (ROOT / "app" / "desk_layout.css").read_text(encoding="utf-8")
    assert '[class*="st-key-lift_"] button' in css and "min-width" in css
    assert ".st-key-session_actions button p { white-space: normal" in css
