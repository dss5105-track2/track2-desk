"""Orders table helpers: load orders.csv and the state cross-checks the protocol requires."""
from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List, Optional

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
TODAY = date(2026, 4, 1)   # data_dictionary.md: "today" in the dataset


@dataclass(frozen=True)
class Order:
    order_id: str
    customer: str
    product: str
    category: str
    pieces: int
    order_date: date
    due_date: date
    status: str
    current_stage: str
    last_activity_date: date
    completed_date: Optional[date]
    days_late: Optional[int]


def load_orders(path: Path = DATA_DIR / "orders.csv") -> Dict[str, Order]:
    out: Dict[str, Order] = {}
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            out[r["order_id"]] = Order(
                order_id=r["order_id"], customer=r["customer"], product=r["product"], category=r["category"],
                pieces=int(r["pieces"]), order_date=date.fromisoformat(r["order_date"]),
                due_date=date.fromisoformat(r["due_date"]), status=r["status"], current_stage=r["current_stage"],
                last_activity_date=date.fromisoformat(r["last_activity_date"]),
                completed_date=date.fromisoformat(r["completed_date"]) if r["completed_date"] else None,
                days_late=int(r["days_late"]) if r["days_late"] else None,
            )
    return out


def last_week(today: date = TODAY):
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
            continue
        if customer and o.customer.lower() != customer.lower():
            continue
        if product and o.product.lower() != product.lower():
            continue
        if in_progress_only and o.status != "IN_PROGRESS":
            continue
        out.append(o)
    if largest_first:
        return sorted(out, key=lambda o: (-o.pieces, o.order_id))
    return sorted(out, key=lambda o: o.due_date)


def state_checks(order: Optional[Order], today: date = TODAY, ledger=None) -> List[str]:
    """The protocol's cross-checks. Any non-empty result means: warn or clarify before allocating."""
    if order is None:
        return ["order not found"]
    flags = []
    if order.status == "COMPLETE":
        flags.append(f"order already COMPLETE on {order.completed_date}")
    elif order.current_stage == "PACKING":
        flags.append(f"order is in PACKING in-house (last activity {order.last_activity_date}); farming out makes little sense")
    if order.due_date < today:
        flags.append(f"due date {order.due_date} already passed ({(today - order.due_date).days} days ago)")
    elif order.due_date == today:
        flags.append("due today: no workshop can return it today (every pickup_lead_days >= 1)")
    if ledger is not None:
        prior = ledger.already_committed(order.order_id)
        if prior is not None:
            flags.append(f"already dispatched to {prior['workshop_id']} by {prior['request_id']} ({prior['audit_id']})")
    return flags
