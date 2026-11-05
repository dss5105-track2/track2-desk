"""The dispatch desk: chat line -> structured request -> behaviour -> kernel -> explanation -> ledger.

Two ways in:
  * `Desk.propose(line)` returns a decision and writes nothing. A dispatcher then calls
    `confirm`, `mark`, `follow_up`, `reassign` or `lift_constraint`. This is what the UI uses.
  * `Desk.handle(line)` proposes and auto-confirms on-time allocations. The CLI below uses it
    to replay a whole inbox unattended.

CLI:
    python desk/pipeline.py                  # rule parser, no network, no cost
    python desk/pipeline.py --llm            # LLM extraction, GPT-5 mini by default (costs money; needs .env)
    python desk/pipeline.py --only R12       # one request, full detail

For every chat line, in timestamp order:
  1. parse           -> structured request (llm/llm_client.py; rules by default)
  2. resolve order   -> explicit id, or candidates from customer/product
  3. route           -> decline / clarify / refuse / extract   (deterministic, labeling_guide order)
  4. kernel          -> eligibility table, estimates, ranking  (kernel/, zero LLM)
  5. explain         -> text built only from tool outputs; every number is checked against them
  6. confirm+commit  -> only a human confirmation changes the ledger
Outputs go to eval/runs/<timestamp>/ (git-ignored): decisions.jsonl, audit.json, transcript.md.
The run is scored against eval/gold_labels.csv. That comparison is a development
check on the official 30, not the held-out evaluation.
"""
from __future__ import annotations

import argparse
import copy
import csv
import json
import re
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from kernel.register import load_workshops, check_eligibility, eligibility_table  # noqa: E402
from kernel.orders import load_orders, find_orders, last_week, state_checks, TODAY  # noqa: E402
from kernel.allocator import Allocator, OBJECTIVES, flexibility  # noqa: E402
from kernel.estimator import estimate, split_estimate  # noqa: E402
from kernel.ledger import Ledger  # noqa: E402
from desk.multi_orders import (ALSO_RE, DISPATCH_WORD_RE, NOT_A_REQUEST_RE, looks_like_dispatch, normalise_ids, other_batches,  # noqa: E402
                               split_orders, suspect_ids, take_held, unhandled_question)
from desk.stop_reports import asks_nothing, read_stops  # noqa: E402
from llm.llm_client import RuleBasedParser, LLMClient, order_ids, parse_header  # noqa: E402

OFFICIAL = {"allocate": "extract", "no_on_time_option": "extract", "ambiguous_reference": "clarify",
            "missing_fields": "clarify", "state_conflict": "clarify", "ineligible_suggestion": "refuse",
            "not_in_data": "decline-to-answer", "closure_report": "clarify"}
# what the dispatcher is expected to do next, per subtype
STATUS = {"allocate": "awaiting_confirmation", "no_on_time_option": "awaiting_decision",
          "ineligible_suggestion": "refused", "ambiguous_reference": "needs_reply",
          "missing_fields": "needs_reply", "state_conflict": "needs_reply", "not_in_data": "answered",
          "closure_report": "closure_reported"}
# statuses a dispatcher can set without touching the ledger
HUMAN_STATUSES = {"reply_sent", "answer_sent", "escalated", "renegotiating", "dismissed", "closure_confirmed"}
NEW_ORDER_RE = re.compile(r"details to follow|new rush|coming in from", re.I)


def days(n: int) -> str:
    return f"{n} day" if n == 1 else f"{n} days"


class Desk:
    def __init__(self, parser=None, objective: str = "use_slack"):
        self.W = load_workshops()
        self.O = load_orders()
        self.ledger = Ledger(self.W, TODAY)
        self.alloc = Allocator(objective)
        self.parser = parser or RuleBasedParser().parse
        self.session_excl: Dict[str, dict] = {}     # workshop_id -> {"by", "source"}
        self.stopped: Dict[str, dict] = {}          # workshop_id -> {"by", "source", "time"}; set only by a person's confirmation
        self.history: List[dict] = []               # parsed requests, for cross-message memory
        self.decisions: Dict[str, dict] = {}
        self.actions: List[dict] = []               # every human action, ledger or not
        self.arrival: Dict[str, int] = {}           # request_id -> position in the inbox
        self.seq = 0
        self.taken_ids: set = set()                 # request ids in use, including ones that arrived on a chat line
        self.last_proposed: List[dict] = []         # the decisions from the latest chat line

    # ---------------------------------------------------------------- helpers
    def name(self, wid: str) -> str:
        return self.W[wid].name

    def set_objective(self, objective: str) -> None:
        load = self.alloc.load
        self.alloc = Allocator(objective)
        self.alloc.load = load
        self.refresh_all()

    def next_request_id(self) -> str:
        while True:
            self.seq += 1
            rid = f"H{self.seq:02d}"
            if rid not in self.taken_ids:
                self.taken_ids.add(rid)
                return rid

    def _batch(self, order, req) -> dict:
        pieces = req["pieces"] or order.pieces
        due = date.fromisoformat(req["due_date"]) if req["due_date"] else order.due_date
        return {"order_id": order.order_id, "category": order.category, "pieces": pieces, "sent_date": TODAY, "due_date": due}

    def _mismatch_notes(self, order, req) -> List[str]:
        notes = []
        if req["pieces"] and req["pieces"] != order.pieces:
            notes.append(f"chat says {req['pieces']} pieces, orders.csv says {order.pieces}")
        if req["due_date"] and date.fromisoformat(req["due_date"]) != order.due_date:
            notes.append(f"chat due date {req['due_date']} differs from orders.csv {order.due_date}")
        return notes

    def _forced_problem(self, wid: str, batch: dict) -> str:
        """Why the workshop a message names cannot take this batch; '' if it can."""
        ok, why = check_eligibility(self.W[wid], batch["category"], batch["pieces"])
        if not ok:
            return why
        if wid in self.stopped:
            return "it is reported as stopped"
        if wid in self.session_excl:
            return f"{self.session_excl[wid]['by']} said nothing new goes to it ({self.session_excl[wid]['source']})"
        return ""

    def _identity_clash(self, order, req) -> str:
        """The customer or product the message names, when it is not this order's: the id is probably mistyped. '' when they agree.
        Piece count and date differences stay flags (_mismatch_notes); the labelling rules do not stop on them."""
        said = [v for v, own in ((req["customer"], order.customer), (req["product"], order.product)) if v and v.lower() != own.lower()]
        if said and req["pieces"]:
            said.append(f"{req['pieces']} pcs")
        return ", ".join(said)

    def _parse(self, line: str) -> dict:
        """Parse a chat line, with any clause saying a workshop has stopped taken out first. A message that only
        reports a stop becomes a report, without calling the model. One that also asks for something stays a request."""
        names = {wid: w.name for wid, w in self.W.items()}
        text = parse_header(line)[3]
        stopped, rest = read_stops(text, names)
        if not stopped:
            return self.parser(line, list(self.history))
        held, rest = take_held(rest)
        rest_line = line.strip()[:-len(text)] + rest
        rules = RuleBasedParser().parse(rest_line, list(self.history))
        quiet = asks_nothing(rest, stopped, names) and not any(rules.get(k) for k in ("order_id", "pieces", "due_date", "customer", "product"))
        req = rules if quiet else self.parser(rest_line, list(self.history))
        req["raw_text"] = text
        req["held_orders"] = held
        if quiet and len(stopped) == 1:
            req["stop_report"] = stopped[0]
        else:
            self._add_stop_mentions(req, stopped)
            if held:
                req["extra_notes"] = [f"message says {', '.join(held)} already at the stopped workshop; not treated as new dispatches"]
        return req

    def _parse_all(self, line: str) -> List[dict]:
        """One parsed request per order number. Whatever cannot be handled is noted on the card, never dropped silently."""
        names = {wid: w.name for wid, w in self.W.items()}
        rid, stamp, who, text = parse_header(line)
        stopped, rest = read_stops(text, names)
        held, rest = take_held(rest) if stopped else ([], rest)
        rest = normalise_ids(rest)
        ids = list(dict.fromkeys(order_ids(rest)))
        unread = suspect_ids(rest, self.O)
        if rid and rid in self.decisions:       # a later line must not replace a card that took this id
            new_rid = self.next_request_id()
            line, rid = line.replace(rid, new_rid, 1), new_rid
        if rid:
            self.taken_ids.add(rid)
        question = unhandled_question(rest)
        asked_too = bool(question and DISPATCH_WORD_RE.search(rest.replace(question, "")))
        if asked_too:       # read the request alone, or the question would hide it
            rest, line = rest.replace(question, "").strip(), line.replace(question, "")
        rules = RuleBasedParser().parse(rest)
        if len(ids) >= 2 and looks_like_dispatch(rest, rules["question_type"]):
            parts, unclear, extras = split_orders(rest)
            rids = [rid or self.next_request_id()] + [self.next_request_id() for _ in parts[1:]]
            reqs = []
            for prid, (oid, part) in zip(rids, parts):
                req = self.parser(f"{prid} [{stamp or datetime.now().strftime('%H:%M')}] {who or 'Unknown'}: {part}", list(self.history))
                req["raw_text"], req["source_message"] = part, text
                req["extra_notes"] = [f"one of {len(parts)} orders in this message; the others: {', '.join(r for r in rids if r != prid)}"]
                if unclear:
                    req["extra_notes"].append("part of this message is not clear which order it belongs to, so it is not applied and the order book's values are used; read the message")
                if held:
                    req["extra_notes"].append(f"message says {', '.join(held)} already at the stopped workshop; not treated as new dispatches")
                if question:
                    req["extra_notes"].append(f"this message also asks something not handled here: \"{question}\"")
                if extras:
                    req["extra_notes"].append(f"this message also mentions {', '.join(extras)}; not handled here")
                if unread:
                    req["extra_notes"].append("this message may name more orders than could be read; please check")
                req["extra_notes"] += self._other_customer_note(oid, part, rest)
                if stopped:
                    self._add_stop_mentions(req, stopped)
                reqs.append(req)
            return reqs
        req = self._parse(line)
        req["raw_text"] = text
        notes = req.setdefault("extra_notes", [])
        batches = other_batches(rest)
        if len(ids) >= 2:
            notes.append(f"this message also names {', '.join(ids[1:])}; not handled here")
            if rules["question_type"] == "allocation" and NOT_A_REQUEST_RE.search(rest) and not stopped:
                req["unsure_orders"] = ids
        elif ids and len(batches) >= 2:
            notes.append(f"this message also mentions {', '.join(batches[1:])}; not handled here")
        elif not ids and len(batches) >= 2:
            req["multi_batches"] = batches
        elif ids:
            notes += self._other_customer_note(ids[0], rest, rest)
            beside = re.search(r"\bORD-\d{1,3}\s+(?:and|plus|&)\s+(\d[^,.;]*)", rest, re.I)
            if beside:      # "ORD-053 and 300 scarves": the quantity may not be this order's
                notes.append(f"this message also mentions {beside.group(1).strip()}; not handled here")
        if unread:
            notes.append("this message may name more orders than could be read; please check")
        if question and (asked_too or rules["question_type"] == "allocation"):
            notes.append(f"this message also asks something not handled here: \"{question}\"")
        return [req]

    def _other_customer_note(self, order_id: str, text: str, whole: str) -> List[str]:
        """'ORD-041 and also the Cotton Club vests': something beside this order that the card does not cover."""
        order = self.O.get(order_id)
        if not order or not ALSO_RE.search(whole):
            return []
        rules = RuleBasedParser().parse(text)
        others = [v for v, own in ((rules["customer"], order.customer), (rules["product"], order.product)) if v and v.lower() != own.lower()]
        return [f"this message also mentions {', '.join(others)}, which is not {order_id}; not handled here"] if others else []

    @staticmethod
    def _add_stop_mentions(req: dict, stopped: List[str]) -> None:
        """Keep these shops out of this request only, until a person confirms or dismisses the stop."""
        req["stop_mentions"] = sorted(set(req.get("stop_mentions", [])) | set(stopped))
        req["stop_added"] = sorted(set(req.get("stop_added", [])) | (set(stopped) - set(req["excluded_workshops"])))
        req["excluded_workshops"] = sorted(set(req["excluded_workshops"]) | set(stopped))
        if req["forced_workshop"] in stopped:
            req["stop_forced"], req["forced_workshop"] = req["forced_workshop"], None

    @staticmethod
    def _clear_stop_mention(req: dict, wid: str) -> None:
        """Undo _add_stop_mentions() for one shop. What the message itself ruled out stays ruled out."""
        req["stop_mentions"] = [w for w in req.get("stop_mentions", []) if w != wid]
        if wid in req.get("stop_added", []):
            req["stop_added"].remove(wid)
            req["excluded_workshops"] = [w for w in req["excluded_workshops"] if w != wid]
        if req.get("stop_forced") == wid:
            req["forced_workshop"], req["stop_forced"] = wid, None

    def pending_stops(self) -> Dict[str, str]:
        """Workshops someone has said have stopped, not yet confirmed or dismissed: workshop_id -> request_id."""
        out: Dict[str, str] = {}
        for rid, d in self.decisions.items():
            if d["status"] == "closure_reported":
                out.setdefault(d["reported_workshop"], rid)
            elif d["status"] != "dismissed":
                for wid in d.get("stop_mentions", []):
                    if wid not in self.stopped:
                        out.setdefault(wid, rid)
        return out

    def blocked_for_move(self, rec: dict) -> set:
        """Where a dispatched batch may not go: what its own request ruled out, standing bans and stopped shops."""
        d = self.decisions.get(rec["request_id"])
        own = set(d["parsed"]["excluded_workshops"]) if d else set()
        return own | set(self.session_excl) | set(self.stopped)

    def _batches_at(self, wid: str) -> List[dict]:
        return [r for r in self.ledger.records if r["status"] == "committed" and r["workshop_id"] == wid]

    def exclusions_for(self, req: dict) -> set:
        return set(req["excluded_workshops"]) | set(self.session_excl) | set(self.stopped)

    def _set_later(self, wid: str, req: dict) -> bool:
        """True when the standing constraint on wid was set by a message that arrived after req."""
        src = self.session_excl.get(wid)
        mine = self.arrival.get(req.get("request_id"))
        return bool(src and mine is not None and src.get("seq", -1) > mine)

    def _excl_label(self, wid: str, req: dict) -> str:
        if wid in self.stopped:
            return f"{self.name(wid)} (stopped, confirmed by {self.stopped[wid]['by']})"
        src = self.session_excl.get(wid)
        if src and wid not in req["excluded_workshops"]:
            when = (f", set at {src['time']}, after this request arrived; it applies while the request is open"
                    if self._set_later(wid, req) else "")
            return f"{self.name(wid)} (excluded by {src['by']} in {src['source']}{when})"
        return f"{self.name(wid)} (excluded in this request)"

    def _log(self, request_id: Optional[str], action: str, by: str, note: str = "") -> dict:
        entry = {"at": datetime.now().isoformat(timespec="seconds"), "request_id": request_id, "action": action, "by": by, "note": note}
        self.actions.append(entry)
        return entry

    # ---------------------------------------------------------------- routing
    def route(self, req: dict) -> dict:
        d = {"request_id": req["request_id"], "timestamp": req["timestamp"], "requester": req["requester"],
             "raw_text": req.get("source_message") or req["raw_text"], "parsed": req, "tool_calls": [], "subtype": None, "order_id": req["order_id"],
             "recommended": None, "candidates": [], "eligibility": [], "explanation": "", "committed": None,
             "flags": [], "batch": None, "order_candidates": [], "refused_workshop": None}

        # a workshop reported as stopped: flag it for the dispatcher; nothing changes until they confirm
        reported = req.get("stop_report")
        if reported:
            batches = self._batches_at(reported)
            d["subtype"] = "closure_report"
            d["reported_workshop"] = reported
            d["tool_calls"].append({"tool": "workshop_batches", "input": reported,
                                    "output": {"count": len(batches), "orders": [r["order_id"] for r in batches]}})
            d["explanation"] = (f"{self.name(reported)} is reported as stopped. Nothing changes until you confirm. Once you do, no new work "
                                f"goes there, and {len(batches)} dispatched {'batch' if len(batches) == 1 else 'batches'} there can be re-dispatched.")
            if reported in self.stopped:
                d["explanation"] = f"{self.name(reported)} is reported as stopped; it is already marked as stopped."
            if req.get("held_orders"):
                d["explanation"] += f" The message says {', '.join(req['held_orders'])} are held there."
            return d

        # several batches and no order numbers: say what was heard and ask, do not guess which orders they are
        if req.get("multi_batches"):
            d["subtype"] = "ambiguous_reference"
            d["tool_calls"].append({"tool": "message_batches", "output": {"count": len(req["multi_batches"]), "batches": req["multi_batches"]}})
            d["explanation"] = (f"This message mentions {len(req['multi_batches'])} batches: {'; '.join(req['multi_batches'])}. "
                                "Which orders are they? Please send each with its order number.")
            return d

        # several order numbers and words like "not", "already", "don't": ask which are to be sent
        if req.get("unsure_orders"):
            d["subtype"] = "ambiguous_reference"
            d["tool_calls"].append({"tool": "message_orders", "output": {"orders": req["unsure_orders"]}})
            d["explanation"] = (f"This message names {', '.join(req['unsure_orders'])}, but may not be asking to send them all. "
                                "Which of them should go out now? Please resend those order numbers.")
            return d

        # 1. questions the data cannot answer
        if req["question_type"] == "information":
            d["subtype"] = "not_in_data"
            d["explanation"] = ("I can't answer that from the data: the system holds current orders and workshop profile cards only. "
                                "There is no dispatch history and no price quoted to customers (cost_per_piece is what workshops charge us).")
            return d
        order = self.O.get(req["order_id"]) if req["order_id"] else None
        if req["order_id"] and order is None:
            d["subtype"] = "not_in_data"
            d["tool_calls"].append({"tool": "state_checks", "output": ["order not found"]})
            d["explanation"] = f"{req['order_id']} does not exist in the order book, so I can't report on it or dispatch it. Please check the order number."
            return d
        # a status reply skips every later check, so first make sure the message is about the order its id names:
        # "ORD-035: 600 cardigans for UrbanThread, sent it out" names another order. Dispatch requests go on to the
        # usual checks, which record any difference (labelling rules: note both, do not stop).
        clash = self._identity_clash(order, req) if order and req["question_type"] == "status" else ""
        if clash:
            d["subtype"] = "state_conflict"
            d["tool_calls"].append({"tool": "resolve_order_reference", "input": {"order_id": order.order_id},     # the record the reply quotes
                                    "output": {"count": 1, "orders": [{"order_id": order.order_id, "customer": order.customer, "product": order.product,
                                                                       "pieces": order.pieces, "due_date": order.due_date.isoformat(),
                                                                       "stage": order.current_stage}]}})
            d["tool_calls"].append({"tool": "state_checks", "input": order.order_id, "output": [f"message names {clash}"]})
            d["explanation"] = (f"{order.order_id} in the order book is {order.customer}, {order.product}, {order.pieces} pcs, due {order.due_date}, "
                                f"but your message names {clash}. Which order do you mean?")
            return d
        if req["question_type"] == "status":
            d["subtype"] = "not_in_data"
            d["explanation"] = "Progress tracking is outside this desk; it only allocates batches to workshops."
            return d

        # 2. which order?
        if order is None:
            prior = next((h for h in self.history if h["request_id"] == req.get("references_prior")), None)
            prior_dec = self.decisions.get(prior["request_id"]) if prior else None
            low = req["raw_text"].lower()
            window = last_week(TODAY) if "last week" in low else (None, None)
            big = bool(re.search(r"\bbig\b|\blarge\b|\bbiggest\b", low))
            cands = (find_orders(self.O, customer=req["customer"], product=req["product"], placed_from=window[0], placed_to=window[1],
                                 largest_first=big) if (req["customer"] or req["product"] or window[0]) else [])
            d["tool_calls"].append({"tool": "resolve_order_reference",
                                    "input": {"customer": req["customer"], "product": req["product"],
                                              "placed_from": window[0].isoformat() if window[0] else None,
                                              "placed_to": window[1].isoformat() if window[1] else None, "largest_first": big},
                                    "output": {"count": len(cands),
                                               "orders": [{"order_id": o.order_id, "customer": o.customer, "product": o.product,
                                                           "pieces": o.pieces, "due_date": o.due_date.isoformat(), "stage": o.current_stage}
                                                          for o in cands]}})
            listing = "; ".join(f"{o.order_id} {o.customer} {o.product} {o.pieces} pcs due {o.due_date}" for o in cands)
            # not an order yet, or the message leaves quantity / date undefined: ask for the details, do not guess an order
            new_work = bool(NEW_ORDER_RE.search(req["raw_text"]) or ({"pieces", "due_date"} & set(req["missing_fields"]))
                            or (prior_dec and prior_dec["subtype"] == "missing_fields" and not cands))
            if new_work:
                d["subtype"] = "missing_fields"
                d["order_candidates"] = [o.order_id for o in cands]
                ref = f" (follow-up to {prior['request_id']})" if prior else ""
                d["explanation"] = (f"I can't book capacity yet{ref}: I need the order number, piece count and due date. "
                                    "Capacity depends on them, so I won't guess."
                                    + (f" If you mean an order already in progress, say which: {listing}." if cands else ""))
                return d
            if len(cands) > 1 and (req["pieces"] or req["due_date"]):
                # several orders fit the customer and product; the piece count and due date in the message may single one out
                fit = [o for o in cands if (not req["pieces"] or o.pieces == req["pieces"])
                       and (not req["due_date"] or o.due_date.isoformat() == req["due_date"])]
                if len(fit) == 1:
                    d["flags"].append(f"{len(cands)} orders match the customer and product; only {fit[0].order_id} matches the pieces and due date")
                    cands = fit
            if len(cands) == 1:
                order = cands[0]
                d["order_id"] = order.order_id
                d["flags"].append(f"resolved uniquely to {order.order_id}")
            else:
                d["subtype"] = "ambiguous_reference"
                d["order_candidates"] = [o.order_id for o in cands]
                if cands:
                    scope = f" placed last week ({window[0]} to {window[1]}), largest first" if window[0] else ""
                    d["explanation"] = f"Which order do you mean? {len(cands)} in-progress orders match{scope}: {listing}."
                    if prior_dec and prior_dec["subtype"] == "missing_fields":
                        d["explanation"] += f" Or is this the new work from {prior['request_id']}? Then I need the piece count and due date."
                else:
                    d["explanation"] = "Which order do you mean? The message doesn't name an order, customer or product I can match."
                return d

        # 3. state conflicts
        flags = state_checks(order, TODAY, self.ledger)
        d["tool_calls"].append({"tool": "state_checks", "input": order.order_id, "output": flags})
        d["flags"] += flags + self._mismatch_notes(order, req)
        # v3 data dictionary: the inbox is about orders still in progress, so an in-house stage (even PACKING)
        # is context for the dispatcher, not a reason to stop. A finished order or a repeat dispatch is.
        conflict = [f for f in flags if "COMPLETE" in f or "already dispatched" in f]
        if conflict:
            d["subtype"] = "state_conflict"
            d["explanation"] = f"Before I place {order.order_id}: {'; '.join(conflict)}. Do you still want it sent outside?"
            # one message, two problems: say both and let the dispatcher decide; neither hides the other
            batch = self._batch(order, req)
            shop = req["forced_workshop"] or req.get("stop_forced")
            why = self._forced_problem(shop, batch) if req["forced_workshop"] else ("it is reported as stopped" if shop else "")
            if why:
                d["refused_workshop"] = shop
                d["tool_calls"].append({"tool": "eligibility_table", "input": {"category": batch["category"], "pieces": batch["pieces"]},
                                        "output": eligibility_table(self.W, batch["category"], batch["pieces"])})
                d["explanation"] = (f"Two problems with {order.order_id}: {'; '.join(conflict)}. Also, {self.name(shop)} can't take it: {why}. "
                                    "Do you still want it sent outside, and to which workshop?")
            return d

        # 4. missing information the order book can't fill
        if "due_date" in req["missing_fields"]:
            d["subtype"] = "missing_fields"
            d["explanation"] = (f"{order.order_id}: the new due date isn't confirmed yet, and the estimate depends on it. "
                                "I'll hold off until the date is confirmed.")
            return d

        batch = self._batch(order, req)
        excl = self.exclusions_for(req)
        if self.session_excl:
            d["tool_calls"].append({"tool": "standing_constraints",
                                    "output": {wid: {"workshop": self.name(wid), "by": v["by"], "source": v["source"], "time": v.get("time", "")}
                                               for wid, v in self.session_excl.items()}})
        if self.stopped:
            d["tool_calls"].append({"tool": "stopped_workshops", "output": {wid: {"workshop": self.name(wid), "by": v["by"]} for wid, v in self.stopped.items()}})
        pref = req["preference"] if req["preference"] in ("fastest", "cheapest_on_time", "lowest_defect") else None
        rows = self.alloc.rank(batch, self.W, self.ledger.queues(), exclude=excl, preference=pref)
        ests = [r["estimate"] for r in rows]
        table = eligibility_table(self.W, batch["category"], batch["pieces"], exclude=excl)
        for row in table:
            src = self.session_excl.get(row["workshop_id"])
            if row["workshop_id"] in self.stopped and row["reason"] == "excluded by request":
                row["reason"] = f"stopped, confirmed by {self.stopped[row['workshop_id']]['by']}"
            elif src and row["reason"] == "excluded by request" and row["workshop_id"] not in req["excluded_workshops"]:
                row["reason"] = f"excluded by {src['by']} in {src['source']} (this week)"
                if self._set_later(row["workshop_id"], req):
                    row["reason"] += "; set after this request arrived"
        d["tool_calls"].append({"tool": "eligibility_table", "input": {"category": batch["category"], "pieces": batch["pieces"],
                                "exclude": sorted(excl)}, "output": table})
        d["tool_calls"].append({"tool": "rank_candidates", "input": {"objective": self.alloc.objective, "preference": pref},
                                "output": [e.as_dict() for e in ests]})
        d["candidates"] = [e.as_dict() for e in ests]
        d["eligibility"] = table
        d["batch"] = {k: (v.isoformat() if isinstance(v, date) else v) for k, v in batch.items()}
        excl_text = ""
        if excl:
            excl_text = " Not considered: " + ", ".join(self._excl_label(wid, req) for wid in sorted(excl)) + "."
            for wid in sorted(excl):
                if self._set_later(wid, req):
                    d["flags"].append(f"standing constraint on {self.name(wid)} was set later, in {self.session_excl[wid]['source']}; "
                                      "it applies because this request is still open")

        # 5. ineligible suggestion
        fw = req["forced_workshop"]
        if fw:
            why = self._forced_problem(fw, batch)
            if why:
                d["subtype"] = "ineligible_suggestion"
                d["recommended"] = ests[0].workshop_id if ests else None
                d["refused_workshop"] = fw
                others = [w for w in sorted(excl) if w != fw]
                d["explanation"] = f"{self.name(fw)} can't take {order.order_id}: {why}. {self._alt_text(ests)}{excl_text if others else ''}"
                return d

        # 6. extract: on time or not
        if not ests:
            d["subtype"] = "no_on_time_option"
            d["explanation"] = f"No eligible workshop can make {order.order_id} ({batch['category']}, {batch['pieces']} pcs).{excl_text} Escalating to a human."
            return d
        best = ests[0]
        d["recommended"] = best.workshop_id
        if best.on_time:
            d["subtype"] = "allocate"
            runner = next((e for e in ests[1:]), None)
            fastest = min((e for e in ests if e.on_time), key=lambda e: e.finish_days)
            d["why"] = self._why(rows[0], pref, best, fastest)
            d["explanation"] = (f"Recommend {best.name} for {order.order_id} ({batch['pieces']} pcs): {self._why(rows[0], pref, best, fastest)}. "
                                f"Estimate {best.finish_days:.1f} days = queue {best.queue_days:.1f} + work {best.work_days:.1f} "
                                f"+ expected rework {best.rework_days:.1f} + transport {best.lead_days:.0f}; back {best.promised_date}"
                                + (f" ({best.worst_date} if the batch is reworked)" if best.worst_date != best.promised_date else "")
                                + f", due {batch['due_date']}. Cost {best.cost:.0f}, defect rate {best.defect_rate:.0%}."
                                + (f" Fastest: {fastest.name}, {fastest.finish_days:.1f} days, back {fastest.promised_date}."
                                   if fastest.workshop_id != best.workshop_id else
                                   (f" Next best: {runner.name}, {runner.finish_days:.1f} days, back {runner.promised_date}." if runner else ""))
                                + excl_text)
            if req["preference"] == "split":
                s = split_estimate(self.W, batch["category"], batch["pieces"], self.ledger.queues(), TODAY, batch["due_date"], exclude=excl)
                d["tool_calls"].append({"tool": "split_estimate", "output": s})
                d["explanation"] += f" No split needed: {best.name} alone is on time."
                if s.get("possible") and s["gain_days"] >= 0.5:
                    d["explanation"] += (f" A two-shop split would finish {s['gain_days']:.1f} days sooner than the fastest single shop; "
                                         "the shared simulator cannot split, so that is a chat-layer estimate.")
        else:
            d["subtype"] = "no_on_time_option"
            late_word = "already past due" if batch["due_date"] < TODAY else f"due {batch['due_date']}"
            d["explanation"] = (f"No workshop can return {order.order_id} on time ({late_word}). "
                                f"Earliest is {best.name}: back {best.promised_date}, {days(best.late_days)} late ({best.finish_days:.1f} days). "
                                "Options: accept the delay, renegotiate the date with the customer, relax a constraint, or escalate."
                                + excl_text)
            if req["preference"] == "split":
                s = split_estimate(self.W, batch["category"], batch["pieces"], self.ledger.queues(), TODAY, batch["due_date"], exclude=excl)
                d["tool_calls"].append({"tool": "split_estimate", "output": s})
                if s.get("possible"):
                    d["explanation"] += (f" Splitting across two shops gains {s['gain_days']:.1f} days"
                                         + (", so it doesn't help." if s["gain_days"] < 0.5 else "."))
            if fw is None and self.session_excl:
                lifted = [r["estimate"] for r in self.alloc.rank(batch, self.W, self.ledger.queues(),
                                                                 exclude=set(req["excluded_workshops"]) | set(self.stopped), preference=pref)]
                d["tool_calls"].append({"tool": "rank_candidates", "input": {"exclude": sorted(set(req["excluded_workshops"]) | set(self.stopped)), "note": "session ban lifted"},
                                        "output": [e.as_dict() for e in lifted]})
                if lifted and lifted[0].workshop_id in self.session_excl:
                    l0 = lifted[0]
                    d["explanation"] += (f" If the ban on {l0.name} were lifted: back {l0.promised_date}"
                                         + (", on time." if l0.on_time else f", {days(l0.late_days)} late."))
        return d

    def _why(self, row: dict, pref: Optional[str], best, fastest) -> str:
        """One clause saying why this workshop is first. No numbers: those come from the estimate."""
        if pref:
            return {"fastest": "fastest turnaround", "cheapest_on_time": "cheapest workshop that still makes the date",
                    "lowest_defect": "lowest defect rate among on-time options"}[pref]
        if "tier" not in row:
            return "earliest on-time finish" if self.alloc.objective == "lateness_v1" else f"best score under the {self.alloc.objective} objective"
        safe = ("on time even if the batch is reworked" if row["tier"] == 0
                else "on time, though a rework would make it late (no eligible shop is safe against that)")
        if fastest.workshop_id == best.workshop_id:
            return safe + "; earliest finish among those"
        w = self.W[best.workshop_id]
        only = "it only makes " + "+".join(sorted(w.makes)) if len(w.makes) == 1 else "it is the less flexible shop"
        if w.max_batch is not None:
            only += " and is capped at small batches"
        return safe + f"; {only}, so the shops that can take other work stay free for tighter batches"

    def _alt_text(self, ests) -> str:
        if not ests:
            return "No other eligible workshop can take it."
        on = [e for e in ests if e.on_time]
        e = on[0] if on else ests[0]
        return (f"Alternative: {e.name}, back {e.promised_date}"
                + (" (on time)." if e.on_time else f" ({days(e.late_days)} late; nothing makes the date)."))

    def _finish(self, d: dict, req: dict) -> dict:
        d["official_behaviour"] = OFFICIAL[d["subtype"]]
        d["status"] = STATUS[d["subtype"]]
        d["number_check"] = number_check(d["explanation"], d["tool_calls"], d.get("batch"), req)
        d["flags"] += req.get("extra_notes", [])
        d["stop_mentions"] = [w for w in req.get("stop_mentions", []) if w not in self.stopped]
        d["flags"] += [f"message says {self.name(w)} may have stopped; kept out of this request until someone confirms" for w in d["stop_mentions"]]
        src = self.pending_stops().get(d["recommended"])
        if src and src != d["request_id"]:
            d["flags"].append(f"{self.name(d['recommended'])} is reported as stopped in {src}, not yet confirmed")
        return d

    # ---------------------------------------------------------------- dispatcher API
    def propose(self, line: str) -> dict:
        """Route one chat line. Writes nothing to the ledger. A line with several orders becomes several decisions;
        the first is returned and the rest are in self.decisions."""
        self.last_proposed = [self._propose_one(req) for req in self._parse_all(line)]
        return self.last_proposed[0]

    def _propose_one(self, req: dict) -> dict:
        if not req.get("request_id"):
            req["request_id"] = self.next_request_id()
        self.arrival[req["request_id"]] = len(self.arrival)
        d = self._finish(self.route(req), req)
        if req["constraint_scope"] == "session" and not req.get("stop_report"):
            for wid in [w for w in req["excluded_workshops"] if w not in req.get("stop_added", [])]:
                said_once = req.get("source_message")       # one ban in a message split into several cards
                if said_once and self.session_excl.get(wid, {}).get("message") == said_once:
                    continue
                by = "Boss" if re.search(r"\bboss\b", req["raw_text"], re.I) else req["requester"]
                self.session_excl[wid] = {"by": by, "source": req["request_id"], "time": req.get("timestamp") or "",
                                          "seq": self.arrival[req["request_id"]], "message": said_once}
                d["flags"].append(f"session constraint recorded: exclude {self.name(wid)} (by {by})")
        d["received_at"] = datetime.now().isoformat(timespec="seconds")
        d["as_received"] = {"subtype": d["subtype"], "recommended": d["recommended"]}
        self.history.append(req)
        self.decisions[req["request_id"]] = d
        return d

    def is_open(self, d: dict) -> bool:
        return not d["committed"] and d["status"] not in HUMAN_STATUSES

    def refresh(self, request_id: str) -> dict:
        """Re-route an open request against the current ledger and constraints."""
        d = self.decisions[request_id]
        if not self.is_open(d):
            return d
        req = d["parsed"]
        new = self._finish(self.route(req), req)
        new["received_at"] = d.get("received_at")
        new["as_received"] = d.get("as_received")
        new["flags"] += [f for f in d["flags"] if f.startswith("session constraint recorded")]
        if new["recommended"] != d["recommended"] or new["subtype"] != d["subtype"]:
            new["flags"].append(f"updated since received: was {d['subtype']} / {d['recommended'] or '-'}")
        self.decisions[request_id] = new
        return new

    def refresh_all(self) -> None:
        for rid in list(self.decisions):
            self.refresh(rid)

    def new_message(self, sender: str, text: str) -> dict:
        text = re.sub(r"\s*\n\s*", ". ", text.strip())     # a request line is one line; a line break ends a sentence
        line = f"{self.next_request_id()} [{datetime.now():%H:%M}] {sender}: {text}"
        return self.propose(line)

    def follow_up(self, request_id: str, text: str, by: str = "dispatcher") -> dict:
        """The requester's answer to a clarifying question, processed as a new message."""
        d = self.decisions[request_id]
        new = self.new_message(d["requester"], text)
        cards = list(self.last_proposed)
        asked = d["parsed"].get("multi_batches") or []
        for card in cards:
            if d["parsed"].get("stop_mentions"):    # the answer does not repeat that a shop has stopped
                self._add_stop_mentions(card["parsed"], d["parsed"]["stop_mentions"])
            if len(asked) > len(cards):
                card["parsed"].setdefault("extra_notes", []).append(f"the question was about {', '.join(asked)}; this answer covers {len(cards)}; not handled here")
            self.refresh(card["request_id"])
        new = self.decisions[new["request_id"]]
        new["flags"].append(f"answer to {request_id}")
        d["status"] = "reply_sent"
        d["follow_up"] = new["request_id"]
        self._log(request_id, "follow_up", by, f"{new['request_id']}: {text}")
        return new

    def mark(self, request_id: str, status: str, by: str = "dispatcher", note: str = "") -> dict:
        if status not in HUMAN_STATUSES:
            raise ValueError(f"unknown status {status!r}")
        d = self.decisions[request_id]
        if d["committed"]:
            raise ValueError(f"{request_id} is already committed as {d['committed']}")
        d["status"] = status
        self._log(request_id, status, by, note)
        return d

    def confirm(self, request_id: str, workshop_id: Optional[str] = None, by: str = "dispatcher",
                accept_late: bool = False) -> dict:
        """Human confirmation. Re-estimates against the current ledger, then commits."""
        d = self.refresh(request_id)
        if d["committed"]:
            raise ValueError(f"{request_id} already committed as {d['committed']}")
        if d["subtype"] not in ("allocate", "no_on_time_option", "ineligible_suggestion"):
            raise ValueError(f"{request_id} is {d['subtype']}; there is nothing to commit")
        wid = workshop_id or d["recommended"]
        if wid is None:
            raise ValueError(f"{request_id} has no eligible workshop")
        req = d["parsed"]
        order = self.O[d["order_id"]]
        batch = self._batch(order, req)
        ok, why = check_eligibility(self.W[wid], batch["category"], batch["pieces"])
        if not ok:
            raise ValueError(f"{self.name(wid)} cannot take {order.order_id}: {why}")
        if wid in self.stopped:
            raise ValueError(f"{self.name(wid)} is marked as stopped; reopen it first")
        if wid in self.exclusions_for(req):
            src = self.session_excl.get(wid)
            raise ValueError(f"{self.name(wid)} is excluded" + (f" by {src['by']} ({src['source']}); lift the constraint first" if src else " by this request"))
        fresh = estimate(self.W[wid], batch["pieces"], self.ledger.queues()[wid], TODAY, batch["due_date"])
        if not fresh.on_time and not accept_late:
            raise ValueError(f"{self.name(wid)} would be {days(fresh.late_days)} late; confirm again accepting the delay")
        note = []
        if wid != d["recommended"]:
            note.append(f"dispatcher chose {self.name(wid)} over the recommended {self.name(d['recommended'])}")
        if not fresh.on_time:
            note.append(f"delay accepted: {days(fresh.late_days)} late")
        rec = self.ledger.commit(request_id=request_id, order_id=order.order_id, workshop_id=wid,
                                 category=order.category, pieces=batch["pieces"], sent_date=TODAY, due_date=batch["due_date"],
                                 requester=req["requester"], confirmed_by=by, reason=" | ".join([d["explanation"]] + note),
                                 constraints={"excluded": sorted(self.exclusions_for(req)), "session": copy.deepcopy(self.session_excl),
                                              "stopped": copy.deepcopy(self.stopped)},
                                 candidates=d["candidates"], objective={"name": self.alloc.objective, "preference": req["preference"]},
                                 model_version=req["parser"])
        self.alloc.load[wid] = self.alloc.load.get(wid, 0) + batch["pieces"]
        d["committed"] = rec["audit_id"]
        d["status"] = "committed"
        d["confirmed_workshop"] = wid
        d["confirmed_by"] = by
        d["confirm_notes"] = note
        d["final_estimate"] = fresh.as_dict()
        self._log(request_id, "confirm", by, f"{rec['audit_id']} -> {self.name(wid)}" + (f" ({'; '.join(note)})" if note else ""))
        return rec

    def reassign(self, audit_id: str, workshop_id: str, by: str = "dispatcher", reason: str = "reassigned by dispatcher") -> dict:
        old = next((r for r in self.ledger.records if r["audit_id"] == audit_id), None)
        if old is None:
            raise ValueError(f"no audit record {audit_id}")
        ok, why = check_eligibility(self.W[workshop_id], old["category"], old["pieces"])
        if not ok:
            raise ValueError(f"{self.name(workshop_id)} cannot take {old['order_id']}: {why}")
        if workshop_id in self.blocked_for_move(old):
            raise ValueError(f"{self.name(workshop_id)} cannot take {old['order_id']}: it is stopped, banned, or ruled out by the request")
        rec = self.ledger.reassign(audit_id, workshop_id, confirmed_by=by, reason=reason)
        self.alloc.load[old["workshop_id"]] = self.alloc.load.get(old["workshop_id"], 0) - old["pieces"]
        self.alloc.load[workshop_id] = self.alloc.load.get(workshop_id, 0) + old["pieces"]
        for d in self.decisions.values():
            if d["committed"] == audit_id:
                d["committed"] = rec["audit_id"]
                d["confirmed_workshop"] = workshop_id
                d["confirm_notes"] = (d.get("confirm_notes") or []) + [f"reassigned from {audit_id} to {self.name(workshop_id)}"]
                d["final_estimate"] = rec["estimate"]
        self._log(old["request_id"], "reassign", by, f"{audit_id} -> {rec['audit_id']} {self.name(workshop_id)}: {reason}")
        # the replay re-estimated every live batch; keep decisions in step with the ledger
        live = {r["request_id"]: r for r in self.ledger.records if r["status"] == "committed"}
        for d in self.decisions.values():
            if d["committed"] and d["request_id"] in live:
                d["committed"] = live[d["request_id"]]["audit_id"]
                d["final_estimate"] = live[d["request_id"]]["estimate"]
        self.refresh_all()
        return rec

    def mark_stopped(self, workshop_id: str, by: str = "dispatcher", source: Optional[str] = None) -> None:
        """A person confirmed the workshop has stopped: no new work goes there until reopen()."""
        if workshop_id in self.stopped:
            return
        self.stopped[workshop_id] = {"by": by, "source": source or "dispatcher", "time": f"{datetime.now():%H:%M}"}
        self._log(source, "mark_stopped", by, self.name(workshop_id))
        self.refresh_all()

    def reopen(self, workshop_id: str, by: str = "dispatcher") -> None:
        """Ends a stop, and what messages ruled out because of it. A ban on the same workshop is separate and stays."""
        self.stopped.pop(workshop_id, None)
        for d in self.decisions.values():
            self._clear_stop_mention(d["parsed"], workshop_id)
            d["stop_mentions"] = [w for w in d.get("stop_mentions", []) if w != workshop_id]
        self._log(None, "reopen", by, self.name(workshop_id))
        self.refresh_all()

    def dismiss_stop_mention(self, request_id: str, workshop_id: str, by: str = "dispatcher") -> dict:
        """The dispatcher says the message was wrong, or was misread: the shop can take this request after all."""
        d = self.decisions[request_id]
        self._clear_stop_mention(d["parsed"], workshop_id)
        d["stop_mentions"] = [w for w in d.get("stop_mentions", []) if w != workshop_id]
        self._log(request_id, "dismiss_stop_mention", by, self.name(workshop_id))
        return self.refresh(request_id)

    def confirm_closure(self, request_id: str, by: str = "dispatcher") -> None:
        d = self.decisions[request_id]
        if d["status"] != "closure_reported":
            raise ValueError(f"{request_id} is not an open report of a stopped workshop")
        d["status"] = "closure_confirmed"
        self.mark_stopped(d["reported_workshop"], by, source=request_id)

    def stopped_impact(self) -> List[dict]:
        """Batches already at a stopped workshop, each with the best place to move it now. Writes nothing."""
        rows = []
        for wid in self.stopped:
            for r in self._batches_at(wid):
                due = r["due_date"] if isinstance(r["due_date"], date) else date.fromisoformat(r["due_date"])
                batch = {"order_id": r["order_id"], "category": r["category"], "pieces": r["pieces"], "sent_date": TODAY, "due_date": due}
                pref = self.decisions[r["request_id"]]["parsed"]["preference"]
                pref = pref if pref in ("fastest", "cheapest_on_time", "lowest_defect") else None
                ranked = self.alloc.rank(batch, self.W, self.ledger.queues(), exclude=self.blocked_for_move(r), preference=pref)
                best = ranked[0]["estimate"].as_dict() if ranked else None
                rows.append({"audit_id": r["audit_id"], "request_id": r["request_id"], "order_id": r["order_id"], "pieces": r["pieces"],
                             "workshop_id": wid, "due_date": due.isoformat(), "best": best})
        return rows

    def lift_constraint(self, workshop_id: str, by: str = "dispatcher") -> dict:
        src = self.session_excl.pop(workshop_id, None)
        self._log(src["source"] if src else None, "lift_constraint", by, f"{self.name(workshop_id)} (set by {src['by'] if src else '-'})")
        self.refresh_all()
        return {"workshop_id": workshop_id, "was": src, "lifted_by": by}

    def bulk_plan(self, only_safe: bool = True) -> dict:
        """Which open on-time recommendations a bulk confirm would take, on the ledger as it stands.
        Writes nothing. Held back: tight requests (a rework would make them late), and safe requests
        whose workshop a tight request also counts on."""
        self.refresh_all()
        open_alloc = [(rid, d) for rid, d in self.decisions.items() if self.is_open(d) and d["subtype"] == "allocate"]
        open_alloc.sort(key=lambda x: self.arrival.get(x[0], 10 ** 9))
        best = {rid: next(c for c in d["candidates"] if c["workshop_id"] == d["recommended"]) for rid, d in open_alloc}
        pending = self.pending_stops()
        tight = {}
        if only_safe:
            for rid, d in open_alloc:
                if not best[rid].get("safe") and d["recommended"] not in pending:
                    tight.setdefault(d["recommended"], []).append(rid)
        go, held = [], []
        for rid, d in open_alloc:
            if d["recommended"] in pending:
                held.append({"request_id": rid, "reason": f"reported stopped: {self.name(d['recommended'])}, in {pending[d['recommended']]}; decide that first"})
            elif only_safe and not best[rid].get("safe"):
                held.append({"request_id": rid, "reason": "tight: on time, but not if the batch is reworked"})
            elif only_safe and tight.get(d["recommended"]):
                held.append({"request_id": rid, "reason": f"would use {self.name(d['recommended'])}, which tight request "
                                                          f"{', '.join(tight[d['recommended']])} also needs; decide that first"})
            else:
                go.append(rid)
        return {"confirm": go, "held": held}

    def confirm_all(self, by: str = "dispatcher", only_safe: bool = True) -> dict:
        """One human click: confirm what bulk_plan() lists, in arrival order. Each request is re-estimated
        against the ledger as it then stands and is left alone if it no longer qualifies."""
        plan = self.bulk_plan(only_safe)
        done, skipped = [], list(plan["held"])
        for rid in plan["confirm"]:
            d = self.refresh(rid)
            c = next((c for c in d["candidates"] if c["workshop_id"] == d["recommended"]), None)
            if d["subtype"] != "allocate" or (only_safe and not (c and c.get("safe"))):
                skipped.append({"request_id": rid, "reason": "no longer safe after the earlier confirmations in this batch"})
                continue
            rec = self.confirm(rid, by=by)
            done.append({"request_id": rid, "workshop_id": rec["workshop_id"], "audit_id": rec["audit_id"]})
        self._log(None, "confirm_all", by, f"{len(done)} confirmed ({', '.join(x['request_id'] for x in done) or '-'}); "
                                           f"{len(skipped)} left for an individual decision")
        return {"confirmed": done, "skipped": skipped}

    def handle(self, line: str) -> dict:
        """Propose, and auto-confirm when there is an on-time option (unattended replay)."""
        first = self.propose(line)
        for d in list(self.last_proposed):
            if d["subtype"] == "allocate":
                self.confirm(d["request_id"], by="demo-dispatcher")
        return self.decisions[first["request_id"]]


NUM_RE = re.compile(r"(?<![A-Za-z\-])\d+(?:\.\d+)?")


def number_check(text: str, tool_calls: list, batch: Optional[dict], req: dict) -> dict:
    """Every number in the explanation must appear in a tool output, the batch, or the request itself."""
    blob = json.dumps(tool_calls, ensure_ascii=False, default=str) + json.dumps(batch or {}, default=str) + (req.get("raw_text") or "")
    allowed = set(NUM_RE.findall(blob))
    for x in list(allowed):
        try:
            f = float(x)
            allowed |= {f"{f:.1f}", f"{f:.0f}", str(int(f)) if f.is_integer() else x, f"{f * 100:.0f}"}
        except ValueError:
            pass
    found = NUM_RE.findall(re.sub(r"\b(ORD-\d+|[A-Z]\d+)\b", "", re.sub(r"\d{4}-\d{2}-\d{2}", "", text)))
    dates = re.findall(r"\d{4}-\d{2}-\d{2}", text)
    bad = [n for n in found if n not in allowed] + [x for x in dates if x not in blob]
    return {"numbers": len(found) + len(dates), "untraced": bad, "ok": not bad}


def inbox_lines() -> List[str]:
    src = ROOT / "data" / "dispatch_requests.txt"
    lines = [ln for ln in src.read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.startswith("#")]
    lines.sort(key=lambda ln: re.search(r"\[(\d\d:\d\d)\]", ln).group(1))
    return lines


def load_gold():
    labels = ROOT / "eval" / "gold_labels.csv"
    facts = ROOT / "eval" / "gold_facts.csv"
    if not labels.exists():
        return None
    with open(labels, encoding="utf-8") as f:
        lab = {r["request_id"]: r for r in csv.DictReader(f)}
    fac = {}
    if facts.exists():
        with open(facts, encoding="utf-8") as f:
            fac = {r["request_id"]: r for r in csv.DictReader(f)}
    return lab, fac


def score(decisions: Dict[str, dict]) -> dict:
    """Development check against the frozen labels. Not the held-out evaluation."""
    gold = load_gold()
    if not gold:
        return {"available": False, "rows": []}
    lab, fac = gold
    rows = []
    for rid, d in decisions.items():
        if rid not in lab:
            continue
        g_beh = lab[rid].get("official_behaviour", "")
        g_sub = lab[rid].get("internal_subtype", "")
        g_ws = fac.get(rid, {}).get("recommended", "")
        ws_ok = None
        if g_ws and d["subtype"] in ("allocate", "no_on_time_option", "ineligible_suggestion"):
            ws_ok = d["recommended"] == g_ws
        rows.append({"request_id": rid, "behaviour": d["official_behaviour"], "gold_behaviour": g_beh,
                     "subtype": d["subtype"], "gold_subtype": g_sub, "recommended": d["recommended"],
                     "gold_recommended": g_ws, "behaviour_ok": d["official_behaviour"] == g_beh, "workshop_ok": ws_ok,
                     "numbers_ok": d["number_check"]["ok"]})
    n = len(rows)
    ws_rows = [r for r in rows if r["workshop_ok"] is not None]
    return {"available": True, "n": n, "behaviour": sum(1 for r in rows if r["behaviour_ok"]),
            "workshop": sum(1 for r in ws_rows if r["workshop_ok"]), "workshop_n": len(ws_rows),
            "numbers": sum(1 for r in rows if r["numbers_ok"]), "rows": rows}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--llm", action="store_true", help="use the LLM for parsing, GPT-5 mini by default (costs money)")
    ap.add_argument("--only", default=None, help="print full detail for one request id, e.g. R12")
    ap.add_argument("--objective", default="use_slack", choices=list(OBJECTIVES))
    args = ap.parse_args()

    client = LLMClient(provider="openai") if args.llm else None
    desk = Desk(parser=client.parse_request if client else None, objective=args.objective)
    for ln in inbox_lines():
        desk.handle(ln)

    run_dir = ROOT / "eval" / "runs" / datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=True)
    with open(run_dir / "decisions.jsonl", "w", encoding="utf-8") as f:
        for d in desk.decisions.values():
            f.write(json.dumps(d, ensure_ascii=False, default=str) + "\n")
    desk.ledger.save(run_dir / "audit.json")

    s = score(desk.decisions)
    by_id = {r["request_id"]: r for r in s["rows"]}
    md = [f"# Desk run {run_dir.name}", "",
          f"parser: {'llm:' + client.model if client else 'rules'} · objective: {args.objective} · today {TODAY}", ""]
    for rid, d in desk.decisions.items():
        g = by_id.get(rid, {})
        md += [f"## {rid} [{d['timestamp']}] {d['requester']}", f"> {d['raw_text']}", "",
               f"- behaviour: **{d['official_behaviour']}** / {d['subtype']}"
               + (f"  (gold: {g.get('gold_behaviour')} / {g.get('gold_subtype')})" if g else ""),
               f"- order: {d['order_id'] or '-'} · recommended: {d['recommended'] or '-'}"
               + (f" (gold: {g.get('gold_recommended') or '-'})" if g else ""),
               f"- explanation: {d['explanation']}",
               f"- numbers traced to tools: {'yes' if d['number_check']['ok'] else 'NO ' + str(d['number_check']['untraced'])}",
               f"- flags: {'; '.join(d['flags']) or '-'}",
               f"- ledger: {d['committed'] or 'no write'}", ""]
    (run_dir / "transcript.md").write_text("\n".join(md), encoding="utf-8")

    if args.only:
        d = desk.decisions[args.only]
        print(json.dumps({k: d[k] for k in ("request_id", "official_behaviour", "subtype", "status", "order_id", "recommended",
                                            "explanation", "flags", "number_check", "committed")},
                         ensure_ascii=False, indent=2, default=str))
        print("\ntool calls:")
        for t in d["tool_calls"]:
            print("  -", t["tool"], json.dumps(t.get("input"), ensure_ascii=False, default=str))
        return

    print(f"{'id':<4} {'behaviour':<18} {'subtype':<22} {'order':<8} {'rec':<4} {'gold':<18} {'gold ws':<7} {'nums':<5} ledger")
    for rid, d in desk.decisions.items():
        g = by_id.get(rid, {})
        mark = "" if not g else ("ok " if g["behaviour_ok"] else "XX ")
        wmark = "" if not g or g["workshop_ok"] is None else ("" if g["workshop_ok"] else " XX")
        print(f"{rid:<4} {mark}{d['official_behaviour']:<15} {d['subtype']:<22} {d['order_id'] or '-':<8} {d['recommended'] or '-':<4} "
              f"{g.get('gold_behaviour', ''):<18} {g.get('gold_recommended') or '-':<4}{wmark:<3} "
              f"{'ok' if d['number_check']['ok'] else 'NO':<5} {d['committed'] or ''}")
    if s["available"]:
        print(f"\nbehaviour matches the frozen labels: {s['behaviour']}/{s['n']}")
        print(f"recommended workshop matches (where both have one): {s['workshop']}/{s['workshop_n']}")
        print(f"explanations with every number traced to a tool output: {s['numbers']}/{s['n']}")
    print(f"ledger writes: {len(desk.ledger.records)}  session constraints: {desk.session_excl}")
    if client:
        print(f"LLM spent ${client.spent_usd:.4f}, fallbacks {sum(1 for c in client.calls if 'outcome' in c)}")
    print(f"\nwritten {run_dir}")


if __name__ == "__main__":
    main()
