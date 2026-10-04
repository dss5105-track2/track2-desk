"""Objective-as-configuration allocator, plus the simple rule-based allocator it must be compared with.

An objective is one of two things.

1. A set of weights. Every candidate gets a score = sum(weight_k * normalised_metric_k); lower is
   better. Metrics are normalised inside the candidate set so weights are comparable across orders:
       late    predicted late days / max late days among candidates (0 if nobody is late)
       finish  predicted finish days / max finish days among candidates
       defect  defect_rate / max defect_rate in the register
       load    pieces already sent to this workshop / total pieces sent so far (fairness needs state)
       cost    cost / max cost among candidates
   Ties are broken by earliest finish.

2. A priority rule (the primary objective, lateness, since round 2). In order:
       a. keep the workshops that make the date even if the batch is reworked ("safe");
          if there are none, the workshops that make the date; if none, everyone
       b. among safe workshops, the least flexible one first: a shop that only makes this category,
          or one with a batch cap, before a shop that could also take the other category's work
       c. then the earliest finish ("tie": "earliest") or the latest safe finish ("tie": "latest")
   Why: earliest-finish spends the fast, flexible shops on batches that had slack to spare, and the
   next tight batch then has nowhere to go. See docs/allocator_v2.md for the evidence.

The class implements the simulate.py allocator signature, so
`Simulator().run(Allocator("lateness"), "lateness")` just works.
"""
from __future__ import annotations

from typing import Dict, Iterable, List, Optional

from .estimator import estimate
from .register import eligible_workshops

OBJECTIVES: Dict[str, Dict] = {
    # primary objective: on time safely, specialist first, then earliest finish
    "lateness": dict(rule="specialist_first", tie="earliest"),
    # fewest defects among shops that can still make the date
    "defects":  dict(late=1.0, finish=0.0, defect=1.0, load=0.0, cost=0.0),
    # spread work, but never at the price of a late batch
    "fairness": dict(late=1.0, finish=0.0, defect=0.0, load=1.0, cost=0.0),
    # hybrid v2: weights chosen on a defect x load grid (docs/results), checked on held-out seeds
    "hybrid":   dict(late=1.0, finish=0.3, defect=0.25, load=0.5, cost=0.0),
    # cheapest that still makes the date (R21 style)
    "cost":     dict(late=1.0, finish=0.0, defect=0.0, load=0.0, cost=1.0),
    # same rule as lateness, but among equals take the latest safe finish: uses the slack, costs less
    "use_slack": dict(rule="specialist_first", tie="latest"),
    # kept so earlier results can be reproduced
    "lateness_v1": dict(late=1.0, finish=0.3, defect=0.0, load=0.0, cost=0.0),   # ties earliest_finish
    "hybrid_v0":   dict(late=0.6, finish=0.0, defect=0.2, load=0.2, cost=0.0),
}

# per-request overrides coming from the chat ("fastest", "cheapest that makes it", "lowest defect")
PREFERENCE_OVERRIDES: Dict[str, Dict[str, float]] = {
    "fastest":          dict(late=1.0, finish=1.0, defect=0.0, load=0.0, cost=0.0),
    "cheapest_on_time": dict(late=5.0, finish=0.0, defect=0.0, load=0.0, cost=1.0),
    "lowest_defect":    dict(late=5.0, finish=0.0, defect=1.0, load=0.0, cost=0.0),
}

TIER_TEXT = {0: "on time even if the batch is reworked", 1: "on time, but not if the batch is reworked", 2: "late"}


def flexibility(w) -> float:
    """How much of the order book a workshop could take: one point per category it makes, half a
    point less if it is batch-capped. Lower = more of a specialist."""
    return len(w.makes) - (0.5 if w.max_batch is not None else 0.0)


class Allocator:
    def __init__(self, objective: str = "lateness", weights: Optional[Dict[str, float]] = None,
                 include_rework: bool = True):
        self.rule: Optional[Dict] = None
        if weights is None:
            if objective not in OBJECTIVES:
                raise KeyError(f"unknown objective {objective!r}; choose from {sorted(OBJECTIVES)}")
            cfg = OBJECTIVES[objective]
            if "rule" in cfg:
                self.rule, weights = dict(cfg), {}
            else:
                weights = cfg
        self.objective = objective
        self.weights = dict(weights)
        self.include_rework = include_rework
        self.load: Dict[str, int] = {}      # pieces committed per workshop (fairness state)

    # ---- ranking -------------------------------------------------------------
    def rank(self, batch: dict, workshops, queues: Dict[str, float],
             exclude: Iterable[str] = (), preference: Optional[str] = None) -> List[dict]:
        cands = eligible_workshops(workshops, batch["category"], batch["pieces"], exclude)
        if not cands:
            return []
        ests = [
            estimate(w, batch["pieces"], queues.get(w.workshop_id, getattr(w, "queue0", 0.0)),
                     batch["sent_date"], batch["due_date"], self.include_rework)
            for w in cands
        ]
        if self.rule and not preference:
            return self._rank_by_rule(cands, ests)
        weights = dict(PREFERENCE_OVERRIDES[preference]) if preference else dict(self.weights)
        if not weights:                      # a rule objective asked for a preference it has no weights for
            weights = dict(OBJECTIVES["lateness_v1"])
        max_late = max(1, max(e.late_days for e in ests))
        max_finish = max(e.finish_days for e in ests) or 1.0
        max_defect = max(w.defect_rate for w in workshops.values()) or 1.0
        max_cost = max(e.cost for e in ests) or 1.0
        total_load = sum(self.load.values()) or 1
        rows = []
        for w, e in zip(cands, ests):
            parts = {
                "late":   weights["late"]   * e.late_days / max_late,
                "finish": weights["finish"] * e.finish_days / max_finish,
                "defect": weights["defect"] * w.defect_rate / max_defect,
                "load":   weights["load"]   * self.load.get(w.workshop_id, 0) / total_load,
                "cost":   weights["cost"]   * e.cost / max_cost,
            }
            rows.append({"estimate": e, "score": sum(parts.values()), "parts": parts, "weights": weights})
        rows.sort(key=lambda r: (r["score"], r["estimate"].finish_days))
        return rows

    def _rank_by_rule(self, cands, ests) -> List[dict]:
        latest = self.rule.get("tie") == "latest"
        rows = []
        for w, e in zip(cands, ests):
            tier = 0 if e.safe else (1 if e.on_time else 2)
            flex = flexibility(w)
            if tier == 0:
                key = (0, flex, -e.finish_days if latest else e.finish_days)
            elif tier == 1:
                key = (1, flex, e.finish_days)
            else:
                key = (2, e.late_days, e.finish_days)
            rows.append({"estimate": e, "score": float(tier), "key": key, "tier": tier,
                         "parts": {"tier": tier, "flexibility": flex}, "weights": {}, "rule": dict(self.rule)})
        rows.sort(key=lambda r: r["key"])
        return rows

    def choose(self, batch: dict, workshops, queues: Dict[str, float],
               exclude: Iterable[str] = (), preference: Optional[str] = None) -> Optional[str]:
        rows = self.rank(batch, workshops, queues, exclude, preference)
        if not rows:
            return None
        best = rows[0]["estimate"].workshop_id
        self.load[best] = self.load.get(best, 0) + batch["pieces"]
        return best

    # ---- simulate.py signature ----------------------------------------------
    def __call__(self, batch: dict, workshops, queues: Dict[str, float]) -> str:
        wid = self.choose(batch, workshops, queues)
        if wid is None:
            raise ValueError(f"no eligible workshop for {batch['order_id']}")
        return wid

    def reset(self) -> None:
        self.load = {}


def earliest_finish(batch, workshops, queues):
    """The simple rule-based allocator (Tracks v4: no LLM, about the size of the shipped baselines).
    Every result in the report is compared against this."""
    ok = eligible_workshops(workshops, batch["category"], batch["pieces"])
    return min(ok, key=lambda w: queues[w.workshop_id] + batch["pieces"] / w.capacity + w.lead_days).workshop_id


def earliest_finish_with_rework(batch, workshops, queues):
    """Same, but with the expected defect rework folded in."""
    ok = eligible_workshops(workshops, batch["category"], batch["pieces"])
    return min(ok, key=lambda w: queues[w.workshop_id]
               + (batch["pieces"] / w.capacity) * (1 + 0.5 * w.defect_rate) + w.lead_days).workshop_id
