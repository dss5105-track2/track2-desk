"""Provider-agnostic LLM client interface + the rule-based fallback parser.

Week-1 scope: the *interface* and the *fallback*. No network call is made here yet.
The language layer (week 3) will call `LLMClient.parse_request()`; when the model is
unavailable, over budget, or returns malformed JSON, `RuleBasedParser` produces the same
schema (language/schema.md) from regexes, so the demo never depends on the network.

Configuration is read from environment variables, never from the repo:
    DESK_LLM_PROVIDER   anthropic | openai | none      (default none -> rules only)
    DESK_LLM_MODEL      model id
    DESK_LLM_API_KEY    key
    DESK_LLM_BUDGET_USD hard stop for the session (default 5)
"""
from __future__ import annotations

import json
import os
import re
from datetime import date
from typing import Dict, List, Optional

MONTHS = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12}

PRODUCT_WORDS = {
    # word in chat -> (product in orders.csv, category)
    "vest": ("Vest", "TOPS"), "vests": ("Vest", "TOPS"),
    "hoodie": ("Hoodie", "TOPS"), "hoodies": ("Hoodie", "TOPS"),
    "polo": ("Polo shirt", "TOPS"), "polos": ("Polo shirt", "TOPS"), "polo shirt": ("Polo shirt", "TOPS"), "polo shirts": ("Polo shirt", "TOPS"),
    "crewneck": ("Crewneck sweater", "TOPS"), "crewnecks": ("Crewneck sweater", "TOPS"),
    "crewneck sweater": ("Crewneck sweater", "TOPS"), "crewneck sweaters": ("Crewneck sweater", "TOPS"),
    "cardigan": ("Cardigan", "TOPS"), "cardigans": ("Cardigan", "TOPS"),
    "scarf": ("Scarf", "ACCESSORIES"), "scarves": ("Scarf", "ACCESSORIES"),
    "beanie": ("Beanie", "ACCESSORIES"), "beanies": ("Beanie", "ACCESSORIES"),
}
CUSTOMERS = ["UrbanThread", "TrendCart", "Cotton Club", "Harbor Knits", "Bright Basics", "Loom & Leaf", "Maple & Co", "Northwind Apparel"]
WORKSHOP_NAMES = {"QuickStitch": "W1", "SteadyHands": "W2", "BudgetWorks": "W3", "Little Loom": "W4",
                  "GiantWeave": "W5", "Nimble Needle": "W6", "OldMill": "W7", "FreshStart": "W8"}

LINE_RE = re.compile(r"^(R\d+)\s+\[(\d\d:\d\d)\]\s+([A-Za-z]+):\s*(.*)$")
ORD_RE = re.compile(r"\bORD-\d{3}\b")
DATE_RE = re.compile(r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{1,2})\b", re.I)
PIECES_RE = re.compile(r"\b(\d[\d,]*)\s+(polo shirts?|crewneck sweaters?|vests?|hoodies?|polos?|crewnecks?|cardigans?|scarves|scarf|beanies?)\b", re.I)
EXCLUDE_PATTERNS = [r"keep it away from\s+([A-Za-z &]+)", r"nothing new to\s+([A-Za-z &]+)", r"not\s+([A-Za-z &]+?)\b", r"avoid\s+([A-Za-z &]+)"]


def empty_request() -> Dict:
    return {
        "request_id": None, "timestamp": None, "requester": None, "raw_text": None,
        "order_id": None, "order_ref_hint": None, "customer": None, "product": None, "category": None,
        "pieces": None, "due_date": None, "forced_workshop": None, "excluded_workshops": [], "constraint_scope": "request",
        "preference": "none", "references_prior": None, "question_type": "allocation",
        "missing_fields": [], "parser": None, "notes": [],
    }


class RuleBasedParser:
    """Deterministic extraction. Good enough to keep the demo alive; not the final parser."""

    def __init__(self, year: int = 2026):
        self.year = year

    def parse(self, line: str, prior: Optional[List[Dict]] = None) -> Dict:
        r = empty_request()
        r["parser"] = "rules"
        m = LINE_RE.match(line.strip())
        text = line
        if m:
            r["request_id"], r["timestamp"], r["requester"], text = m.groups()
        r["raw_text"] = text
        low = text.lower()

        ords = ORD_RE.findall(text)
        if ords:
            r["order_id"] = ords[0]

        for c in CUSTOMERS:
            if c.lower() in low:
                r["customer"] = c
        for word, (prod, cat) in sorted(PRODUCT_WORDS.items(), key=lambda kv: -len(kv[0])):
            if re.search(r"\b" + re.escape(word) + r"\b", low):
                r["product"], r["category"] = prod, cat
                break

        pm = PIECES_RE.search(text)
        if pm:
            r["pieces"] = int(pm.group(1).replace(",", ""))

        dm = DATE_RE.search(text)
        if dm:
            r["due_date"] = date(self.year, MONTHS[dm.group(1).lower()[:3]], int(dm.group(2))).isoformat()

        # workshops: exclusions first, everything else mentioned is a suggestion
        excluded = set()
        for pat in EXCLUDE_PATTERNS:
            for em in re.finditer(pat, text, re.I):
                for name, wid in WORKSHOP_NAMES.items():
                    if name.lower() in em.group(1).lower():
                        excluded.add(wid)
        mentioned = [wid for name, wid in WORKSHOP_NAMES.items() if name.lower() in low]
        r["excluded_workshops"] = sorted(excluded)
        if excluded and re.search(r"this week|until further notice|for now|anymore", low):
            r["constraint_scope"] = "session"
        forced = [wid for wid in mentioned if wid not in excluded]
        r["forced_workshop"] = forced[0] if forced else None

        if re.search(r"fastest|quickest|asap|as soon as", low):
            r["preference"] = "fastest"
        elif "cheapest" in low or "margin is thin" in low:
            r["preference"] = "cheapest_on_time"
        elif re.search(r"lowest defect|defect rate|rejected a batch|quality", low):
            r["preference"] = "lowest_defect"
        elif "split" in low:
            r["preference"] = "split"

        if re.search(r"\bwhich workshop did we use\b|last (october|month|year)|what price|quote(d)? .* on", low):
            r["question_type"] = "information"
        if re.search(r"any movement|how is|status", low) and not r["pieces"]:
            r["question_type"] = "status"

        # cross-message references
        if prior:
            if re.search(r"\bthat\b|\bthe (big )?reorder\b|stuff|details to follow|will confirm", low):
                same_person = [p for p in prior if p.get("requester") == r["requester"]]
                if same_person:
                    r["references_prior"] = same_person[-1]["request_id"]
            for p in prior:
                if r["order_id"] and p.get("order_id") == r["order_id"]:
                    r["notes"].append(f"same order as {p['request_id']}")

        missing = []
        if not r["order_id"]:
            missing.append("order_id")
        if r["pieces"] is None and r["question_type"] == "allocation":
            missing.append("pieces")
        if r["due_date"] is None and r["question_type"] == "allocation":
            missing.append("due_date")
        r["missing_fields"] = missing
        return r


class LLMClient:
    """Thin wrapper. `complete()` is provider-specific; everything else is provider-agnostic."""

    def __init__(self, provider: Optional[str] = None, model: Optional[str] = None, budget_usd: Optional[float] = None):
        self.provider = (provider or os.getenv("DESK_LLM_PROVIDER", "none")).lower()
        self.model = model or os.getenv("DESK_LLM_MODEL", "")
        self.api_key = os.getenv("DESK_LLM_API_KEY", "")
        self.budget_usd = float(budget_usd if budget_usd is not None else os.getenv("DESK_LLM_BUDGET_USD", "5"))
        self.spent_usd = 0.0
        self.fallback = RuleBasedParser()
        self.calls: List[Dict] = []     # every call is logged: prompt hash, model, tokens, cost, outcome

    # ---- to be implemented per provider in week 3 -------------------------
    def complete(self, system: str, user: str, json_schema: Optional[dict] = None) -> str:
        if self.provider == "none" or not self.api_key:
            raise RuntimeError("LLM disabled or no API key")
        if self.spent_usd >= self.budget_usd:
            raise RuntimeError(f"budget of {self.budget_usd} USD exhausted")
        raise NotImplementedError(f"provider {self.provider!r}: implement complete() in week 3")

    # ---- provider-agnostic ---------------------------------------------------
    def parse_request(self, line: str, prior: Optional[List[Dict]] = None, system_prompt: str = "") -> Dict:
        """Returns a request dict per language/schema.md. Falls back to rules on any failure."""
        try:
            raw = self.complete(system_prompt, line)
            data = json.loads(raw)
            base = empty_request(); base.update(data); base["parser"] = f"llm:{self.model}"
            self.calls.append({"line": line, "outcome": "ok"})
            return base
        except Exception as ex:           # noqa: BLE001 - any failure must degrade, never crash the desk
            self.calls.append({"line": line, "outcome": f"fallback: {type(ex).__name__}: {ex}"})
            r = self.fallback.parse(line, prior)
            r["notes"].append(f"fallback: {type(ex).__name__}")
            return r


if __name__ == "__main__":
    import sys
    from pathlib import Path
    src = Path(__file__).resolve().parent.parent / "data" / "dispatch_requests.txt"
    prior: List[Dict] = []
    p = RuleBasedParser()
    for line in src.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        r = p.parse(line, prior)
        prior.append(r)
        print(json.dumps({k: r[k] for k in ("request_id", "requester", "order_id", "customer", "product", "pieces", "due_date",
                                            "forced_workshop", "excluded_workshops", "constraint_scope", "preference",
                                            "question_type", "references_prior", "missing_fields")},
                         ensure_ascii=False))
