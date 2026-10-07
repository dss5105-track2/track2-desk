"""One-off patch (round 2): resolve "last week" and "big" when a message points at an order without
naming it (R19), and stop treating an in-house PACKING stage as a conflict (v3 data dictionary: the
inbox is about orders still in progress, whatever their stage).
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


patch("kernel/orders.py", [
    ('''def find_orders(orders: Dict[str, Order], customer: Optional[str] = None, product: Optional[str] = None,
                in_progress_only: bool = True) -> List[Order]:
    out = []
    for o in orders.values():''', '''def last_week(today: date = TODAY):
    """Monday to Sunday of the calendar week before `today`."""
    monday = today - timedelta(days=today.weekday() + 7)
    return monday, monday + timedelta(days=6)


def find_orders(orders: Dict[str, Order], customer: Optional[str] = None, product: Optional[str] = None,
                in_progress_only: bool = True, placed_from: Optional[date] = None, placed_to: Optional[date] = None,
                largest_first: bool = False) -> List[Order]:
    out = []
    for o in orders.values():
        if placed_from and o.order_date < placed_from:
            continue
        if placed_to and o.order_date > placed_to:
            continue'''),
    ('''        out.append(o)
    return sorted(out, key=lambda o: o.due_date)''', '''        out.append(o)
    if largest_first:
        return sorted(out, key=lambda o: (-o.pieces, o.order_id))
    return sorted(out, key=lambda o: o.due_date)'''),
])

patch("desk/pipeline.py", [
    ("from kernel.orders import load_orders, find_orders, state_checks, TODAY  # noqa: E402",
     "from kernel.orders import load_orders, find_orders, last_week, state_checks, TODAY  # noqa: E402"),
    ('''            cands = find_orders(self.O, customer=req["customer"], product=req["product"]) if (req["customer"] or req["product"]) else []
            d["tool_calls"].append({"tool": "resolve_order_reference", "input": {"customer": req["customer"], "product": req["product"]},''',
     '''            low = req["raw_text"].lower()
            window = last_week(TODAY) if "last week" in low else (None, None)
            big = bool(re.search(r"\\bbig\\b|\\blarge\\b|\\bbiggest\\b", low))
            cands = (find_orders(self.O, customer=req["customer"], product=req["product"], placed_from=window[0], placed_to=window[1],
                                 largest_first=big) if (req["customer"] or req["product"] or window[0]) else [])
            d["tool_calls"].append({"tool": "resolve_order_reference",
                                    "input": {"customer": req["customer"], "product": req["product"],
                                              "placed_from": window[0].isoformat() if window[0] else None,
                                              "placed_to": window[1].isoformat() if window[1] else None, "largest_first": big},'''),
    ('''                    d["explanation"] = f"Which order do you mean? {len(cands)} in-progress orders match: {listing}."''',
     '''                    scope = f" placed last week ({window[0]} to {window[1]}), largest first" if window[0] else ""
                    d["explanation"] = f"Which order do you mean? {len(cands)} in-progress orders match{scope}: {listing}."'''),
    ('''        conflict = [f for f in flags if "PACKING" in f or "COMPLETE" in f or "already dispatched" in f]''',
     '''        # v3 data dictionary: the inbox is about orders still in progress, so an in-house stage (even PACKING)
        # is context for the dispatcher, not a reason to stop. A finished order or a repeat dispatch is.
        conflict = [f for f in flags if "COMPLETE" in f or "already dispatched" in f]'''),
])
print("lookup patched")
