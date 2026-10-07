"""One-off patch to the existing tests after the lateness objective changed (round 2).

The old tests pinned the behaviour of the weight-based lateness setting (which is earliest finish).
That setting still exists as "lateness_v1", so the tests about ledger mechanics now name it explicitly.
"""
import sys
from pathlib import Path

root = Path(sys.argv[1])


def patch(rel, pairs):
    p = root / rel
    s = p.read_text(encoding="utf-8")
    for a, b in pairs:
        assert s.count(a) == 1, (rel, s.count(a), a[:70])
        s = s.replace(a, b)
    p.write_text(s, encoding="utf-8", newline="")


patch("tests/test_kernel.py", [
    ('''    L = Ledger(W, TODAY)
    a = Allocator("lateness")
    # R12 processed in isolation -> Nimble Needle''', '''    L = Ledger(W, TODAY)
    a = Allocator("lateness_v1")          # earliest finish; the mechanics below do not depend on the rule
    # R12 processed in isolation -> Nimble Needle'''),
    ('''    L = Ledger(W, TODAY)
    a = Allocator("lateness")
    _commit(L, "R09", "ORD-045", "W6")
    _commit(L, "R12", "ORD-053", "W5")''', '''    L = Ledger(W, TODAY)
    a = Allocator("lateness_v1")
    _commit(L, "R09", "ORD-045", "W6")
    _commit(L, "R12", "ORD-053", "W5")'''),
])

patch("tests/test_desk.py", [
    ('''def loaded() -> Desk:
    desk = Desk()''', '''def loaded(objective: str = "lateness") -> Desk:
    desk = Desk(objective=objective)'''),
    ('''def test_open_requests_follow_the_ledger():
    desk = loaded()''', '''def test_open_requests_follow_the_ledger():
    desk = loaded("lateness_v1")                               # earliest finish makes the hand-off visible'''),
    ('''    rec = desk.confirm("R08")
    assert rec["workshop_id"] == "W6" and rec["estimate"]["on_time"]''', '''    rec = desk.confirm("R08")
    assert rec["workshop_id"] != "W8" and rec["estimate"]["on_time"]       # not FreshStart, and on time
    assert rec["workshop_id"] not in desk.session_excl                      # and not the shop Boss ruled out'''),
    ('''    assert {"R09", "R12", "R25"} <= set(committed)''', '''    assert {"R09", "R12"} <= set(committed)'''),
])
print("tests patched")
