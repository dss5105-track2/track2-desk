"""Presentation helpers for constraint-change feedback; never change allocations."""
from __future__ import annotations

from copy import deepcopy
from datetime import date
import re


def collect_change_report(desk, state) -> None:
    """Consume each backend report once; retain row markers until the next desk action.

    Refreshing/navigating the interface does not create history, actions or ledger
    entries. Keeping the Desk reference also distinguishes Reset/parser sessions.
    """
    revision = (desk, len(desk.history), len(desk.actions),
                len(desk.ledger.records), desk.alloc.objective)
    previous = state.get("change_feedback_revision")
    if previous != revision:
        state.pop("pending_change_report", None)
        state["changed_request_ids"] = ()
        if previous is not None and previous[0] is not desk:
            state.pop("last_change_report", None)

    if desk.last_change is not None:
        report = deepcopy(desk.last_change)
        state["last_change_report"] = report
        state["pending_change_report"] = report
        state["changed_request_ids"] = tuple(row["request_id"] for row in report["open_changed"])
        desk.last_change = None
    state["change_feedback_revision"] = revision


def take_change_report(state):
    """The notice appears on one render; the archived report is never replayed."""
    return state.pop("pending_change_report", None)


def workshop_label(workshop_id, name) -> str:
    if not workshop_id:
        return "No recommendation"
    try:
        return name(workshop_id)
    except KeyError:
        return f"Unknown workshop ({workshop_id})"


def order_labels(order_id, orders) -> tuple[str, str]:
    order = orders.get(order_id)
    return (order.customer, order.product) if order is not None else ("", "")


def risk_label(risk: str) -> str:
    """Format only dates supplied by the backend; preserve unfamiliar risk text."""
    patterns = [
        (r"late if reworked: back (\d{4}-\d{2}-\d{2}) if reworked, due (\d{4}-\d{2}-\d{2})",
         "Late if reworked"),
        (r"late: back (\d{4}-\d{2}-\d{2}), due (\d{4}-\d{2}-\d{2})", "Late"),
    ]
    for pattern, label in patterns:
        match = re.fullmatch(pattern, risk)
        if match:
            try:
                back, due = (date.fromisoformat(value).strftime("%a %d %b") for value in match.groups())
            except ValueError:
                return risk
            return f"{label}: back {back}; due {due}."
    return risk


def change_tables(report: dict, name) -> tuple[list[dict], list[dict]]:
    changed = [{
        "Request": row["request_id"], "Order": row.get("order_id") or "",
        "Before workshop": workshop_label(row["before"].get("recommended"), name),
        "After workshop": workshop_label(row["after"].get("recommended"), name),
        "Before decision": row["before"].get("subtype", "").replace("_", " "),
        "After decision": row["after"].get("subtype", "").replace("_", " "),
    } for row in report["open_changed"]]
    dispatched = [{
        "Request": row["request_id"], "Order": row.get("order_id") or "",
        "Workshop": workshop_label(row.get("workshop_id"), name), "Audit": row.get("audit_id", ""),
        "Risks": " · ".join(risk_label(risk) for risk in row.get("risks", [])) or "No risk reported",
    } for row in report["dispatched"]]
    return changed, dispatched


def inbox_styles(row) -> list[str]:
    styles = ["background-color: #fff3cd;" if row["Update"] else "" for _ in row]
    if "⚠ tight" in row["Decision"]:
        styles[row.index.get_loc("Decision")] += "color: #8a4b00; font-weight: bold;"
    return styles
