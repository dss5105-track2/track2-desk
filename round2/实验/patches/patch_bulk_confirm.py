"""One-off patch (round 2): a bulk confirm for the dispatcher, and the short reason kept on the decision.

confirm_all() is still a human action: one click confirms every open request whose recommendation is on
time (by default only those on time even if reworked), in arrival order, re-estimating each against the
ledger as it then stands. Anything that stops qualifying on the way is left for an individual decision.
"""
import sys
from pathlib import Path

p = Path(sys.argv[1]) / "desk" / "pipeline.py"
s = p.read_text(encoding="utf-8")


def rep(a, b):
    global s
    assert s.count(a) == 1, (s.count(a), a[:70])
    s = s.replace(a, b)


rep('''            fastest = min((e for e in ests if e.on_time), key=lambda e: e.finish_days)
''', '''            fastest = min((e for e in ests if e.on_time), key=lambda e: e.finish_days)
            d["why"] = self._why(rows[0], pref, best, fastest)
''')

rep('''    def handle(self, line: str) -> dict:''', '''    def confirm_all(self, by: str = "dispatcher", only_safe: bool = True) -> dict:
        """Confirm every open on-time recommendation, in arrival order, each re-estimated against the ledger
        as it then stands. With only_safe, a recommendation that a rework would make late is left alone."""
        done, skipped = [], []
        for rid in sorted(self.decisions, key=lambda r: self.arrival.get(r, 10 ** 9)):
            d = self.refresh(rid)
            if not self.is_open(d) or d["subtype"] != "allocate":
                continue
            best = next(c for c in d["candidates"] if c["workshop_id"] == d["recommended"])
            if only_safe and not best.get("safe"):
                skipped.append({"request_id": rid, "reason": "on time, but not if the batch is reworked"})
                continue
            rec = self.confirm(rid, by=by)
            done.append({"request_id": rid, "workshop_id": rec["workshop_id"], "audit_id": rec["audit_id"]})
        self._log(None, "confirm_all", by, f"{len(done)} confirmed ({', '.join(x['request_id'] for x in done) or '-'}); "
                                           f"{len(skipped)} left for an individual decision")
        return {"confirmed": done, "skipped": skipped}

    def handle(self, line: str) -> dict:''')

p.write_text(s, encoding="utf-8", newline="")
print("bulk confirm patched")
