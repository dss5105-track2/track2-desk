"""Round-2 patch to desk/pipeline.py: work that is not in the order book yet.

Found on the challenge inbox: "Maple & Co will send a repeat order this afternoon, numbers not final" was
answered with "Which order do you mean?" and a list of Maple & Co's existing orders. The right question is
for the missing details. The router now trusts the parsed request: when the parser says pieces or due
date are missing and no order is named, it asks for them, and still lists matching in-progress orders in
case the sender meant one of those (which also serves R01, "scarves for Harbor Knits, usual quantities").
"""
import sys
from pathlib import Path

p = Path(sys.argv[1]) / "desk" / "pipeline.py"
s = p.read_text(encoding="utf-8")
a = s[s.index("            if NEW_ORDER_RE.search(req[\"raw_text\"]) or (prior_dec and prior_dec[\"subtype\"] == \"missing_fields\"):"):
      s.index("            if len(cands) == 1:")]
b = r'''            low = req["raw_text"].lower()
            window = last_week(TODAY) if "last week" in low else (None, None)
            big = bool(re.search(r"\bbig\b|\blarge\b|\bbiggest\b", low))
            cands = (find_orders(self.O, customer=req["customer"], product=req["product"], placed_from=window[0], placed_to=window[1],
                                 largest_first=big) if (req["customer"] or req["product"] or window[0]) else [])
            d["tool_calls"].append({"tool": "resolve_order_reference",
                                    "input": {"customer": req["customer"], "product": req["product"],
                                              "placed_from": window[0].isoformat() if window[0] else None,
                                              "placed_to": window[1].isoformat() if window[1] else None, "largest_first": big},
                                    "output": {"count": len(cands),
                                               "orders": [{"order_id": o.order_id, "customer": o.customer, "product": o.product,
                                                           "pieces": o.pieces, "due_date": o.due_date.isoformat(), "stage": o.current_stage}
                                                          for o in cands]}})
            listing = "; ".join(f"{o.order_id} {o.customer} {o.product} {o.pieces} pcs due {o.due_date}" for o in cands)
            # not an order yet, or the message leaves quantity / date undefined: ask for the details, do not guess an order
            new_work = (NEW_ORDER_RE.search(req["raw_text"]) or (prior_dec and prior_dec["subtype"] == "missing_fields")
                        or bool({"pieces", "due_date"} & set(req["missing_fields"])))
            if new_work:
                d["subtype"] = "missing_fields"
                d["order_candidates"] = [o.order_id for o in cands]
                ref = f" (follow-up to {prior['request_id']})" if prior else ""
                d["explanation"] = (f"I can't book capacity yet{ref}: I need the order number, piece count and due date. "
                                    "Capacity depends on them, so I won't guess."
                                    + (f" If you mean an order already in progress, say which: {listing}." if cands else ""))
                return d
'''
assert a.count("NEW_ORDER_RE") == 1
s = s.replace(a, b)
a2 = '''                if cands:
                    listing = "; ".join(f"{o.order_id} {o.customer} {o.product} {o.pieces} pcs due {o.due_date}" for o in cands)
                    scope'''
assert s.count(a2) == 1
s = s.replace(a2, '''                if cands:
                    scope''')
p.write_text(s, encoding="utf-8", newline="")
print("new-work routing patched")
