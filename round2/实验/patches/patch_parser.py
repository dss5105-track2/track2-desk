"""One-off patch applied to track2-desk-优化版/llm/llm_client.py in round 2 (kept for the record).

  1. references_prior: a message that names its own order does not continue an earlier one just because
     the customer is the same and it contains the word "that" (R21, R23 were wrongly linked to R01, R13)
  2. references_prior: a second message about the same order id links to the first (R20 -> R14)
  3. missing_fields: pointing at an existing order without its id ("the TrendCart order") is missing the
     order id only; pieces and due date are missing too only when the work is not in the order book yet
     or the message leaves them undefined ("new rush, details to follow", "usual quantities")
  4. the LLM instructions say the same, so both parsers are scored against one convention
"""
import sys
from pathlib import Path

p = Path(sys.argv[1])
s = p.read_text(encoding="utf-8")


def rep(a, b):
    global s
    assert s.count(a) == 1, (s.count(a), a[:70])
    s = s.replace(a, b)


rep('''            if r["customer"] and re.search(r"\\bthat\\b|\\bthe (big )?reorder\\b|\\bstuff\\b", low):
                same = [p for p in prior if p.get("requester") == r["requester"] and p.get("customer") == r["customer"]]
                if same:
                    r["references_prior"] = same[-1]["request_id"]
            for p in prior:
                if r["order_id"] and p.get("order_id") == r["order_id"]:
                    r["notes"].append(f"same order as {p['request_id']}")''',
    '''            if not r["order_id"] and r["customer"] and re.search(r"\\bthat (big |last )?(re)?order\\b|\\bthe (big )?reorder\\b|\\bstuff\\b", low):
                same = [p for p in prior if p.get("requester") == r["requester"] and p.get("customer") == r["customer"]]
                if same:
                    r["references_prior"] = same[-1]["request_id"]
            for p in prior:
                if r["order_id"] and p.get("order_id") == r["order_id"] and p.get("question_type") == "allocation":
                    r["notes"].append(f"same order as {p['request_id']}")
                    if r["question_type"] == "allocation":
                        r["references_prior"] = p["request_id"]''')

rep('''            if not r["order_id"]:
                missing.append("order_id")
                if r["pieces"] is None:
                    missing.append("pieces")
                if r["due_date"] is None:
                    missing.append("due_date")''',
    '''            if not r["order_id"]:
                missing.append("order_id")
                # pieces and date come from the order book once the order is identified; they are missing too
                # only when the work is not an existing order, or the message leaves them undefined
                ref = next((p for p in (prior or []) if p.get("request_id") == r["references_prior"]), None)
                undefined = re.search(r"new rush|details to follow|coming in from|usual quantit", low) or (ref and "pieces" in ref.get("missing_fields", []))
                if undefined:
                    if r["pieces"] is None:
                        missing.append("pieces")
                    if r["due_date"] is None:
                        missing.append("due_date")''')

rep('''- missing_fields: for allocation messages, which of order_id, pieces, due_date the message leaves unstated and that cannot be identified from an explicit order id.''',
    '''- missing_fields: for allocation messages only. If the message names an order id, it is empty unless the message itself says a value is still to come ("will confirm the new date" -> ["due_date"]). If it points at an existing order without its id ("the TrendCart order", "that big reorder", "the vests"), it is ["order_id"] only: pieces and due date are in the order book. If it is about work that is not an existing order, or leaves the quantity or date undefined ("new rush, details to follow", "usual quantities"), list order_id and also pieces and due_date when they are unstated.''')

p.write_text(s, encoding="utf-8", newline="")
print("parser patched")
