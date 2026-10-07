"""Round-2 patch: a follow-up that points at existing orders is an ambiguous reference, not new work.

R15 ("Boss wants the Loom & Leaf stuff outside asap") follows R10 ("new rush from Loom & Leaf, details to
follow"). Six Loom & Leaf orders are in progress, so the desk lists them and asks which, and also asks
whether it is the new work from R10. Whether quantity and date are missing is decided from the message
itself, not inherited from the earlier one. With this the desk's counts match the instructor's mix
(4 ambiguous, 3 missing) and the proposed labels.
"""
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])

p = root / "llm" / "llm_client.py"
s = p.read_text(encoding="utf-8")
a = '''                             or (ref and "pieces" in ref.get("missing_fields", [])))'''
assert s.count(a) == 1
s = s.replace(a, ''')''')
a = '''                undefined = (re.search('''
assert s.count(a) == 1
p.write_text(s, encoding="utf-8", newline="")

p = root / "desk" / "pipeline.py"
s = p.read_text(encoding="utf-8")
a = '''            new_work = (NEW_ORDER_RE.search(req["raw_text"]) or (prior_dec and prior_dec["subtype"] == "missing_fields")
                        or bool({"pieces", "due_date"} & set(req["missing_fields"])))'''
assert s.count(a) == 1
s = s.replace(a, '''            new_work = bool(NEW_ORDER_RE.search(req["raw_text"]) or ({"pieces", "due_date"} & set(req["missing_fields"]))
                            or (prior_dec and prior_dec["subtype"] == "missing_fields" and not cands))''')
a = '''                    d["explanation"] = f"Which order do you mean? {len(cands)} in-progress orders match{scope}: {listing}."'''
assert s.count(a) == 1
s = s.replace(a, a + '''
                    if prior_dec and prior_dec["subtype"] == "missing_fields":
                        d["explanation"] += f" Or is this the new work from {prior['request_id']}? Then I need the piece count and due date."''')
p.write_text(s, encoding="utf-8", newline="")

p = root / "language" / "requests_gold.json"
lines = p.read_text(encoding="utf-8").split("\n")
n = 0
for i, line in enumerate(lines):
    if '"request_id":"R15"' in line:
        body = line.strip().rstrip(",")
        e = json.loads(body)
        e["missing_fields"] = ["order_id"]
        e["notes"] = [x for x in e.get("notes", [])] + ["missing only the order: quantity and date come from the order book once it is named"]
        lines[i] = "  " + json.dumps(e, ensure_ascii=False, separators=(",", ":")) + ("," if line.rstrip().endswith(",") else "")
        n += 1
assert n == 1
p.write_text("\n".join(lines), encoding="utf-8", newline="")
print("follow-up patched")
