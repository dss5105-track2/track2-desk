"""One chat message, more than one thing to do: nothing may be dropped without saying so."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "harness"))

from desk.multi_orders import status_question, split_orders  # noqa: E402
from desk.pipeline import Desk  # noqa: E402


def send(text, sender="Ravi"):
    desk = Desk()
    desk.new_message(sender, text)
    return desk, list(desk.decisions.values())


# ---------------------------------------------------------------- several order numbers: one card each
@pytest.mark.parametrize("text", ["Send ORD-053 and ORD-066 out, both need a shop.",
                                  "ORD-053, ORD-066 please, find shops.",
                                  "ORD-053 & ORD-066 need to go out.",
                                  "Please place ORD-053 plus ORD-066."])
def test_each_order_gets_a_card(text):
    _, ds = send(text)
    assert [d["order_id"] for d in ds] == ["ORD-053", "ORD-066"]
    assert all(d["batch"] for d in ds)


def test_three_orders():
    _, ds = send("Send ORD-053, ORD-066 and ORD-120 out.")
    assert [d["order_id"] for d in ds] == ["ORD-053", "ORD-066", "ORD-120"]


def test_the_same_order_named_twice_among_others_is_one_card():
    _, ds = send("ORD-053, ORD-053 and ORD-066 need to go out.")
    assert [d["order_id"] for d in ds] == ["ORD-053", "ORD-066"]


def test_a_question_that_asks_to_place_them_is_split():
    _, ds = send("Can someone place ORD-095 and ORD-010 today?")
    assert [d["order_id"] for d in ds] == ["ORD-095", "ORD-010"]


def test_a_question_about_them_is_not_split_and_names_the_other():
    _, ds = send("Are ORD-041 and ORD-045 done?")
    assert len(ds) == 1 and any("ORD-045" in f for f in ds[0]["flags"])


def test_a_remark_that_a_shop_holds_them_is_not_split_and_names_the_other():
    _, ds = send("QuickStitch is holding ORD-053 and ORD-066.")
    assert len(ds) == 1 and any("ORD-066" in f for f in ds[0]["flags"])


def test_each_part_carries_only_its_own_order_number():
    parts, _, _ = split_orders("Send ORD-053 and ORD-066 to BudgetWorks.")
    assert [(o, t.count("ORD-")) for o, t in parts] == [("ORD-053", 1), ("ORD-066", 1)]


def test_the_same_order_twice_is_one_card():
    _, ds = send("ORD-053 again: ORD-053 needs a shop.")
    assert [d["order_id"] for d in ds] == ["ORD-053"]


def test_a_short_order_number_counts():
    _, ds = send("Send ORD-53 and ORD-66 out.")
    assert [d["order_id"] for d in ds] == ["ORD-053", "ORD-066"]


def test_new_message_returns_the_first_card_and_ids_differ():
    desk = Desk()
    first = desk.new_message("Ravi", "Send ORD-053 and ORD-066 out.")
    assert first["order_id"] == "ORD-053" and len(set(desk.decisions)) == 2


def test_each_card_shows_the_whole_message_and_names_the_others():
    _, ds = send("Send ORD-053 and ORD-066 out.")
    assert all(d["raw_text"] == "Send ORD-053 and ORD-066 out." for d in ds)
    assert any(ds[1]["request_id"] in f for f in ds[0]["flags"])
    assert any(ds[0]["request_id"] in f for f in ds[1]["flags"])


def test_both_can_be_confirmed_and_the_second_sees_the_first():
    desk, ds = send("Send ORD-053 and ORD-066 to BudgetWorks.")
    for d in ds:
        desk.confirm(d["request_id"], "W3", accept_late=True)
    assert [r["order_id"] for r in desk.ledger.records] == ["ORD-053", "ORD-066"]
    assert desk.ledger.records[1]["queue_before"] > desk.ledger.records[0]["queue_before"]


def test_a_refresh_keeps_the_cards_apart():
    desk, ds = send("Send ORD-053 and ORD-066 out.")
    desk.refresh_all()
    assert [d["order_id"] for d in desk.decisions.values()] == ["ORD-053", "ORD-066"]
    assert all(d["raw_text"] == "Send ORD-053 and ORD-066 out." for d in desk.decisions.values())


# ---------------------------------------------------------------- what applies to which
def test_quantity_and_date_stay_with_their_own_order():
    _, ds = send("ORD-053 - 500 polo shirts for UrbanThread, due Apr 12. ORD-066 - 700 polo shirts, due Apr 28.")
    assert [(d["batch"]["pieces"], d["batch"]["due_date"]) for d in ds] == [(500, "2026-04-12"), (700, "2026-04-28")]


def test_a_shared_date_is_not_guessed():
    _, ds = send("ORD-053 and ORD-066, due Apr 20.")
    assert [d["batch"]["due_date"] for d in ds] == ["2026-04-10", "2026-04-26"]     # the order book's
    assert all(any("not clear which order" in f for f in d["flags"]) for d in ds)


def test_a_date_in_the_same_clause_as_both_is_not_guessed():
    _, ds = send("Send ORD-053 and ORD-066 by Apr 20.")
    assert [d["batch"]["due_date"] for d in ds] == ["2026-04-10", "2026-04-26"]
    assert all(any("not clear which order" in f for f in d["flags"]) for d in ds)


def test_a_date_in_its_own_sentence_at_the_end_is_not_guessed():
    _, ds = send("ORD-053 - 500 polo shirts. ORD-066 - 700 polo shirts. Due Apr 20.")
    assert [d["batch"]["due_date"] for d in ds] == ["2026-04-10", "2026-04-26"]
    assert [d["batch"]["pieces"] for d in ds] == [500, 700]


def test_a_date_after_orders_with_no_details_of_their_own_is_not_guessed():
    _, ds = send("ORD-053 for UrbanThread, ORD-066 for Northwind Apparel, due Apr 20.")
    assert [d["batch"]["due_date"] for d in ds] == ["2026-04-10", "2026-04-26"]
    assert all(any("not clear which order" in f for f in d["flags"]) for d in ds)


def test_a_named_shop_said_of_both_applies_to_both():
    _, ds = send("ORD-053 and ORD-066 to BudgetWorks please.")
    assert [d["parsed"]["forced_workshop"] for d in ds] == ["W3", "W3"]


def test_each_order_can_name_its_own_shop():
    _, ds = send("ORD-053 to GiantWeave, ORD-066 to BudgetWorks.")
    assert [d["parsed"]["forced_workshop"] for d in ds] == ["W5", "W3"]


def test_an_exclusion_applies_to_both():
    _, ds = send("Send ORD-053 and ORD-066 out. Not GiantWeave.")
    assert [d["parsed"]["excluded_workshops"] for d in ds] == [["W5"], ["W5"]]


def test_a_standing_ban_is_recorded_once():
    desk, ds = send("ORD-053 and ORD-066. Boss says nothing new to QuickStitch this week.")
    assert len(ds) == 2 and list(desk.session_excl) == ["W1"]
    assert desk.session_excl["W1"]["source"] == ds[0]["request_id"]
    assert sum("session constraint recorded" in f for d in ds for f in d["flags"]) == 1
    assert not any("set later" in f or "after this request" in f for d in ds for f in d["flags"])


# ---------------------------------------------------------------- lists: what follows is said of all of them
@pytest.mark.parametrize("text", ["ORD-053, ORD-066 to BudgetWorks.", "Send ORD-053/ORD-066 to BudgetWorks.", "To BudgetWorks: ORD-053, ORD-066.",
                                  "ORD-053 to BudgetWorks. Same for ORD-066."])
def test_a_shop_after_a_list_applies_to_all(text):
    _, ds = send(text)
    assert [d["parsed"]["forced_workshop"] for d in ds] == ["W3", "W3"]


@pytest.mark.parametrize("text", ["ORD-053, ORD-066 not GiantWeave.", "Not GiantWeave: ORD-053, ORD-066."])
def test_a_ban_after_or_before_a_list_applies_to_all(text):
    _, ds = send(text)
    assert [d["parsed"]["excluded_workshops"] for d in ds] == [["W5"], ["W5"]]


@pytest.mark.parametrize("text", ["Send ORD-053, ORD-066 by Apr 20.", "By Apr 20: ORD-053, ORD-066.", "ORD-053 500 polo shirts, ORD-066 700 polo shirts, both due Apr 20."])
def test_a_date_near_a_list_is_on_no_card(text):
    _, ds = send(text)
    assert [d["batch"]["due_date"] for d in ds] == ["2026-04-10", "2026-04-26"]
    assert all(any("not clear which order" in f for f in d["flags"]) for d in ds)


def test_a_detail_right_after_the_last_order_is_its_own():
    _, ds = send("ORD-053 for UrbanThread, ORD-066 700 polo shirts due Apr 30.")
    assert [d["batch"]["pieces"] for d in ds] == [800, 700]
    assert [d["batch"]["due_date"] for d in ds] == ["2026-04-10", "2026-04-30"]
    assert not any("not clear which order" in f for d in ds for f in d["flags"])


def test_a_quantity_in_a_later_clause_is_on_no_card():
    _, ds = send("ORD-053 for UrbanThread, ORD-066 for Northwind Apparel, 700 polo shirts.")
    assert [d["batch"]["pieces"] for d in ds] == [800, 1000]
    assert all(any("not clear which order" in f for f in d["flags"]) for d in ds)


def test_a_sentence_after_separate_orders_applies_to_all():
    _, ds = send("ORD-053 to GiantWeave. ORD-066 to BudgetWorks. Not FreshStart.")
    assert [d["parsed"]["excluded_workshops"] for d in ds] == [["W8"], ["W8"]]
    assert [d["parsed"]["forced_workshop"] for d in ds] == ["W5", "W3"]


@pytest.mark.parametrize("text", ["GiantWeave for ORD-053, BudgetWorks for ORD-066.", "BudgetWorks: ORD-053. OldMill: ORD-066.", "500 polo shirts for ORD-053, 700 polo shirts for ORD-066",
                                  "OldMill gets ORD-053 and BudgetWorks gets ORD-066", "OldMill gets ORD-053 and BudgetWorks gets ORD-066 please", "BudgetWorks takes ORD-053, GiantWeave ORD-066", "Express ORD-053, BudgetWorks ORD-066"])
def test_words_pointing_at_the_next_number_are_applied_to_no_card(text):
    _, ds = send(text)
    assert [d["order_id"] for d in ds] == ["ORD-053", "ORD-066"]
    assert all(d["parsed"]["forced_workshop"] is None for d in ds) and [d["batch"]["pieces"] for d in ds] == [800, 1000]
    assert all(any("read the message" in f for f in d["flags"]) for d in ds)


def test_a_later_clause_said_of_all_reaches_every_card():
    _, ds = send("ORD-053 500 polo shirts, ORD-066 700 polo shirts, not GiantWeave")
    assert [d["parsed"]["excluded_workshops"] for d in ds] == [["W5"], ["W5"]] and all(d["recommended"] != "W5" for d in ds)
    _, ds = send("ORD-053 rush, ORD-066 rush, both to BudgetWorks.")
    assert [d["parsed"]["forced_workshop"] for d in ds] == ["W3", "W3"]


def test_line_breaks_separate_like_sentences():
    _, ds = send("ORD-053 500 polo shirts\nORD-066 700 polo shirts\ndue Apr 20")
    assert [d["batch"]["pieces"] for d in ds] == [500, 700] and [d["batch"]["due_date"] for d in ds] == ["2026-04-10", "2026-04-26"]


def test_a_day_month_date_near_a_list_is_on_no_card():
    _, ds = send("ORD-053 and ORD-066, due 20 Apr.")
    assert [d["batch"]["due_date"] for d in ds] == ["2026-04-10", "2026-04-26"]


@pytest.mark.parametrize("text", ["ORD-053 to BudgetWorks, ORD-066 too", "ORD-053 to BudgetWorks, ORD-066 ditto", "ORD-053 to BudgetWorks, ORD-066 the same"])
def test_too_copies_the_order_before(text):
    _, ds = send(text)
    assert [d["parsed"]["forced_workshop"] for d in ds] == ["W3", "W3"]


def test_an_unread_quantity_is_flagged():
    _, ds = send("ORD-053 500 pcs, ORD-066 700 pcs")
    assert all(any("read the message" in f for f in d["flags"]) for d in ds)


@pytest.mark.parametrize("text", ["Don't send ORD-053 and ORD-066 yet.", "Send ORD-053, not ORD-066.", "ORD-053, sorry I meant ORD-066", "Did we send ORD-053 and ORD-066?",
                                  "ORD-053 and ORD-066 were already sent to BudgetWorks yesterday."])
def test_not_asking_to_send_them_all_is_one_card_naming_the_other(text):
    _, ds = send(text)
    assert len(ds) == 1 and any("ORD-066" in f for f in ds[0]["flags"])
    assert ds[0]["official_behaviour"] == "clarify" and "ORD-066" in ds[0]["explanation"] and not ds[0]["candidates"]


@pytest.mark.parametrize("text", ["Stop, leave ORD-053 and ORD-066 for now", "Hold ORD-053 and ORD-066 until Monday", "Could you check whether ORD-053 and ORD-066 got sent?"])
def test_holding_words_get_a_question(text):
    _, ds = send(text)
    assert len(ds) == 1 and ds[0]["official_behaviour"] == "clarify" and ds[0]["recommended"] is None


def test_not_between_two_orders_puts_no_shop_on_either():
    _, ds = send("ORD-053 not ORD-066 goes to BudgetWorks")
    assert len(ds) == 1 and ds[0]["official_behaviour"] == "clarify" and ds[0]["recommended"] is None


def test_they_have_to_is_not_held():
    desk, ds = send("GiantWeave has shut. ORD-053 and ORD-066 are urgent and they have to be back by Apr 20.")
    assert [d["order_id"] for d in ds] == ["ORD-053", "ORD-066"] and [d["batch"]["due_date"] for d in ds] == ["2026-04-10", "2026-04-26"]


@pytest.mark.parametrize("text", ["GiantWeave has shut, ORD-053 and ORD-066 are at GiantWeave.", "GiantWeave has shut, ORD-053 and ORD-066 are in there.", "GiantWeave has shut, ORD-053 and ORD-066 were there."])
def test_more_ways_to_say_held(text):
    _, ds = send(text)
    assert len(ds) == 1 and ds[0]["subtype"] == "closure_report"


def test_held_beside_a_split_is_noted_on_every_card():
    _, ds = send("GiantWeave has shut, it has ORD-120. Send ORD-053 and ORD-066 out.")
    assert [d["order_id"] for d in ds] == ["ORD-053", "ORD-066"] and all(any("ORD-120" in f for f in d["flags"]) for d in ds)


@pytest.mark.parametrize("text", ["ORD-053 and 066 need shops", "ORD-053/066 to BudgetWorks", "ORD-050\u2013053 find shops"])
def test_more_unreadable_numbers_are_flagged(text):
    _, ds = send(text)
    assert all(any("may name more orders" in f for f in d["flags"]) for d in ds)


def test_lower_case_second_order_counts():
    _, ds = send("ORD-053 and ord-066 to BudgetWorks")
    assert [d["order_id"] for d in ds] == ["ORD-053", "ORD-066"]


def test_a_later_line_does_not_replace_a_card():
    desk = Desk()
    desk.propose("H01 [09:00] Ravi: Send ORD-053 and ORD-066 out.")
    desk.propose("H02 [09:05] Ravi: ORD-010 needs a shop.")
    assert sorted(d["order_id"] for d in desk.decisions.values()) == ["ORD-010", "ORD-053", "ORD-066"]


def test_a_quantity_joined_to_one_order_is_flagged():
    _, ds = send("ORD-053 and 300 scarves need shops")
    assert any("300 scarves" in f for f in ds[0]["flags"])


def test_pieces_count_as_a_batch():
    _, ds = send("800 polos for TrendCart and 300 pieces of vests for Cotton Club")
    assert ds[0]["official_behaviour"] == "clarify" and "300 pieces" in ds[0]["explanation"]


def test_a_payment_question_does_not_hide_a_request():
    _, ds = send("ORD-041 needs a shop. What did we pay last time?")
    assert ds[0]["candidates"] and any("not handled" in f for f in ds[0]["flags"])


def test_a_question_on_one_of_two_orders_is_noted():
    _, ds = send("ORD-053 price? ORD-066 to BudgetWorks")
    assert any("not handled" in f for d in ds for f in d["flags"])


def test_a_bare_quantity_after_an_order_is_not_a_second_order():
    _, ds = send("ORD-053, 800, due Apr 10.")
    assert not any("may name more orders" in f for f in ds[0]["flags"])


def test_a_previous_figure_is_not_a_second_batch():
    _, ds = send("800 polo shirts for UrbanThread (previously 700 polo shirts)")
    assert not ds[0]["parsed"].get("multi_batches")


def test_an_abbreviated_date_does_not_leak_to_the_other_order():
    parts, _, _ = split_orders("ORD-053 500 polo shirts, due Apr. 12. ORD-066 700 polo shirts, due Apr. 28. Not FreshStart.")
    assert "28" not in parts[0][1] and "12" not in parts[1][1]


def test_a_quantity_each_is_on_no_card():
    _, ds = send("500 pcs each for ORD-053 and ORD-066.")
    assert [d["batch"]["pieces"] for d in ds] == [800, 1000]
    assert all(any("not clear which order" in f for f in d["flags"]) for d in ds)


@pytest.mark.parametrize("text", ["ORD-053 to GiantWeave and ORD-066 to BudgetWorks.", "ORD-053, send to GiantWeave. ORD-066, send to BudgetWorks."])
def test_own_shops_are_not_pooled(text):
    _, ds = send(text)
    assert [d["parsed"]["forced_workshop"] for d in ds] == ["W5", "W3"]


def test_an_abbreviated_month_stays_with_its_order():
    _, ds = send("ORD-053 500 polo shirts, due Apr. 12. ORD-066 700 polo shirts, due Apr. 28.")
    assert [d["batch"]["due_date"] for d in ds] == ["2026-04-12", "2026-04-28"]


# ---------------------------------------------------------------- order numbers written loosely
def test_order_with_a_space():
    _, ds = send("ORD-053 and ORD 066 please, find shops.")
    assert [d["order_id"] for d in ds] == ["ORD-053", "ORD-066"]


@pytest.mark.parametrize("text", ["ORD-053, 066 and 120 need shops.", "ORD-053-066 need shops.", "Send ORD-050 to ORD-053 out."])
def test_numbers_that_cannot_be_read_are_flagged(text):
    _, ds = send(text)
    assert all(any("may name more orders" in f for f in d["flags"]) for d in ds)


def test_a_quantity_after_an_order_is_not_taken_for_an_order_number():
    _, ds = send("ORD-053, 800 polo shirts, due Apr 10.")
    assert not any("may name more orders" in f for f in ds[0]["flags"])


# ---------------------------------------------------------------- beside a split
def test_a_further_batch_beside_two_orders_is_flagged():
    _, ds = send("ORD-053 700 polo shirts, ORD-066 500 polo shirts, plus 300 scarves for TrendCart.")
    assert [d["order_id"] for d in ds] == ["ORD-053", "ORD-066"] and all(any("300 scarves" in f for f in d["flags"]) for d in ds)


def test_another_customer_beside_two_orders_is_flagged():
    _, ds = send("ORD-053, ORD-066 and also the Cotton Club vests, send them.")
    assert any("Cotton Club" in f for d in ds for f in d["flags"])


def test_two_identical_batches_are_two():
    _, ds = send("800 polo shirts for UrbanThread and 800 polo shirts for Northwind Apparel, find shops.")
    assert ds[0]["official_behaviour"] == "clarify" and ds[0]["explanation"].count("800 polo shirts") == 2


def test_a_corrected_quantity_is_not_a_second_batch():
    _, ds = send("800 polo shirts for UrbanThread, due Apr 20, was 700 polo shirts.")
    assert not ds[0]["parsed"].get("multi_batches")


# ---------------------------------------------------------------- ids, follow-ups, replay
def test_a_line_with_its_own_h_id_does_not_collide():
    desk = Desk()
    desk.propose("H01 [09:00] Ravi: Send ORD-053 and ORD-066 out.")
    assert [d["order_id"] for d in desk.decisions.values()] == ["ORD-053", "ORD-066"]
    next_card = desk.new_message("Ravi", "ORD-010 needs a shop.")
    assert len(desk.decisions) == 3 and next_card["order_id"] == "ORD-010"


def test_a_follow_up_with_two_orders_keeps_the_stop_on_both():
    desk = Desk()
    d = desk.new_message("Ravi", "GiantWeave has shut, 800 polo shirts and 300 scarves")
    desk.follow_up(d["request_id"], "ORD-053 and ORD-066")
    cards = [x for x in desk.decisions.values() if x["order_id"]]
    assert len(cards) == 2 and all(x["stop_mentions"] == ["W5"] for x in cards)
    assert all(c["workshop_id"] != "W5" for x in cards for c in x["candidates"])


def test_answering_one_of_two_batches_says_so():
    desk = Desk()
    d = desk.new_message("Ravi", "800 polo shirts for UrbanThread and 300 scarves for TrendCart, find shops.")
    new = desk.follow_up(d["request_id"], "ORD-053")
    assert any("300 scarves" in f for f in new["flags"])


def test_unattended_replay_confirms_every_card():
    desk = Desk()
    desk.handle("H90 [09:00] Ravi: Send ORD-066 and ORD-010 out.")
    assert sorted(r["order_id"] for r in desk.ledger.records) == ["ORD-010", "ORD-066"]


# ---------------------------------------------------------------- one order behaves as before
@pytest.mark.parametrize("text", ["I need to know about ORD-041, how far along is it?", "TrendCart needs an answer on ORD-120. How much did we quote?"])
def test_needing_an_answer_is_not_a_dispatch(text):
    _, ds = send(text)
    assert ds[0]["subtype"] == "not_in_data" and not ds[0]["candidates"]


def test_stuck_in_house_is_not_held_at_the_workshop():
    _, ds = send("ORD-053 is stuck in washing, find a shop. GiantWeave has shut.")
    assert ds[0]["order_id"] == "ORD-053" and ds[0]["stop_mentions"] == ["W5"] and ds[0]["candidates"]


# ---------------------------------------------------------------- with a stop
def test_a_stop_applies_to_every_card():
    desk, ds = send("ORD-053 and ORD-066, GiantWeave has shut until May 30.")
    assert [d["order_id"] for d in ds] == ["ORD-053", "ORD-066"]
    assert all(d["stop_mentions"] == ["W5"] for d in ds)
    assert all(c["workshop_id"] != "W5" for d in ds for c in d["candidates"])
    assert [d["batch"]["due_date"] for d in ds] == ["2026-04-10", "2026-04-26"]
    desk.mark_stopped("W5")
    assert all(d["stop_mentions"] == [] for d in desk.decisions.values())


@pytest.mark.parametrize("text", ["GiantWeave has shut, it was holding ORD-053 and ORD-066.",
                                  "GiantWeave has shut. ORD-053 and ORD-066 are stuck there.",
                                  "GiantWeave has shut, ORD-053 is sitting there.",
                                  "GiantWeave has shut, it was holding ORD-053, ORD-066 and ORD-120.",
                                  "GiantWeave has shut, ORD-053 and ORD-066 are there.",
                                  "GiantWeave has shut and it has ORD-053 and ORD-066."])
def test_orders_held_at_a_stopped_shop_are_not_new_dispatches(text):
    desk, ds = send(text)
    assert len(ds) == 1 and ds[0]["subtype"] == "closure_report" and ds[0]["reported_workshop"] == "W5"
    assert "ORD-053" in ds[0]["explanation"]
    assert desk.bulk_plan()["confirm"] == []


def test_held_and_a_request_in_one_sentence():
    _, ds = send("GiantWeave has shut. It has ORD-053, send ORD-066 out.")
    assert [d["order_id"] for d in ds] == ["ORD-066"] and any("ORD-053" in f for f in ds[0]["flags"])


def test_held_up_is_not_held_at_a_workshop():
    _, ds = send("ORD-053 is held up, send ORD-066 out.")
    assert [d["order_id"] for d in ds] == ["ORD-053", "ORD-066"]


def test_a_held_order_does_not_hide_a_request():
    _, ds = send("GiantWeave has shut, it was holding ORD-053. Send ORD-066 elsewhere.")
    assert [d["order_id"] for d in ds] == ["ORD-066"]
    assert ds[0]["stop_mentions"] == ["W5"] and any("ORD-053" in f for f in ds[0]["flags"])


# ---------------------------------------------------------------- when it cannot tell, it says so
def test_a_question_about_two_orders_is_answered_once_and_names_both():
    _, ds = send("How is ORD-053 and ORD-066 going?")
    assert len(ds) == 1 and ds[0]["subtype"] == "not_in_data" and any("ORD-066" in f for f in ds[0]["flags"])


def test_two_batches_without_order_numbers_are_asked_about_not_guessed():
    desk, ds = send("800 polo shirts for UrbanThread and 1000 polo shirts for Northwind Apparel, find shops.")
    assert len(ds) == 1 and ds[0]["official_behaviour"] == "clarify"
    assert "800 polo shirts" in ds[0]["explanation"] and "1000 polo shirts" in ds[0]["explanation"]
    assert ds[0]["number_check"]["ok"] and desk.ledger.records == []


def test_a_second_batch_beside_one_order_is_flagged():
    _, ds = send("ORD-053 - 800 polo shirts for UrbanThread, plus 300 scarves for TrendCart.")
    assert len(ds) == 1 and ds[0]["order_id"] == "ORD-053"
    assert any("300 scarves" in f for f in ds[0]["flags"])


def test_an_unrelated_question_is_flagged():
    _, ds = send("ORD-066 - 1000 polo shirts, due Apr 26. What's the price we quoted them?")
    assert ds[0]["order_id"] == "ORD-066" and any("not handled" in f and "price" in f for f in ds[0]["flags"])


def test_a_question_does_not_hide_a_request():
    _, ds = send("ORD-041 needs a shop. By the way, how much did we quote for it?")
    assert len(ds) == 1 and ds[0]["order_id"] == "ORD-041" and ds[0]["candidates"]
    assert any("not handled" in f and "how much" in f for f in ds[0]["flags"])
    assert ds[0]["raw_text"] == "ORD-041 needs a shop. By the way, how much did we quote for it?"


def test_a_question_alongside_two_orders_is_flagged_on_both():
    _, ds = send("Send ORD-053 and ORD-066 out. What's the price we quoted?")
    assert [d["order_id"] for d in ds] == ["ORD-053", "ORD-066"]
    assert all(any("not handled" in f and "price" in f for f in d["flags"]) for d in ds)


def test_a_price_question_about_an_order_is_still_only_a_question():
    _, ds = send("ORD-120 for TrendCart. What price did we quote?")
    assert ds[0]["subtype"] == "not_in_data" and not any("not handled" in f for f in ds[0]["flags"])


def test_another_customer_beside_one_order_is_flagged():
    _, ds = send("ORD-041 and also the Cotton Club vests, send both.")
    assert ds[0]["order_id"] == "ORD-041" and any("Cotton Club" in f and "not handled" in f for f in ds[0]["flags"])


def test_asking_who_can_take_it_is_not_flagged_as_another_question():
    _, ds = send("ORD-066 - 1000 polo shirts, due Apr 26. Who can take this order?")
    assert not any("not handled" in f for f in ds[0]["flags"])


# ---------------------------------------------------------------- nothing changes for one order
def test_scores_on_the_evaluation_sets_are_pinned():
    """Rule parser, first reply type, sets replayed in order. Splitting must not move any of these counts.
    Held-out went from 36 to 37 when curly apostrophes started reading like straight ones (H04's ban now reaches H41);
    that fix came after we had seen the held-out set, so 37 is not a clean result."""
    import csv
    for path, labels, want in (("data/dispatch_requests.txt", "eval/gold_labels.csv", 30),
                               ("experiments/language_eval/challenge_set/challenge_requests.txt", "experiments/language_eval/challenge_set/challenge_labels.csv", 37),
                               ("eval/heldout/requests.txt", "eval/heldout/gold_labels.csv", 37)):
        gold = {r["request_id"]: r["official_behaviour"] for r in csv.DictReader(open(ROOT / labels, encoding="utf-8-sig"))}
        desk = Desk()
        for line in (ROOT / path).read_text(encoding="utf-8").splitlines():
            if line.strip() and not line.startswith("#"):
                desk.propose(line)
        assert sum(d["official_behaviour"] == gold[k] for k, d in desk.decisions.items()) == want, path


def test_the_evaluation_sets_are_untouched():
    for path in ("data/dispatch_requests.txt", "experiments/language_eval/challenge_set/challenge_requests.txt", "eval/heldout/requests.txt"):
        desk = Desk()
        lines = [ln for ln in (ROOT / path).read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.startswith("#")]
        unread = []
        for line in lines:
            d = desk.propose(line)
            notes = [n for n in d["parsed"].get("extra_notes", []) if "could not read" not in n]
            unread += [d["request_id"] for n in d["parsed"].get("extra_notes", []) if "could not read" in n]
            assert not notes and not d["parsed"].get("multi_batches"), line
        assert len(desk.decisions) == len(lines), path
        # the only unread detail in all three sets: "1000 pieces" (the parser reads "1000 cardigans", not "pieces")
        assert unread == (["H17"] if "heldout" in path else []), path


# ---------------------------------------------------------------- another batch, or a question, inside the message
@pytest.mark.parametrize("text", ["ORD-053 needs a shop, also 300 scarves for TrendCart due Apr 20",
                                  "ORD-053 needs a shop also 300 scarves for TrendCart due Apr 20",
                                  "ORD-053 needs a shop, 300 scarves for TrendCart, due Apr 20"])
def test_details_said_of_another_customer_stay_off_the_card(text):
    _, ds = send(text)
    assert len(ds) == 1 and ds[0]["batch"]["pieces"] == 800 and ds[0]["batch"]["due_date"] == "2026-04-10"
    assert any("TrendCart" in f and "not applied" in f for f in ds[0]["flags"])


def test_details_written_right_on_the_number_stay_as_a_flagged_difference():
    _, ds = send("ORD-053 - 300 scarves for TrendCart, needs a shop")
    assert ds[0]["batch"]["pieces"] == 300 and any("chat says 300 pieces" in f for f in ds[0]["flags"]) and not any("not applied" in f for f in ds[0]["flags"])


def test_details_of_another_product_stay_off_the_card():
    _, ds = send("ORD-053 needs a shop, plus 300 scarves due Apr 20")
    assert ds[0]["batch"]["pieces"] == 800 and any("scarves" in f and "not applied" in f for f in ds[0]["flags"])


def test_the_orders_own_details_stay_beside_another_batch():
    _, ds = send("ORD-053 - 500 polo shirts for UrbanThread, due Apr 12, also 300 scarves for TrendCart")
    assert ds[0]["batch"]["pieces"] == 500 and ds[0]["batch"]["due_date"] == "2026-04-12"
    assert any("TrendCart" in f for f in ds[0]["flags"])


def test_two_quantities_of_the_same_product_are_flagged():
    _, ds = send("ORD-053 - 500 polo shirts, 300 polo shirts")
    assert any("300 polo shirts" in f and "not handled" in f for f in ds[0]["flags"])


def test_the_orders_own_customer_and_product_are_not_another_batch():
    _, ds = send("ORD-053 - 500 polo shirts for UrbanThread, due Apr 12")
    assert ds[0]["batch"]["pieces"] == 500 and not any("not applied" in f for f in ds[0]["flags"])


def test_another_batch_inside_a_split_stays_off_that_card():
    _, ds = send("ORD-053 500 polo shirts, ORD-066 rush also 300 scarves for TrendCart")
    assert [d["batch"]["pieces"] for d in ds] == [500, 1000] and any("TrendCart" in f for f in ds[1]["flags"])


def test_a_status_question_beside_a_request_is_noted_not_dispatched():
    _, ds = send("ORD-053 needs a shop. Is ORD-066 done?")
    assert [d["order_id"] for d in ds] == ["ORD-053"] and any("Is ORD-066 done?" in f and "not handled" in f for f in ds[0]["flags"])


def test_the_order_in_a_status_question_is_not_counted_as_a_second_request():
    _, ds = send("ORD-053 needs a shop. Is ORD-066 done?")
    assert not any("also names" in f or "one of" in f for f in ds[0]["flags"])


def test_a_progress_question_is_left_alone_by_the_other_batch_check():
    _, ds = send("How far along is ORD-053, due Apr 20 for TrendCart?")
    assert not any("not applied" in f for f in ds[0]["flags"])


@pytest.mark.parametrize("clause, want", [("Is ORD-066 done?", True), ("Has ORD-066 shipped?", True), ("Was ORD-066 sent?", True),
                                          ("Is ORD-066 ready to ship?", False), ("Did you send ORD-066?", False),
                                          ("Is ORD-066 at BudgetWorks?", False), ("Is it done?", False), ("Is ORD-066 done", False)])
def test_what_counts_as_a_status_question(clause, want):
    assert status_question(clause) is want


def test_a_status_question_and_a_ban_beside_a_request():
    desk, ds = send("ORD-053 needs a shop. Is ORD-066 done? Nothing new to QuickStitch this week.")
    assert [d["order_id"] for d in ds] == ["ORD-053"] and "W1" in desk.session_excl and any("Is ORD-066 done?" in f for f in ds[0]["flags"])


def test_a_status_question_before_a_request():
    _, ds = send("Has ORD-066 shipped? ORD-053 to BudgetWorks.")
    assert [(d["order_id"], d["parsed"]["forced_workshop"]) for d in ds] == [("ORD-053", "W3")] and any("Has ORD-066 shipped?" in f for f in ds[0]["flags"])


def test_lines_pasted_into_a_one_line_box_still_split():
    _, ds = send("ORD-053 500 polo shirts due Apr 12 ORD-066 700 polo shirts due Apr 28 ORD-010 to BudgetWorks")
    assert [(d["order_id"], d["batch"]["pieces"], d["batch"]["due_date"], d["parsed"]["forced_workshop"]) for d in ds] == [
        ("ORD-053", 500, "2026-04-12", None), ("ORD-066", 700, "2026-04-28", None), ("ORD-010", 1000, "2026-04-25", "W3")]


def test_a_pasted_chat_log_applies_nothing_and_says_so():
    _, ds = send("Ravi: ORD-053 needs a shop\nPriya: ORD-066 to BudgetWorks\nBoss: nothing new to QuickStitch this week")
    assert [d["parsed"]["forced_workshop"] for d in ds] == [None, None] and all(any("read the message" in f for f in d["flags"]) for d in ds)
