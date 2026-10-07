"""One-off patch applied to track2-desk-优化版/desk/pipeline.py in round 2 (kept for the record).

  1. explanation says why this shop, the date if the batch is reworked, and the fastest alternative
  2. a 'split if faster' request with an on-time single shop gets an explicit answer
  3. a standing constraint remembers when it was set; a request that arrived earlier says so
  4. the decision as first received is kept next to the refreshed one
"""
import sys
from pathlib import Path

p = Path(sys.argv[1])
s = p.read_text(encoding="utf-8")


def rep(a, b):
    global s
    assert s.count(a) == 1, (s.count(a), a[:70])
    s = s.replace(a, b)


rep("from kernel.allocator import Allocator, OBJECTIVES  # noqa: E402",
    "from kernel.allocator import Allocator, OBJECTIVES, flexibility  # noqa: E402")

rep('''        self.actions: List[dict] = []               # every human action, ledger or not
        self.seq = 0''', '''        self.actions: List[dict] = []               # every human action, ledger or not
        self.arrival: Dict[str, int] = {}           # request_id -> position in the inbox
        self.seq = 0''')

rep('''    def exclusions_for(self, req: dict) -> set:
        return set(req["excluded_workshops"]) | set(self.session_excl)
''', '''    def exclusions_for(self, req: dict) -> set:
        return set(req["excluded_workshops"]) | set(self.session_excl)

    def _set_later(self, wid: str, req: dict) -> bool:
        """True when the standing constraint on wid was set by a message that arrived after req."""
        src = self.session_excl.get(wid)
        mine = self.arrival.get(req.get("request_id"))
        return bool(src and mine is not None and src.get("seq", -1) > mine)

    def _excl_label(self, wid: str, req: dict) -> str:
        src = self.session_excl.get(wid)
        if src and wid not in req["excluded_workshops"]:
            when = (f", set at {src['time']}, after this request arrived; it applies while the request is open"
                    if self._set_later(wid, req) else "")
            return f"{self.name(wid)} (excluded by {src['by']} in {src['source']}{when})"
        return f"{self.name(wid)} (excluded in this request)"
''')

rep('''            if src and row["reason"] == "excluded by request" and row["workshop_id"] not in req["excluded_workshops"]:
                row["reason"] = f"excluded by {src['by']} in {src['source']} (this week)"''',
    '''            if src and row["reason"] == "excluded by request" and row["workshop_id"] not in req["excluded_workshops"]:
                row["reason"] = f"excluded by {src['by']} in {src['source']} (this week)"
                if self._set_later(row["workshop_id"], req):
                    row["reason"] += "; set after this request arrived"''')

rep('''        if excl:
            parts = []
            for wid in sorted(excl):
                src = self.session_excl.get(wid)
                parts.append(f"{self.name(wid)} (excluded by {src['by']} in {src['source']})" if src and wid not in req["excluded_workshops"]
                             else f"{self.name(wid)} (excluded in this request)")
            excl_text = " Not considered: " + ", ".join(parts) + "."''',
    '''        if excl:
            excl_text = " Not considered: " + ", ".join(self._excl_label(wid, req) for wid in sorted(excl)) + "."
            for wid in sorted(excl):
                if self._set_later(wid, req):
                    d["flags"].append(f"standing constraint on {self.name(wid)} was set later, in {self.session_excl[wid]['source']}; "
                                      "it applies because this request is still open")''')

rep('''            runner = next((e for e in ests[1:]), None)
            why_pref = {"fastest": "fastest turnaround", "cheapest_on_time": "cheapest workshop that still makes the date",
                        "lowest_defect": "lowest defect rate among on-time options"}.get(pref, "earliest on-time finish")
            d["explanation"] = (f"Recommend {best.name} for {order.order_id} ({batch['pieces']} pcs): {why_pref}. "
                                f"Estimate {best.finish_days:.1f} days = queue {best.queue_days:.1f} + work {best.work_days:.1f} "
                                f"+ expected rework {best.rework_days:.1f} + transport {best.lead_days:.0f}; back {best.promised_date}, "
                                f"due {batch['due_date']}. Cost {best.cost:.0f}, defect rate {best.defect_rate:.0%}."
                                + (f" Next best: {runner.name}, {runner.finish_days:.1f} days, back {runner.promised_date}." if runner else "")
                                + excl_text)''',
    '''            runner = next((e for e in ests[1:]), None)
            fastest = min((e for e in ests if e.on_time), key=lambda e: e.finish_days)
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
                                         "the shared simulator cannot split, so that is a chat-layer estimate.")''')

rep('''    def _alt_text(self, ests) -> str:''', '''    def _why(self, row: dict, pref: Optional[str], best, fastest) -> str:
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

    def _alt_text(self, ests) -> str:''')

rep('''        d = self._finish(self.route(req), req)
        if req["constraint_scope"] == "session":
            for wid in req["excluded_workshops"]:
                by = "Boss" if re.search(r"\\bboss\\b", req["raw_text"], re.I) else req["requester"]
                self.session_excl[wid] = {"by": by, "source": req["request_id"]}
                d["flags"].append(f"session constraint recorded: exclude {self.name(wid)} (by {by})")
        d["received_at"] = datetime.now().isoformat(timespec="seconds")''',
    '''        self.arrival[req["request_id"]] = len(self.arrival)
        d = self._finish(self.route(req), req)
        if req["constraint_scope"] == "session":
            for wid in req["excluded_workshops"]:
                by = "Boss" if re.search(r"\\bboss\\b", req["raw_text"], re.I) else req["requester"]
                self.session_excl[wid] = {"by": by, "source": req["request_id"], "time": req.get("timestamp") or "",
                                          "seq": self.arrival[req["request_id"]]}
                d["flags"].append(f"session constraint recorded: exclude {self.name(wid)} (by {by})")
        d["received_at"] = datetime.now().isoformat(timespec="seconds")
        d["as_received"] = {"subtype": d["subtype"], "recommended": d["recommended"]}''')

rep('''        new["received_at"] = d.get("received_at")''', '''        new["received_at"] = d.get("received_at")
        new["as_received"] = d.get("as_received")''')

p.write_text(s, encoding="utf-8", newline="")
print("pipeline patched")
