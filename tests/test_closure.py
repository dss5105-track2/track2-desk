"""A workshop stops: spotted from the queue in the simulator, reported in chat at the desk."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "harness"))

from desk.pipeline import Desk, inbox_lines  # noqa: E402
from kernel.allocator import Allocator  # noqa: E402
from kernel.closure import ClosureAwareAllocator, QueueWatch  # noqa: E402
from simulate import Simulator  # noqa: E402


def test_watch_ignores_a_queue_a_rework_can_explain():
    watch = QueueWatch()
    watch.observe(0, {"W1": 2.0})
    watch.dispatched("W1", 4.0)              # worst case: 2 + 4 x 1.5 = day 8
    assert watch.observe(1, {"W1": 7.0}) == []


def test_watch_flags_a_jump_nothing_explains():
    watch = QueueWatch()
    watch.observe(0, {"W1": 2.0})
    watch.dispatched("W1", 4.0)
    assert watch.observe(1, {"W1": 17.0}) == ["W1"]
    assert watch.stopped(5) == ["W1"]
    assert watch.stopped(11) == []


def test_no_false_alarm_and_same_result_without_a_closure():
    for seed in (5105, 5106):
        sim = Simulator(shock=False, seed=seed)
        plain = Simulator.metrics(sim.run(Allocator("use_slack"), "plain"))
        watched = ClosureAwareAllocator(Allocator("use_slack"))
        assert Simulator.metrics(sim.run(watched, "watched")) == plain
        assert watched.watch.events == []


def test_closure_is_flagged_in_a_shock_run():
    flagged = 0
    for seed in range(5105, 5115):
        watched = ClosureAwareAllocator(Allocator("use_slack"))
        Simulator(shock=True, seed=seed).run(watched, "watched")
        flagged += bool(watched.watch.events)
    assert flagged >= 8


def morning():
    desk = Desk()
    for line in inbox_lines():
        desk.handle(line)
    return desk


def test_a_report_changes_nothing_until_confirmed():
    desk = Desk()
    d = desk.new_message("Ravi", "GiantWeave failed its inspection and has shut for two weeks.")
    assert d["subtype"] == "closure_report" and d["status"] == "closure_reported"
    assert d["reported_workshop"] == "W5" and d["number_check"]["ok"]
    assert desk.session_excl == {}
    assert desk.new_message("Boss", "ORD-066 - 1000 polo shirts, due Apr 20")["candidates"]


def test_confirmed_closure_stops_new_work_and_reopening_restores_it():
    desk = Desk()
    before = desk.new_message("Boss", "ORD-053 - 800 polo shirts for UrbanThread, due Apr 10.")
    assert any(c["workshop_id"] == "W5" for c in before["candidates"])
    report = desk.new_message("Ravi", "GiantWeave has stopped, the line is down.")
    desk.confirm_closure(report["request_id"])
    assert desk.decisions[report["request_id"]]["status"] == "closure_confirmed"
    after = desk.decisions[before["request_id"]]
    assert all(c["workshop_id"] != "W5" for c in after["candidates"])
    desk.lift_constraint("W5")
    assert any(c["workshop_id"] == "W5" for c in desk.decisions[before["request_id"]]["candidates"])


def test_batches_at_a_stopped_workshop_can_be_moved():
    desk = Desk()
    d = desk.new_message("Boss", "ORD-066 - 1000 polo shirts, due Apr 20")
    wid = d["recommended"]
    desk.confirm(d["request_id"], wid)
    assert desk.stopped_impact() == []
    desk.mark_stopped(wid)
    rows = desk.stopped_impact()
    assert [r["order_id"] for r in rows] == ["ORD-066"]
    target = rows[0]["best"]["workshop_id"]
    assert target != wid
    desk.reassign(rows[0]["audit_id"], target, reason="stopped")
    assert desk.stopped_impact() == []
    assert desk.ledger.already_committed("ORD-066")["workshop_id"] == target


def test_questions_and_order_messages_are_not_reports():
    desk = Desk()
    assert desk.new_message("Ravi", "Is GiantWeave closed this week?")["subtype"] != "closure_report"
    assert desk.new_message("Ravi", "ORD-066 is closed out, send it to GiantWeave. 1000 polo shirts, due Apr 20")["subtype"] != "closure_report"
    assert desk.new_message("Ravi", "The office is closed on Friday.")["subtype"] != "closure_report"


def test_no_message_in_the_official_inbox_reads_as_a_report():
    assert not [rid for rid, d in morning().decisions.items() if d["subtype"] == "closure_report"]
