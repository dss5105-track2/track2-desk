"""User testing (task 7, both testers): after a constraint changes, the dispatcher could not see what changed, and expected
dispatched batches to update. The desk now reports which open requests changed, and which dispatched batches were left
alone and whether any of them is now at risk."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "harness")]

from desk.pipeline import Desk  # noqa: E402


def morning(confirm=True):
    desk = Desk()
    for line in (ROOT / "data/dispatch_requests.txt").read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.startswith("#"):
            desk.propose(line)
    if confirm:
        desk.confirm_all()
        desk.confirm("R12", desk.decisions["R12"]["recommended"], accept_late=True)
    return desk


def test_lifting_a_constraint_lists_the_open_requests_that_changed():
    desk = morning()
    desk.refresh_all()      # as the interface does on every page: changes from the confirmations above are not the lift's
    before = {k: d["recommended"] for k, d in desk.decisions.items() if desk.is_open(d)}
    report = desk.lift_constraint("W1")["changes"]
    changed = {c["request_id"]: c for c in report["open_changed"]}
    assert changed and set(changed) == {k for k, w in before.items() if desk.decisions[k]["recommended"] != w}
    c = next(iter(changed.values()))
    assert c["before"]["recommended"] == before[c["request_id"]] and c["after"]["recommended"] == desk.decisions[c["request_id"]]["recommended"]
    assert "QuickStitch" in report["cause"] and desk.last_change is report


def test_dispatched_batches_are_listed_as_not_changed():
    desk = morning()
    report = desk.lift_constraint("W1")["changes"]
    dispatched = {d["request_id"]: d for d in report["dispatched"]}
    assert "R12" in dispatched and len(dispatched) == sum(1 for r in desk.ledger.records if r["status"] == "committed")
    assert desk.decisions["R12"]["recommended"] == dispatched["R12"]["workshop_id"]


def test_a_tight_dispatched_batch_is_at_risk():
    desk = morning()
    report = desk.lift_constraint("W1")["changes"]
    r12 = next(d for d in report["dispatched"] if d["request_id"] == "R12")
    assert any("late if reworked" in r for r in r12["risks"])


def test_stopping_a_workshop_puts_its_dispatched_batches_at_risk():
    desk = morning()
    wid = desk.decisions["R12"]["committed"] and next(r["workshop_id"] for r in desk.ledger.records if r["request_id"] == "R12")
    desk.mark_stopped(wid)
    r12 = next(d for d in desk.last_change["dispatched"] if d["request_id"] == "R12")
    assert any("stopped" in r for r in r12["risks"]) and desk.name(wid) in desk.last_change["cause"]


def test_a_new_ban_in_a_message_is_reported_too():
    desk = morning()
    wid = next(r["workshop_id"] for r in desk.ledger.records if r["request_id"] == "R12")
    desk.new_message("Boss", f"Nothing new to {desk.name(wid)} this week.")
    report = desk.last_change
    assert desk.name(wid) in report["cause"]
    r12 = next(d for d in report["dispatched"] if d["request_id"] == "R12")
    assert any("no new work" in r for r in r12["risks"])


def test_nothing_changed_gives_empty_lists():
    desk = morning(confirm=False)
    report = desk.lift_constraint("W7")["changes"]          # no constraint on OldMill: nothing to lift
    assert report["open_changed"] == [] and report["dispatched"] == []


def test_a_lift_right_after_a_ban_message_reports_against_fresh_cards():
    """A ban said in a message is only previewed; lifting it must compare against re-ranked cards, as the interface shows them."""
    def run(refresh_first):
        desk = morning(confirm=False)
        desk.new_message("Boss", "Don’t send anything new to GiantWeave this week, and ORD-053 needs a shop")
        if refresh_first:
            desk.refresh_all()
        return {c["request_id"] for c in desk.lift_constraint("W5")["changes"]["open_changed"]}
    assert run(False) == run(True) and len(run(True)) > 1
