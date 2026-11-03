"""A workshop stops: spotted from the queue in the simulator, reported in chat at the desk."""
import sys
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "harness"))

from desk.pipeline import Desk, inbox_lines  # noqa: E402
from kernel.allocator import Allocator  # noqa: E402
from kernel.closure import ClosureAwareAllocator, QueueWatch  # noqa: E402
from simulate import Simulator  # noqa: E402

BAN = "ORD-053 - 800 polo shirts for UrbanThread, due Apr 10. Boss says nothing new to QuickStitch this week."


# ---------------------------------------------------------------- the simulator experiment
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


def test_watch_sends_no_new_work_to_a_flagged_shop():
    class Spy:
        def __init__(self):
            self.excluded = []

        def reset(self):
            pass

        def choose(self, batch, workshops, queues, exclude=()):
            self.excluded.append(list(exclude))
            return "W1"

    class Shop:
        capacity = 100

    spy = Spy()
    watched = ClosureAwareAllocator(spy)
    day0, day1 = date(2026, 1, 1), date(2026, 1, 2)
    batch = {"order_id": "X", "category": "TOPS", "pieces": 100}
    watched({**batch, "sent_date": day0}, {"W1": Shop()}, {"W1": 0.0})
    watched({**batch, "sent_date": day1}, {"W1": Shop()}, {"W1": 20.0})
    assert spy.excluded == [[], ["W1"]]


def test_no_false_alarm_and_same_result_without_a_closure():
    for seed in (5105, 5106):
        sim = Simulator(shock=False, seed=seed)
        plain = Simulator.metrics(sim.run(Allocator("use_slack"), "plain"))
        watched = ClosureAwareAllocator(Allocator("use_slack"))
        assert Simulator.metrics(sim.run(watched, "watched")) == plain
        assert watched.watch.events == []


# ---------------------------------------------------------------- what counts as a report
@pytest.mark.parametrize("text", [
    "GiantWeave has stopped being swamped, use them again.",
    "GiantWeave reopened today, no longer closed.",
    "GiantWeave isn't closed, it's fine to use.",
    "The office is closed on Friday.",
    "Is GiantWeave closed this week?",
])
def test_not_a_stop_at_all(text):
    d = Desk().new_message("Ravi", text)
    assert d["subtype"] != "closure_report" and not d.get("stop_mentions")


@pytest.mark.parametrize("text", [
    "The TrendCart deal closed, send 800 hoodies for TrendCart to GiantWeave, due Apr 20.",
    "Send the Harbor Knits scarves to Little Loom before the office closes, due Apr 18.",
    "ORD-066 is closed out, send it to GiantWeave. 1000 polo shirts, due Apr 20",
])
def test_a_dispatch_is_never_swallowed(text):
    d = Desk().new_message("Ravi", text)
    assert d["subtype"] != "closure_report" and not d.get("stop_mentions")


@pytest.mark.parametrize("text,wid", [
    ("GiantWeave has closed for two weeks.", "W5"),
    ("Production stopped at SteadyHands.", "W2"),
    ("Giant Weave is shut.", "W5"),
    ("GiantWeave is on strike.", "W5"),
    ("GiantWeave's machines broke down, nothing moving.", "W5"),
    ("QuickStitch suspended by the auditors.", "W1"),
    ("GiantWeave failed its inspection and has shut for two weeks.", "W5"),
])
def test_a_report_is_read(text, wid):
    d = Desk().new_message("Ravi", text)
    assert d["subtype"] == "closure_report" and d["reported_workshop"] == wid and d["number_check"]["ok"]


def test_no_message_in_the_evaluation_sets_reads_as_a_stop():
    for path in ("data/dispatch_requests.txt", "experiments/language_eval/challenge_set/challenge_requests.txt", "eval/heldout/requests.txt"):
        desk = Desk()
        for line in (ROOT / path).read_text(encoding="utf-8").splitlines():
            if line.strip() and not line.startswith("#"):
                d = desk.propose(line)
                assert d["subtype"] != "closure_report" and not d["stop_mentions"], line


# ---------------------------------------------------------------- a request that also mentions a stop
def test_an_order_message_stays_a_request_and_avoids_the_shop_it_says_has_stopped():
    desk = Desk()
    d = desk.new_message("Ravi", "ORD-053 - 800 polo shirts for UrbanThread, due Apr 10. GiantWeave has shut.")
    assert d["subtype"] in ("allocate", "no_on_time_option") and d["order_id"] == "ORD-053"
    assert d["stop_mentions"] == ["W5"] and d["parsed"]["forced_workshop"] is None
    assert all(c["workshop_id"] != "W5" for c in d["candidates"])
    assert desk.stopped == {} and desk.session_excl == {}       # this request only, until someone confirms
    other = desk.new_message("Boss", "ORD-066 - 1000 polo shirts, due Apr 20")
    assert any(c["workshop_id"] == "W5" for c in other["candidates"])
    desk.mark_stopped("W5", source=d["request_id"])
    assert desk.decisions[d["request_id"]]["stop_mentions"] == []
    assert all(c["workshop_id"] != "W5" for c in desk.decisions[other["request_id"]]["candidates"])


# ---------------------------------------------------------------- nothing changes until a person confirms
def test_a_report_changes_nothing_until_confirmed():
    desk = Desk()
    assert desk.new_message("Boss", "Avoid GiantWeave this week, it has shut.")["subtype"] == "closure_report"
    assert desk.stopped == {} and desk.session_excl == {}
    assert any(c["workshop_id"] == "W5" for c in desk.new_message("Boss", "ORD-066 - 1000 polo shirts, due Apr 20")["candidates"])


def test_confirmed_stop_stops_new_work_and_reopening_restores_it():
    desk = Desk()
    before = desk.new_message("Boss", "ORD-053 - 800 polo shirts for UrbanThread, due Apr 10.")
    report = desk.new_message("Ravi", "GiantWeave has stopped, the line is down.")
    desk.confirm_closure(report["request_id"])
    assert desk.decisions[report["request_id"]]["status"] == "closure_confirmed"
    assert [x["action"] for x in desk.actions if x["action"] == "mark_stopped"] == ["mark_stopped"]
    assert all(c["workshop_id"] != "W5" for c in desk.decisions[before["request_id"]]["candidates"])
    with pytest.raises(ValueError):
        desk.confirm(before["request_id"], "W5", accept_late=True)
    named = desk.new_message("Ravi", "ORD-066 - 1000 polo shirts, due Apr 20, send it to GiantWeave")
    assert named["subtype"] == "ineligible_suggestion" and "stopped" in named["explanation"]
    desk.reopen("W5")
    assert any(c["workshop_id"] == "W5" for c in desk.decisions[before["request_id"]]["candidates"])
    assert desk.actions[-1]["action"] == "reopen"


# ---------------------------------------------------------------- a stop and a ban are separate
def test_reopening_leaves_the_boss_ban_in_place():
    desk = Desk()
    desk.new_message("Boss", BAN)
    desk.mark_stopped("W1")
    desk.reopen("W1")
    assert desk.session_excl["W1"]["by"] == "Boss" and desk.stopped == {}


def test_a_ban_does_not_erase_a_stop_and_lifting_it_leaves_the_stop():
    desk = Desk()
    desk.mark_stopped("W1")
    desk.new_message("Boss", BAN)
    assert "W1" in desk.stopped and "W1" in desk.session_excl
    desk.lift_constraint("W1")
    assert "W1" in desk.stopped and "W1" not in desk.session_excl
    assert all(c["workshop_id"] != "W1" for c in desk.new_message("Boss", "ORD-066 - 1000 polo shirts, due Apr 20")["candidates"])


def test_a_second_confirmation_changes_nothing():
    desk = Desk()
    desk.mark_stopped("W5", by="Chen")
    desk.mark_stopped("W5", by="Ravi")
    assert desk.stopped["W5"]["by"] == "Chen"


# ---------------------------------------------------------------- moving what is already there
def dispatched(desk, text="ORD-066 - 1000 polo shirts, due Apr 20"):
    d = desk.new_message("Boss", text)
    desk.confirm(d["request_id"], d["recommended"])
    return d


def test_batches_at_a_stopped_workshop_can_be_moved():
    desk = Desk()
    wid = dispatched(desk)["recommended"]
    assert desk.stopped_impact() == []
    desk.mark_stopped(wid)
    rows = desk.stopped_impact()
    assert [r["order_id"] for r in rows] == ["ORD-066"]
    target = rows[0]["best"]["workshop_id"]
    assert target != wid
    desk.reassign(rows[0]["audit_id"], target, reason="stopped")
    assert desk.stopped_impact() == []
    assert desk.ledger.already_committed("ORD-066")["workshop_id"] == target


def test_a_move_keeps_to_what_the_request_ruled_out():
    desk = Desk()
    d = dispatched(desk, "ORD-066 - 1000 polo shirts, due Apr 20. Not BudgetWorks.")
    assert d["parsed"]["excluded_workshops"] == ["W3"]
    desk.mark_stopped(d["recommended"])
    best = desk.stopped_impact()[0]["best"]["workshop_id"]
    assert best not in ("W3", d["recommended"])
    with pytest.raises(ValueError):
        desk.reassign(desk.ledger.already_committed("ORD-066")["audit_id"], "W3")


def test_a_batch_cannot_be_moved_onto_a_banned_workshop():
    desk = Desk()
    d = dispatched(desk)
    other = next(c["workshop_id"] for c in d["candidates"] if c["workshop_id"] != d["recommended"])
    desk.new_message("Boss", f"ORD-053 - 800 polo shirts for UrbanThread, due Apr 10. Boss says nothing new to {desk.name(other)} this week.")
    with pytest.raises(ValueError):
        desk.reassign(desk.ledger.already_committed("ORD-066")["audit_id"], other)


def test_a_batch_cannot_be_moved_onto_a_stopped_workshop():
    desk = Desk()
    d = dispatched(desk)
    other = next(c["workshop_id"] for c in d["candidates"] if c["workshop_id"] != d["recommended"])
    desk.mark_stopped(other)
    with pytest.raises(ValueError):
        desk.reassign(desk.ledger.already_committed("ORD-066")["audit_id"], other)


def test_a_stopped_shop_is_not_offered_as_lifting_a_ban():
    """R28 is late everywhere. Banned, QuickStitch is offered as what lifting the ban would give; stopped too, it must not be."""
    line = next(ln for ln in inbox_lines() if ln.startswith("R28"))
    desk = Desk()
    desk.new_message("Boss", BAN)
    assert "If the ban on QuickStitch" in desk.propose(line)["explanation"]
    desk = Desk()
    desk.new_message("Boss", BAN)
    desk.mark_stopped("W1")
    assert "If the ban on QuickStitch" not in desk.propose(line)["explanation"]
