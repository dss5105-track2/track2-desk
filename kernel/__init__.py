"""Deterministic kernel for the SweaterCo subcontracting desk (Track 2).

Zero LLM in this package. Four public entry points, frozen in week 1:

    register.eligible_workshops(...)   can they make it / are they allowed to
    estimator.estimate(...)            queue + work + expected rework + transport
    allocator.Allocator(...).rank(...) objective-as-configuration ranking
    ledger.Ledger.commit(...)          the auditable record + queue update
"""
