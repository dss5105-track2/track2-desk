"""One-off patch (round 2): request ids are no longer assumed to start with R or H, so another inbox
(C01.. for the challenge set, later the held-out set) can be processed. The number check strips any
id of the form LETTER+digits or ORD-digits before it looks for numbers."""
import sys
from pathlib import Path

p = Path(sys.argv[1]) / "desk" / "pipeline.py"
s = p.read_text(encoding="utf-8")
a = r'''re.sub(r"\b(ORD|R|W|A|H)-?\d+\b", "", '''
b = r'''re.sub(r"\b(ORD-\d+|[A-Z]\d+)\b", "", '''
assert s.count(a) == 1, s.count(a)
p.write_text(s.replace(a, b), encoding="utf-8", newline="")
print("ids patched")
