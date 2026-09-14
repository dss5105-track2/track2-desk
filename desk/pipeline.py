"""End-to-end pipeline v0: process the morning inbox exactly as eval/protocol.md describes.

    python desk/pipeline.py                  # rule parser, no network, no cost
    python desk/pipeline.py --llm            # GPT-5 nano extraction (costs money; needs .env)
    python desk/pipeline.py --only R12       # one request, full detail

For every chat line, in timestamp order:
  1. parse           -> structured request (llm/llm_client.py; rules by default)
  2. resolve order   -> explicit id, or candidates from customer/product
  3. route           -> decline / clarify / refuse / extract   (deterministic, labeling_guide order)
  4. kernel          -> eligibility table, estimates, ranking  (kernel/, zero LLM)
  5. explain         -> text built only from tool outputs; every number is checked against them
  6. confirm+commit  -> allocate requests are auto-confirmed by "demo-dispatcher" and written to the ledger
Outputs go to eval/runs/<timestamp>/ (git-ignored): decisions.jsonl, audit.json, transcript.md.
If eval/draft/ gold files exist, the run is scored against them. That comparison is a development
check on the official 30, not the held-out evaluation.
"""
from __future__ import annotations

import argparse
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
from kernel.orders import load_orders, find_orders, state_checks, TODAY  # noqa: E402
from kernel.allocator import Allocator  # noqa: E402
from kernel.estimator import split_estimate  # noqa: E402
from kernel.ledger import Ledger  # noqa: E402
from llm.llm_client import RuleBasedParser, LLMClient  # noqa: E402

OFFICIAL = {"allocate": "extract", "no_on_time_option": "extract", "ambiguous_reference": "clarify",
            "missing_fields": "clarify", "state_conflict": "clarify", "ineligible_suggestion": "refuse",
            "not_in_data": "decline-to-answer"}
NEW_ORDER_RE = re.compile(r"details to follow|new rush|coming in from", re.I)


class Desk:
    def __init__(self, parser, objective: str = "lateness"):
        self.W = load_workshops()
        self.O = load_orders()
        self.ledger = Ledger(self.W, TODAY)
        self.alloc = Allocator(objective)
        self.parser = parser
        self.session_excl: Dict[str, dict] = {}     # workshop_id -> {"by", "source"}
        self.history: List[dict] = []               # parsed requests, for cross-message memory
        self.decisions: Dict[str, dict] = {}

    # ---------------------------------------------------------------- helpers
    def name(self, wid: str) -> str:
        return self.W[wid].name

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

    # ---------------------------------------------------------------- routing
    def route(self, req: dict) -> dict:
        d = {"request_id": req["request_id"], "timestamp": req["timestamp"], "requester": req["requester"],
             "raw_text": req["raw_text"], "parsed": req, "tool_calls": [], "subtype": None, "order_id": req["order_id"],
             "recommended": None, "candidates": [], "explanation": "", "committed": None, "flags": []}

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
        if req["question_type"] == "status":
            d["subtype"] = "not_in_data"
            d["explanation"] = "Progress tracking is outside this desk; it only allocates batches to workshops."
            return d

        # 2. which order?
        if order is None:
            prior = next((h for h in self.history if h["request_id"] == req.get("references_prior")), None)
            prior_dec = self.decisions.get(prior["request_id"]) if prior else None
            if NEW_ORDER_RE.search(req["raw_text"]) or (prior_dec and prior_dec["subtype"] == "missing_fields"):
                d["subtype"] = "missing_fields"
                ref = f" (follow-up to {prior['request_id']})" if prior else ""
                d["explanation"] = (f"I can't book capacity yet{ref}: I need the order number, product, piece count and due date. "
                                    "Capacity depends on all four, so I won't guess.")
                return d
            cands = find_orders(self.O, customer=req["customer"], product=req["product"]) if (req["customer"] or req["product"]) else []
            d["tool_calls"].append({"tool": "resolve_order_reference", "input": {"customer": req["customer"], "product": req["product"]},
                                    "output": {"count": len(cands),
                                               "orders": [{"order_id": o.order_id, "customer": o.customer, "product": o.product,
                                                           "pieces": o.pieces, "due_date": o.due_date.isoformat(), "stage": o.current_stage}
                                                          for o in cands]}})
            if len(cands) == 1:
                order = cands[0]
                d["order_id"] = order.order_id
                d["flags"].append(f"resolved uniquely to {order.order_id}")
            else:
                d["subtype"] = "ambiguous_reference"
                if cands:
                    listing = "; ".join(f"{o.order_id} {o.customer} {o.product} {o.pieces} pcs due {o.due_date}" for o in cands)
                    d["explanation"] = f"Which order do you mean? {len(cands)} in-progress orders match: {listing}."
                else:
                    d["explanation"] = "Which order do you mean? The message doesn't name an order, customer or product I can match."
                return d

        # 3. state conflicts
        flags = state_checks(order, TODAY, self.ledger)
        d["tool_calls"].append({"tool": "state_checks", "input": order.order_id, "output": flags})
        d["flags"] += flags + self._mismatch_notes(order, req)
        conflict = [f for f in flags if "PACKING" in f or "COMPLETE" in f or "already dispatched" in f]
        if conflict:
            d["subtype"] = "state_conflict"
            d["explanation"] = f"Before I place {order.order_id}: {conflict[0]}. Do you still want it sent outside?"
            return d

        # 4. missing information the order book can't fill
        if "due_date" in req["missing_fields"]:
            d["subtype"] = "missing_fields"
            d["explanation"] = (f"{order.order_id}: the new due date isn't confirmed yet, and the estimate depends on it. "
                                "I'll hold off until the date is confirmed.")
            return d

        batch = self._batch(order, req)
        excl = set(req["excluded_workshops"]) | set(self.session_excl)
        pref = req["preference"] if req["preference"] in ("fastest", "cheapest_on_time", "lowest_defect") else None
        rows = self.alloc.rank(batch, self.W, self.ledger.queues(), exclude=excl, preference=pref)
        ests = [r["estimate"] for r in rows]
        table = eligibility_table(self.W, batch["category"], batch["pieces"], exclude=excl)
        d["tool_calls"].append({"tool": "eligibility_table", "input": {"category": batch["category"], "pieces": batch["pieces"],
                                "exclude": sorted(excl)}, "output": table})
        d["tool_calls"].append({"tool": "rank_candidates", "input": {"objective": self.alloc.objective, "preference": pref},
                                "output": [e.as_dict() for e in ests]})
        d["candidates"] = [e.as_dict() for e in ests]
        d["batch"] = {k: (v.isoformat() if isinstance(v, date) else v) for k, v in batch.items()}
        excl_text = ""
        if excl:
            parts = []
            for wid in sorted(excl):
                src = self.session_excl.get(wid)
                parts.append(f"{self.name(wid)} (excluded by {src['by']} in {src['source']})" if src and wid not in req["excluded_workshops"]
                             else f"{self.name(wid)} (excluded in this request)")
            excl_text = " Not considered: " + ", ".join(parts) + "."

        # 5. ineligible suggestion
        fw = req["forced_workshop"]
        if fw:
            ok, why = check_eligibility(self.W[fw], batch["category"], batch["pieces"])
            if ok and fw in self.session_excl:
                ok, why = False, f"{self.session_excl[fw]['by']} said nothing new goes to it ({self.session_excl[fw]['source']})"
            if not ok:
                d["subtype"] = "ineligible_suggestion"
                d["recommended"] = ests[0].workshop_id if ests else None
                alt = self._alt_text(ests)
                others = [w for w in sorted(excl) if w != fw]
                other_text = excl_text if others else ""
                d["explanation"] = f"{self.name(fw)} can't take {order.order_id}: {why}. {alt}{other_text}"
                return d

        # 6. extract: on time or not
        if not ests:
            d["subtype"] = "no_on_time_option"
            d["explanation"] = f"No eligible workshop can make {order.order_id} ({batch['category']}, {batch['pieces']} pcs).{excl_text} Escalating to a human."
            return d
        best = ests[0]
        d["recommended"] = best.workshop_id
        if any(e.on_time for e in ests) and best.on_time:
            d["subtype"] = "allocate"
            runner = next((e for e in ests[1:]), None)
            why_pref = {"fastest": "fastest turnaround", "cheapest_on_time": "cheapest workshop that still makes the date",
                        "lowest_defect": "lowest defect rate among on-time options"}.get(pref, "earliest on-time finish")
            d["explanation"] = (f"Recommend {best.name} for {order.order_id} ({batch['pieces']} pcs): {why_pref}. "
                                f"Estimate {best.finish_days:.1f} days = queue {best.queue_days:.1f} + work {best.work_days:.1f} "
                                f"+ expected rework {best.rework_days:.1f} + transport {best.lead_days:.0f}; back {best.promised_date}, "
                                f"due {batch['due_date']}. Cost {best.cost:.0f}, defect rate {best.defect_rate:.0%}."
                                + (f" Next best: {runner.name}, {runner.finish_days:.1f} days, back {runner.promised_date}." if runner else "")
                                + excl_text)
        else:
            d["subtype"] = "no_on_time_option"
            late_word = "already past due" if batch["due_date"] < TODAY else f"due {batch['due_date']}"
            opts = f"Earliest is {best.name}: back {best.promised_date}, {days(best.late_days)} late ({best.finish_days:.1f} days)."
            d["explanation"] = (f"No workshop can return {order.order_id} on time ({late_word}). {opts} "
                                "Options: accept the delay, renegotiate the date with the customer, relax a constraint, or escalate."
                                + excl_text)
            if req["preference"] == "split":
                s = split_estimate(self.W, batch["category"], batch["pieces"], self.ledger.queues(), TODAY, batch["due_date"], exclude=excl)
                d["tool_calls"].append({"tool": "split_estimate", "output": s})
                if s.get("possible"):
                    d["explanation"] += (f" Splitting across two shops gains {s['gain_days']:.1f} days"
                                         + (", so it doesn't help." if s["gain_days"] < 0.5 else "."))
            if fw is None and any(w in self.session_excl for w in self.W):
                lifted = [r["estimate"] for r in self.alloc.rank(batch, self.W, self.ledger.queues(),
                                                                   exclude=set(req["excluded_workshops"]), preference=pref)]
                d["tool_calls"].append({"tool": "rank_candidates", "input": {"exclude": sorted(req["excluded_workshops"]), "note": "session ban lifted"},
                                        "output": [e.as_dict() for e in lifted]})
                if lifted and lifted[0].workshop_id in self.session_excl:
                    l0 = lifted[0]
                    d["explanation"] += (f" If the ban on {l0.name} were lifted: back {l0.promised_date}"
                                         + (", on time." if l0.on_time else f", {days(l0.late_days)} late."))
        return d

    def _alt_text(self, ests) -> str:
        if not ests:
            return "No other eligible workshop can take it."
        on = [e for e in ests if e.on_time]
        e = on[0] if on else ests[0]
        return (f"Alternative: {e.name}, back {e.promised_date}" + (" (on time)." if e.on_time else f" ({days(e.late_days)} late; nothing makes the date)."))

    # ---------------------------------------------------------------- one request
    def handle(self, line: str) -> dict:
        req = self.parser(line, list(self.history))
        d = self.route(req)
        d["official_behaviour"] = OFFICIAL[d["subtype"]]
        d["number_check"] = number_check(d["explanation"], d["tool_calls"], d.get("batch"), req)
        if d["subtype"] == "allocate":
            order = self.O[d["order_id"]]
            batch = self._batch(order, req)
            rec = self.ledger.commit(request_id=req["request_id"], order_id=order.order_id, workshop_id=d["recommended"],
                                     category=order.category, pieces=batch["pieces"], sent_date=TODAY, due_date=batch["due_date"],
                                     requester=req["requester"], confirmed_by="demo-dispatcher", reason=d["explanation"],
                                     constraints={"excluded": sorted(set(req["excluded_workshops"]) | set(self.session_excl)),
                                                  "session": {k: v for k, v in self.session_excl.items()}},
                                     candidates=d["candidates"], objective={"name": self.alloc.objective, "preference": req["preference"]},
                                     model_version=req["parser"])
            d["committed"] = rec["audit_id"]
        if req["constraint_scope"] == "session":
            for wid in req["excluded_workshops"]:
                by = "Boss" if re.search(r"\bboss\b", req["raw_text"], re.I) else req["requester"]
                self.session_excl[wid] = {"by": by, "source": req["request_id"]}
                d["flags"].append(f"session constraint recorded: exclude {wid} (by {by})")
        self.history.append(req)
        self.decisions[req["request_id"]] = d
        return d


def days(n: int) -> str:
    return f"{n} day" if n == 1 else f"{n} days"


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
    found = NUM_RE.findall(re.sub(r"\b(ORD|R|W|A)-?\d+\b", "", re.sub(r"\d{4}-\d{2}-\d{2}", "", text)))
    dates = re.findall(r"\d{4}-\d{2}-\d{2}", text)
    bad = [n for n in found if n not in allowed] + [x for x in dates if x not in blob]
    return {"numbers": len(found) + len(dates), "untraced": bad, "ok": not bad}


def load_gold():
    draft = ROOT / "eval" / "draft"
    labels = draft / "gold_labels_draft.csv"
    facts = draft / "gold_facts.csv"
    if not labels.exists():
        return None
    with open(labels, encoding="utf-8") as f:
        lab = {r["request_id"]: r for r in csv.DictReader(f)}
    fac = {}
    if facts.exists():
        with open(facts, encoding="utf-8") as f:
            fac = {r["request_id"]: r for r in csv.DictReader(f)}
    return lab, fac


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--llm", action="store_true", help="use GPT-5 nano for parsing (costs money)")
    ap.add_argument("--only", default=None, help="print full detail for one request id, e.g. R12")
    args = ap.parse_args()

    if args.llm:
        client = LLMClient(provider="openai")
        parser = client.parse_request
    else:
        client = None
        parser = RuleBasedParser().parse
    desk = Desk(parser)

    src = ROOT / "data" / "dispatch_requests.txt"
    lines = [ln for ln in src.read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.startswith("#")]
    lines.sort(key=lambda ln: re.search(r"\[(\d\d:\d\d)\]", ln).group(1))
    for ln in lines:
        desk.handle(ln)

    run_dir = ROOT / "eval" / "runs" / datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=True)
    with open(run_dir / "decisions.jsonl", "w", encoding="utf-8") as f:
        for d in desk.decisions.values():
            f.write(json.dumps({k: v for k, v in d.items() if k != "parsed"} | {"parsed": d["parsed"]}, ensure_ascii=False, default=str) + "\n")
    desk.ledger.save(run_dir / "audit.json")

    gold = load_gold()
    md = [f"# Desk run {run_dir.name}", "", f"parser: {'llm:' + client.model if client else 'rules'} · objective: lateness · today {TODAY}", ""]
    rows = []
    for rid, d in desk.decisions.items():
        g_beh = g_sub = g_ws = ""
        if gold:
            lab, fac = gold
            g_beh = lab.get(rid, {}).get("official_behaviour", "")
            g_sub = lab.get(rid, {}).get("internal_subtype", "")
            g_ws = fac.get(rid, {}).get("recommended", "")
        beh_ok = (d["official_behaviour"] == g_beh) if gold else None
        ws_ok = None
        if gold and g_ws and d["subtype"] in ("allocate", "no_on_time_option", "ineligible_suggestion"):
            ws_ok = d["recommended"] == g_ws
        rows.append((rid, d, g_beh, g_sub, g_ws, beh_ok, ws_ok))
        md += [f"## {rid} [{d['timestamp']}] {d['requester']}", f"> {d['raw_text']}", "",
               f"- behaviour: **{d['official_behaviour']}** / {d['subtype']}" + (f"  (gold: {g_beh} / {g_sub})" if gold else ""),
               f"- order: {d['order_id'] or '-'} · recommended: {d['recommended'] or '-'}" + (f" (gold: {g_ws or '-'})" if gold else ""),
               f"- explanation: {d['explanation']}",
               f"- numbers traced to tools: {'yes' if d['number_check']['ok'] else 'NO ' + str(d['number_check']['untraced'])}",
               f"- flags: {'; '.join(d['flags']) or '-'}",
               f"- ledger: {d['committed'] or 'no write'}", ""]
    (run_dir / "transcript.md").write_text("\n".join(md), encoding="utf-8")

    if args.only:
        d = desk.decisions[args.only]
        print(json.dumps({k: d[k] for k in ("request_id", "official_behaviour", "subtype", "order_id", "recommended", "explanation",
                                            "flags", "number_check", "committed")}, ensure_ascii=False, indent=2, default=str))
        print("\ntool calls:")
        for t in d["tool_calls"]:
            print("  -", t["tool"], json.dumps(t.get("input"), ensure_ascii=False, default=str))
        return

    print(f"{'id':<4} {'behaviour':<18} {'subtype':<22} {'order':<8} {'rec':<4} {'gold':<18} {'gold ws':<7} {'nums':<5} ledger")
    for rid, d, g_beh, g_sub, g_ws, beh_ok, ws_ok in rows:
        mark = "" if beh_ok is None else ("ok " if beh_ok else "XX ")
        wmark = "" if ws_ok is None else ("" if ws_ok else " XX")
        print(f"{rid:<4} {mark}{d['official_behaviour']:<15} {d['subtype']:<22} {d['order_id'] or '-':<8} {d['recommended'] or '-':<4} "
              f"{g_beh:<18} {g_ws or '-':<4}{wmark:<3} {'ok' if d['number_check']['ok'] else 'NO':<5} {d['committed'] or ''}")
    if gold:
        n = len(rows)
        beh = sum(1 for r in rows if r[5])
        ws_rows = [r for r in rows if r[6] is not None]
        ws = sum(1 for r in ws_rows if r[6])
        nums = sum(1 for r in rows if r[1]["number_check"]["ok"])
        print(f"\nbehaviour matches draft gold: {beh}/{n}")
        print(f"recommended workshop matches (where both have one): {ws}/{len(ws_rows)}")
        print(f"explanations with every number traced to a tool output: {nums}/{n}")
    print(f"ledger writes: {len(desk.ledger.records)}  session constraints: {desk.session_excl}")
    if client:
        print(f"LLM spent ${client.spent_usd:.4f}, fallbacks {sum(1 for c in client.calls if 'outcome' in c)}")
    print(f"\nwritten {run_dir}")


if __name__ == "__main__":
    main()
