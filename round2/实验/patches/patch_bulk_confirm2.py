"""One-off patch (round 2): the bulk confirm must not take capacity that a tight request needs.

A request that is on time but not rework-safe ("tight") is never bulk-confirmed. A safe request whose
recommended workshop is also the recommended workshop of a tight open request is held back too, so the
dispatcher decides the tight one first.
"""
import sys
from pathlib import Path

p = Path(sys.argv[1]) / "desk" / "pipeline.py"
s = p.read_text(encoding="utf-8")
a = '''        done, skipped = [], []
        for rid in sorted(self.decisions, key=lambda r: self.arrival.get(r, 10 ** 9)):
            d = self.refresh(rid)
            if not self.is_open(d) or d["subtype"] != "allocate":
                continue
            best = next(c for c in d["candidates"] if c["workshop_id"] == d["recommended"])
            if only_safe and not best.get("safe"):
                skipped.append({"request_id": rid, "reason": "on time, but not if the batch is reworked"})
                continue
'''
b = '''        done, skipped = [], []
        self.refresh_all()
        tight = {}                                   # workshop -> the tight open requests that count on it
        if only_safe:
            for rid, d in self.decisions.items():
                if self.is_open(d) and d["subtype"] == "allocate":
                    c = next(c for c in d["candidates"] if c["workshop_id"] == d["recommended"])
                    if not c.get("safe"):
                        tight.setdefault(d["recommended"], []).append(rid)
        for rid in sorted(self.decisions, key=lambda r: self.arrival.get(r, 10 ** 9)):
            d = self.refresh(rid)
            if not self.is_open(d) or d["subtype"] != "allocate":
                continue
            best = next(c for c in d["candidates"] if c["workshop_id"] == d["recommended"])
            if only_safe and not best.get("safe"):
                skipped.append({"request_id": rid, "reason": "tight: on time, but not if the batch is reworked"})
                continue
            if only_safe and tight.get(d["recommended"]):
                skipped.append({"request_id": rid, "reason": f"would use {self.name(d['recommended'])}, which tight request "
                                                             f"{', '.join(tight[d['recommended']])} also needs; decide that first"})
                continue
'''
assert s.count(a) == 1
p.write_text(s.replace(a, b), encoding="utf-8", newline="")
print("bulk confirm v2 patched")
