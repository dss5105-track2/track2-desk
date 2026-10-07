"""Round-2 patch: grounding 2.1. Three fixed phrasings are decided by code instead of left to the model.

Found on the official 30 after prompt v2 + grounding (改进后/official30_nano_v2_console.txt):
  * GPT-5 nano marked Boss's "nothing new to QuickStitch this week" as valid for that request only, in
    3 runs out of 3, so R17 and R22 were then sent to QuickStitch. A standing constraint silently lost.
  * it left the preference at "none" for "asap", "quickest", "cheapest ...", "split ..."
  * it returned no due date for "needs to ship Apr 15, so it has to go out today"

Each of these is a closed phrasing the round-1 rule parser already recognised, so the code now settles it:
  scope       an exclusion plus "this week / until further notice / for now / anymore" lasts for the session
  preference  when the model says none and the text has one of the round-1 keywords, the keyword wins
  due date    when the model gives none, nothing says the date is pending, and the text has exactly one
              "Mon DD" date, that date is the due date
Only the round-1 patterns are used here; nothing learned from the challenge inbox goes into this check.
"""
import sys
from pathlib import Path

p = Path(sys.argv[1]) / "llm" / "llm_client.py"
s = p.read_text(encoding="utf-8")


def rep(a, b):
    global s
    assert s.count(a) == 1, (s.count(a), a[:70])
    s = s.replace(a, b)


rep(r'''DATE_PENDING_RE = re.compile(r"will confirm|moved up|new date|to be confirmed|\btbc\b", re.I)''',
    r'''DATE_PENDING_RE = re.compile(r"will confirm|moved up|new date|to be confirmed|\btbc\b", re.I)
GROUNDING_VERSION = "2.1"
SESSION_SCOPE_RE = re.compile(r"this week|until further notice|for now|anymore", re.I)
PREFERENCE_KEYWORDS = [("fastest", r"fastest|quickest|asap|as soon as"), ("cheapest_on_time", r"cheapest|margin is thin"),
                       ("lowest_defect", r"lowest defect|defect rate|rejected a batch|quality"), ("split", r"\bsplit\b")]
PLAIN_DATE_RE = re.compile(r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{1,2})\b", re.I)''')

rep('''    if not r["excluded_workshops"]:
        setv("constraint_scope", "request", "no exclusion")
''', '''    if not r["excluded_workshops"]:
        setv("constraint_scope", "request", "no exclusion")
    elif SESSION_SCOPE_RE.search(text):
        setv("constraint_scope", "session", "the message says the exclusion lasts beyond this order")

    if (r.get("preference") or "none") == "none" and r.get("question_type") == "allocation":
        for pref, pat in PREFERENCE_KEYWORDS:
            if re.search(pat, low):
                setv("preference", pref, "stated in the text")
                break
''')

rep('''        if not ok:
            setv("due_date", None, "no such date in the text")
''', '''        if not ok:
            setv("due_date", None, "no such date in the text")
    if not r.get("due_date") and r.get("question_type") == "allocation" and not DATE_PENDING_RE.search(text):
        plain = {(m.group(1).lower()[:3], int(m.group(2))) for m in PLAIN_DATE_RE.finditer(text)}
        if len(plain) == 1:
            mon, day = next(iter(plain))
            try:
                setv("due_date", date(int(TODAY[:4]), MONTHS[mon], day).isoformat(), "the only date in the text")
            except ValueError:
                pass
''')

# the question type is settled first, because the checks above only apply to allocation messages
rep('''    if r.get("question_type") == "status" and DISPATCH_INTENT_RE.search(text):
        setv("question_type", "allocation", "the message asks for a dispatch")

''', "")
rep('''    setv("order_id", ids[0] if ids else None, "order ids are read from the text")
''', '''    setv("order_id", ids[0] if ids else None, "order ids are read from the text")
    if r.get("question_type") == "status" and DISPATCH_INTENT_RE.search(text):
        setv("question_type", "allocation", "the message asks for a dispatch")
''')

p.write_text(s, encoding="utf-8", newline="")

q = Path(sys.argv[1]) / "eval" / "run_language_eval.py"
t = q.read_text(encoding="utf-8")
a = '''        summary.update(prompt=client.prompt, grounding=client.grounding, values_corrected_by_grounding=client.grounding_changes)'''
assert t.count(a) == 1
t = t.replace(a, '''        from llm.llm_client import GROUNDING_VERSION
        summary.update(prompt=client.prompt, grounding=client.grounding, grounding_version=GROUNDING_VERSION if client.grounding else None,
                       values_corrected_by_grounding=client.grounding_changes)''')
q.write_text(t, encoding="utf-8", newline="")
print("grounding 2.1 patched")
