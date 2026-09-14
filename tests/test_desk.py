"""Dispatcher workflow tests: nothing is written until a human confirms.

    python tests/test_desk.py      or      python -m pytest tests/ -q
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from desk.pipeline import Desk, inbox_lines  # noqa: E402


def loaded() -> Desk:
    desk = Desk()
    for ln in inbox_lines():
        desk.propose(ln)
    return desk


def test_propose_writes_nothing():
    desk = loaded()
    assert len(desk.decisions) == 30
    assert desk.ledger.records == []
    assert desk.decisions["R09"]["status"] == "awaiting_confirmation"
    assert desk.decisions["R16"]["status"] == "needs_reply"
    assert desk.decisions["R18"]["status"] == "answered"
    assert desk.session_excl["W1"]["by"] == "Boss"


def test_open_requests_follow_the_ledger():
    desk = loaded()
    assert desk.decisions["R12"]["recommended"] == "W6"        # nothing confirmed yet: Nimble Needle
    desk.confirm("R09")
    r12 = desk.refresh("R12")
    assert r12["recommended"] == "W5"                          # after R09 goes to Nimble Needle: GiantWeave
    assert any("updated since received" in f for f in r12["flags"])


def test_late_needs_explicit_acceptance():
    desk = loaded()
    try:
        desk.confirm("R06")
        assert False, "a late dispatch must not commit without accept_late"
    except ValueError as ex:
        assert "late" in str(ex)
    rec = desk.confirm("R06", accept_late=True)
    assert rec["workshop_id"] == "W6" and rec["estimate"]["late_days"] == 4
    assert desk.decisions["R06"]["status"] == "committed"


def test_refused_suggestion_uses_alternative():
    desk = loaded()
    rec = desk.confirm("R08")
    assert rec["workshop_id"] == "W6" and rec["estimate"]["on_time"]


def test_cannot_confirm_ineligible_or_excluded():
    desk = loaded()
    for wid in ("W8", "W7"):
        try:
            desk.confirm("R08", wid)
            assert False
        except ValueError:
            pass
    try:
        desk.confirm("R25", "W1")                                  # Boss's session ban
        assert False
    except ValueError as ex:
        assert "lift" in str(ex)


def test_lifting_the_ban_changes_r21():
    desk = loaded()
    desk.confirm("R09")
    desk.confirm("R12")
    assert desk.refresh("R21")["subtype"] == "no_on_time_option"
    desk.lift_constraint("W1")
    r21 = desk.decisions["R21"]
    assert r21["subtype"] == "allocate" and r21["recommended"] == "W1"
    assert desk.actions[-1]["action"] == "lift_constraint"


def test_follow_up_resolves_ambiguous_request():
    desk = loaded()
    new = desk.follow_up("R03", "ORD-020")
    assert desk.decisions["R03"]["status"] == "reply_sent"
    assert new["order_id"] == "ORD-020" and new["subtype"] == "no_on_time_option"
    assert new["request_id"].startswith("H")


def test_mark_and_reassign_are_logged():
    desk = loaded()
    desk.mark("R16", "reply_sent", note="asked Chen")
    rec = desk.confirm("R09")
    new = desk.reassign(rec["audit_id"], "W8", reason="FreshStart has idle capacity")
    assert new["workshop_id"] == "W8"
    assert desk.decisions["R09"]["confirmed_workshop"] == "W8"
    assert [a["action"] for a in desk.actions] == ["reply_sent", "confirm", "reassign"]


def test_unattended_replay_still_matches_cli():
    desk = Desk()
    for ln in inbox_lines():
        desk.handle(ln)
    assert [r["request_id"] for r in desk.ledger.records] == ["R09", "R12", "R25"]


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
