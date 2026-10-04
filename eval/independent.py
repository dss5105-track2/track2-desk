"""A second, deliberately separate implementation of the three questions and the delivery estimate.

Used only by the evaluation scripts to check what the system says. It reads the two CSVs directly and
imports nothing from kernel/ or desk/, so an implementation mistake there shows up as a disagreement
here. (A shared misunderstanding of the rules would not: both were written from eval/protocol.md.)
"""
from __future__ import annotations

import csv
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, Iterable, List

DATA = Path(__file__).resolve().parent.parent / "data"
TODAY = date(2026, 4, 1)


def load(data_dir: Path = DATA):
    workshops = {r["workshop_id"]: r for r in csv.DictReader(open(data_dir / "workshops.csv", encoding="utf-8"))}
    orders = {r["order_id"]: r for r in csv.DictReader(open(data_dir / "orders.csv", encoding="utf-8"))}
    return workshops, orders


def eligibility(w: dict, category: str, pieces: int):
    if w["status"] != "ACTIVE":
        return False, "status"
    if category not in w["makes"].split("+"):
        return False, "category"
    if w["max_batch_pieces"] and pieces > int(w["max_batch_pieces"]):
        return False, "batch limit"
    return True, ""


def estimate(w: dict, pieces: int, queue_days: float, due: date, today: date = TODAY) -> dict:
    work = pieces / float(w["capacity_pieces_per_day"])
    finish = queue_days + work * (1 + 0.5 * float(w["defect_rate"])) + int(w["pickup_lead_days"])
    back = today + timedelta(days=round(finish))
    return {"workshop_id": w["workshop_id"], "finish_days": finish, "back": back, "on_time": back <= due, "late_days": max(0, (back - due).days),
            "cost": pieces * float(w["cost_per_piece"]), "defect_rate": float(w["defect_rate"])}


def candidates(workshops: Dict[str, dict], order: dict, queues: Dict[str, float], exclude: Iterable[str] = ()) -> List[dict]:
    pieces, due = int(order["pieces"]), date.fromisoformat(order["due_date"])
    ex = set(exclude)
    out = [estimate(w, pieces, queues[wid], due) for wid, w in workshops.items()
           if wid not in ex and eligibility(w, order["category"], pieces)[0]]
    return sorted(out, key=lambda c: c["finish_days"])


def sound_decision(decision: dict, order: dict, workshops: Dict[str, dict], queues: Dict[str, float], exclude: Iterable[str],
                   preference: str = "") -> List[str]:
    """The four conditions in the labelling rules, checked against the ledger state at that moment.
    Returns the list of violated conditions (empty = sound)."""
    problems = []
    cands = candidates(workshops, order, queues, exclude)
    by_id = {c["workshop_id"]: c for c in cands}
    on_time = [c for c in cands if c["on_time"]]
    rec = decision.get("recommended")
    sub = decision.get("subtype")
    if sub == "allocate":
        if rec not in by_id:
            problems.append(f"recommended {rec} is ineligible or excluded")
        elif not by_id[rec]["on_time"]:
            problems.append(f"says on time but {rec} is {by_id[rec]['late_days']} days late")
        elif preference == "fastest" and by_id[rec]["finish_days"] > on_time[0]["finish_days"] + 1e-9:
            problems.append("fastest was asked; a faster on-time shop exists")
        elif preference == "cheapest_on_time" and by_id[rec]["cost"] > min(c["cost"] for c in on_time) + 1e-9:
            problems.append("cheapest on time was asked; a cheaper on-time shop exists")
        elif preference == "lowest_defect" and by_id[rec]["defect_rate"] > min(c["defect_rate"] for c in on_time) + 1e-9:
            problems.append("lowest defect was asked; a lower-defect on-time shop exists")
    elif sub == "no_on_time_option":
        if on_time:
            problems.append("says no on-time option but " + ",".join(c["workshop_id"] for c in on_time) + " is on time")
        elif rec is not None and rec not in by_id:
            problems.append(f"recommended {rec} is ineligible or excluded")
    elif sub == "ineligible_suggestion":
        refused = decision.get("refused_workshop")
        if refused and refused in by_id:
            problems.append(f"refused {refused}, which is eligible")
        if rec is not None:
            if rec not in by_id:
                problems.append(f"alternative {rec} is ineligible or excluded")
            elif on_time and not by_id[rec]["on_time"]:
                problems.append("an on-time alternative exists but a late one was offered")
    return problems
