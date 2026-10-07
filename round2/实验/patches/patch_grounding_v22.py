"""Round-2 patch: grounding 2.2. One more claim of the model is checked against the text.

Found with grounding 2.1 (改进后_核对2.1/): on a message that names an order and a workshop and says nothing
about dates, the model sometimes lists the due date as missing. The desk then answers "the new due date isn't
confirmed yet" instead of refusing the workshop. Seen on the official inbox with GPT-5 nano (R11 run 2, R14 run 3)
and, same pattern, on the challenge inbox with GPT-5 mini (C17, C28).

  R11  "OldMill is free right now — give them ORD-008."         -> model: missing due_date   (wrong)
  R05  "... customer moved up, will confirm new date ..."       -> model: missing due_date   (right)

Rule: when the message names an order, the order book holds the due date. The model may call the date missing
only if the message says something about timing at all. The word list is general vocabulary, not a list of the
phrasings in either inbox.
"""
import sys
from pathlib import Path

p = Path(sys.argv[1]) / "llm" / "llm_client.py"
s = p.read_text(encoding="utf-8")


def rep(a, b):
    global s
    assert s.count(a) == 1, (s.count(a), a[:70])
    s = s.replace(a, b)


rep('GROUNDING_VERSION = "2.1"',
    'GROUNDING_VERSION = "2.2"\n'
    'TIMING_TALK_RE = re.compile(r"\\b(date|due|deadline|when|sooner|earlier|later|moved|postpon\\w*|delay\\w*|confirm\\w*|tbc)\\b", re.I)')

rep('''    elif r.get("order_id"):
        missing = [m for m in missing if m == "due_date" and r.get("due_date") is None]
''', '''    elif r.get("order_id"):                  # the order book has the date unless the message says the date itself is in question
        missing = [m for m in missing if m == "due_date" and r.get("due_date") is None and TIMING_TALK_RE.search(text)]
''')

p.write_text(s, encoding="utf-8", newline="")

t = Path(sys.argv[1]) / "tests" / "test_round2.py"
u = t.read_text(encoding="utf-8")
a = '''def test_grounding_leaves_a_real_status_question_alone():'''
assert u.count(a) == 1
u = u.replace(a, '''def test_grounding_keeps_a_missing_date_only_when_the_message_talks_about_timing():
    named = _ground("OldMill is free right now — give them ORD-008.", order_id="ORD-008", forced_workshop="W7", missing_fields=["due_date"])
    assert named["missing_fields"] == [] and named["forced_workshop"] == "W7"
    asked = _ground("ORD-008: the customer wants it earlier but has not said when.", order_id="ORD-008", missing_fields=["due_date"])
    assert asked["missing_fields"] == ["due_date"]


''' + a)
t.write_text(u, encoding="utf-8", newline="")
print("grounding 2.2 patched")
