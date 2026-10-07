"""One-off patch (round 2): bulk_plan() says, without writing anything, which open requests a bulk
confirm would take and which it would hold back and why. confirm_all() uses the same split, so the
number on the button is the number the dispatcher gets (unless the ledger moves in between)."""
import sys
from pathlib import Path

p = Path(sys.argv[1]) / "desk" / "pipeline.py"
s = p.read_text(encoding="utf-8")
a = s[s.index("    def confirm_all(self"):s.index("    def handle(self, line: str) -> dict:")]
b = '''    def bulk_plan(self, only_safe: bool = True) -> dict:
        """Which open on-time recommendations a bulk confirm would take, on the ledger as it stands.
        Writes nothing. Held back: tight requests (a rework would make them late), and safe requests
        whose workshop a tight request also counts on."""
        self.refresh_all()
        open_alloc = [(rid, d) for rid, d in self.decisions.items() if self.is_open(d) and d["subtype"] == "allocate"]
        open_alloc.sort(key=lambda x: self.arrival.get(x[0], 10 ** 9))
        best = {rid: next(c for c in d["candidates"] if c["workshop_id"] == d["recommended"]) for rid, d in open_alloc}
        tight = {}
        if only_safe:
            for rid, d in open_alloc:
                if not best[rid].get("safe"):
                    tight.setdefault(d["recommended"], []).append(rid)
        go, held = [], []
        for rid, d in open_alloc:
            if only_safe and not best[rid].get("safe"):
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

'''
p.write_text(s.replace(a, b), encoding="utf-8", newline="")
print("bulk plan patched")
