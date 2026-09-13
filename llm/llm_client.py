"""LLM client (Anthropic Claude) + the rule-based fallback parser.

The language layer calls `LLMClient.parse_request()`. When the model is unavailable,
over budget, refuses, or returns something unusable, `RuleBasedParser` produces the same
schema (language/schema.md) from regexes, so the desk never depends on the network.

The LLM only *extracts* fields from chat text. It never does arithmetic, never looks up
queues, and never chooses a workshop - those come from kernel/.

Configuration comes from environment variables (or a local, git-ignored `.env` file):
    DESK_LLM_PROVIDER    anthropic | none           (default none -> rules only)
    DESK_LLM_MODEL       model id                   (default claude-haiku-4-5)
    ANTHROPIC_API_KEY    API key from console.anthropic.com  (DESK_LLM_API_KEY also accepted)
    DESK_LLM_BUDGET_USD  hard stop for one Python process   (default 5)
See .env.example. Never commit a real key.
"""
from __future__ import annotations

import json
import os
import re
from datetime import date
from typing import Dict, List, Optional, Tuple

try:  # optional convenience: load a local .env if python-dotenv is installed
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

TODAY = "2026-04-01"
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
PRODUCTS = ["Cardigan", "Crewneck sweater", "Hoodie", "Polo shirt", "Vest", "Scarf", "Beanie"]
CUSTOMERS = ["UrbanThread", "TrendCart", "Cotton Club", "Harbor Knits", "Bright Basics", "Loom & Leaf", "Maple & Co", "Northwind Apparel"]
WORKSHOP_NAMES = {"QuickStitch": "W1", "SteadyHands": "W2", "BudgetWorks": "W3", "Little Loom": "W4",
                  "GiantWeave": "W5", "Nimble Needle": "W6", "OldMill": "W7", "FreshStart": "W8"}

LINE_RE = re.compile(r"^([RH]\d+)\s+\[(\d\d:\d\d)\]\s+([A-Za-z]+):\s*(.*)$")
ORD_RE = re.compile(r"\bORD-\d{3}\b")
DATE_RE = re.compile(r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{1,2})\b", re.I)
PIECES_RE = re.compile(r"\b(\d[\d,]*)\s+(polo shirts?|crewneck sweaters?|vests?|hoodies?|polos?|crewnecks?|cardigans?|scarves|scarf|beanies?)\b", re.I)
EXCLUDE_PATTERNS = [r"keep it away from\s+([A-Za-z &]+)", r"nothing new to\s+([A-Za-z &]+)", r"not\s+([A-Za-z &]+?)\b", r"avoid\s+([A-Za-z &]+)"]

# USD per million tokens (input, output). Source: Anthropic pricing table, cached 2026-06-24.
PRICING: Dict[str, Tuple[float, float]] = {
    "claude-haiku-4-5": (1.00, 5.00),
    "claude-sonnet-5": (2.00, 10.00),
    "claude-opus-5": (5.00, 25.00),
}
DEFAULT_MODEL = "claude-haiku-4-5"


def empty_request() -> Dict:
    return {
        "request_id": None, "timestamp": None, "requester": None, "raw_text": None,
        "order_id": None, "order_ref_hint": None, "customer": None, "product": None, "category": None,
        "pieces": None, "due_date": None, "forced_workshop": None, "excluded_workshops": [], "constraint_scope": "request",
        "preference": "none", "references_prior": None, "question_type": "allocation",
        "missing_fields": [], "parser": None, "notes": [],
    }


def parse_header(line: str) -> Tuple[Optional[str], Optional[str], Optional[str], str]:
    """'R07 [08:23] Ravi: text' -> ('R07', '08:23', 'Ravi', 'text'). Deterministic, never sent to the LLM to guess."""
    m = LINE_RE.match(line.strip())
    if m:
        return m.group(1), m.group(2), m.group(3), m.group(4)
    return None, None, None, line.strip()


class RuleBasedParser:
    """Deterministic extraction. Good enough to keep the demo alive; not the final parser."""

    def __init__(self, year: int = 2026):
        self.year = year

    def parse(self, line: str, prior: Optional[List[Dict]] = None) -> Dict:
        r = empty_request()
        r["parser"] = "rules"
        r["request_id"], r["timestamp"], r["requester"], text = parse_header(line)
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


# ---------------------------------------------------------------------------------------
# LLM extraction
# ---------------------------------------------------------------------------------------

def _nullable(schema: dict) -> dict:
    return {"anyOf": [schema, {"type": "null"}]}


EXTRACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "question_type": {"type": "string", "enum": ["allocation", "status", "information"]},
        "order_id": _nullable({"type": "string"}),
        "order_ref_hint": _nullable({"type": "string"}),
        "customer": _nullable({"type": "string", "enum": CUSTOMERS}),
        "product": _nullable({"type": "string", "enum": PRODUCTS}),
        "category": _nullable({"type": "string", "enum": ["TOPS", "ACCESSORIES"]}),
        "pieces": _nullable({"type": "integer"}),
        "due_date": _nullable({"type": "string"}),
        "forced_workshop": _nullable({"type": "string", "enum": list(WORKSHOP_NAMES.values())}),
        "excluded_workshops": {"type": "array", "items": {"type": "string", "enum": list(WORKSHOP_NAMES.values())}},
        "constraint_scope": {"type": "string", "enum": ["request", "session"]},
        "preference": {"type": "string", "enum": ["none", "fastest", "cheapest_on_time", "lowest_defect", "split"]},
        "references_prior": _nullable({"type": "string"}),
        "missing_fields": {"type": "array", "items": {"type": "string", "enum": ["order_id", "pieces", "due_date"]}},
        "notes": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["question_type", "order_id", "order_ref_hint", "customer", "product", "category", "pieces", "due_date",
                 "forced_workshop", "excluded_workshops", "constraint_scope", "preference", "references_prior",
                 "missing_fields", "notes"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = f"""You extract structured fields from one message in a knitwear factory's dispatch group chat.
Today is {TODAY}. Dates without a year are in 2026.

Your only job is extraction. Do not look anything up, do not calculate, do not recommend a workshop.

Rules:
- Extract only what the message itself says. If the message does not state a field, return null. Never fill a field from general knowledge or a guess.
- order_id: an explicit ORD-xxx in the message, else null. If the message refers to an order without an id ("the TrendCart order", "that big reorder"), put that phrase in order_ref_hint.
- pieces and due_date: only when stated. "back by", "ship date", "deadline", "due", "make <date>" all mean due_date (ISO yyyy-mm-dd).
- Workshops map to ids: {json.dumps(WORKSHOP_NAMES)}.
- A workshop the sender wants used goes in forced_workshop. A workshop to avoid ("keep it away from", "nothing new to", "avoid") goes in excluded_workshops, not forced_workshop.
- constraint_scope is "session" only when an exclusion is meant to last beyond this one order (e.g. "this week"); otherwise "request".
- preference: "fastest" for fastest/quickest/asap; "cheapest_on_time" for cheapest that still meets the date; "lowest_defect" for quality or lowest defect rate; "split" for splitting across shops; else "none".
- question_type: "information" for questions about history or prices; "status" for progress questions; else "allocation".
- references_prior: the request_id of an earlier message this one continues, chosen only from the prior messages provided; else null.
- missing_fields: for allocation messages, which of order_id, pieces, due_date the message leaves unstated and that cannot be identified from an explicit order id.
- notes: short factual observations about ambiguity in the message, in English. Empty list if none.
"""


class LLMClient:
    """Calls Claude for extraction, enforces a spend cap, and falls back to rules on any failure."""

    def __init__(self, provider: Optional[str] = None, model: Optional[str] = None, budget_usd: Optional[float] = None):
        self.provider = (provider or os.getenv("DESK_LLM_PROVIDER", "none")).lower()
        self.model = model or os.getenv("DESK_LLM_MODEL", DEFAULT_MODEL)
        self.api_key = os.getenv("ANTHROPIC_API_KEY") or os.getenv("DESK_LLM_API_KEY", "")
        self.budget_usd = float(budget_usd if budget_usd is not None else os.getenv("DESK_LLM_BUDGET_USD", "5"))
        self.spent_usd = 0.0
        self.fallback = RuleBasedParser()
        self.calls: List[Dict] = []     # every call: request id, model, tokens, cost, outcome
        self._client = None

    def _anthropic(self):
        if self._client is None:
            try:
                import anthropic
            except ImportError as ex:
                raise RuntimeError("anthropic package not installed: pip install -r requirements.txt") from ex
            self._client = anthropic.Anthropic(api_key=self.api_key, max_retries=2, timeout=30.0)
        return self._client

    def complete(self, system: str, user: str, json_schema: Optional[dict] = None, max_tokens: int = 1024) -> str:
        """One Messages API call. Returns the text of the first text block. Raises RuntimeError on any problem."""
        if self.provider != "anthropic":
            raise RuntimeError(f"LLM provider is {self.provider!r}; set DESK_LLM_PROVIDER=anthropic to enable")
        if not self.api_key:
            raise RuntimeError("no API key: set ANTHROPIC_API_KEY")
        if self.spent_usd >= self.budget_usd:
            raise RuntimeError(f"budget of {self.budget_usd} USD exhausted (spent {self.spent_usd:.4f})")

        import anthropic
        client = self._anthropic()
        kwargs = dict(model=self.model, max_tokens=max_tokens, system=system,
                      messages=[{"role": "user", "content": user}])
        if json_schema is not None:
            kwargs["output_config"] = {"format": {"type": "json_schema", "schema": json_schema}}
        try:
            response = client.messages.create(**kwargs)
        except anthropic.AuthenticationError as ex:
            raise RuntimeError("invalid API key") from ex
        except anthropic.PermissionDeniedError as ex:
            raise RuntimeError("API key lacks permission for this model") from ex
        except anthropic.NotFoundError as ex:
            raise RuntimeError(f"model {self.model!r} not found") from ex
        except anthropic.RateLimitError as ex:
            raise RuntimeError("rate limited") from ex
        except anthropic.BadRequestError as ex:
            raise RuntimeError(f"bad request: {ex.message}") from ex
        except anthropic.APIStatusError as ex:
            raise RuntimeError(f"API error {ex.status_code}") from ex
        except anthropic.APIConnectionError as ex:
            raise RuntimeError("network error") from ex

        price_in, price_out = PRICING.get(self.model, PRICING[DEFAULT_MODEL])
        cost = (response.usage.input_tokens * price_in + response.usage.output_tokens * price_out) / 1_000_000
        self.spent_usd += cost
        self.calls.append({"model": self.model, "input_tokens": response.usage.input_tokens,
                           "output_tokens": response.usage.output_tokens, "cost_usd": round(cost, 6),
                           "stop_reason": response.stop_reason, "request_id": response._request_id})

        if response.stop_reason == "refusal":
            raise RuntimeError("model refused")
        if response.stop_reason == "max_tokens":
            raise RuntimeError("output truncated at max_tokens")
        text = next((b.text for b in response.content if b.type == "text"), None)
        if text is None:
            raise RuntimeError("no text in response")
        return text

    def parse_request(self, line: str, prior: Optional[List[Dict]] = None) -> Dict:
        """Returns a request dict per language/schema.md. Falls back to rules on any failure."""
        rid, ts, who, text = parse_header(line)
        context = [{"request_id": p.get("request_id"), "requester": p.get("requester"),
                    "order_id": p.get("order_id"), "order_ref_hint": p.get("order_ref_hint")}
                   for p in (prior or [])]
        user = (f"Prior messages this morning (for references_prior only):\n{json.dumps(context, ensure_ascii=False)}\n\n"
                f"Message {rid} at {ts} from {who}:\n{text}")
        try:
            data = json.loads(self.complete(SYSTEM_PROMPT, user, EXTRACTION_SCHEMA))
            r = empty_request()
            r.update(data)
            r.update(request_id=rid, timestamp=ts, requester=who, raw_text=text, parser=f"llm:{self.model}")
            if r["references_prior"] and r["references_prior"] not in {c["request_id"] for c in context}:
                r["notes"].append(f"dropped unknown reference {r['references_prior']}")
                r["references_prior"] = None
            return r
        except Exception as ex:           # noqa: BLE001 - any failure must degrade, never crash the desk
            self.calls.append({"request_id": rid, "outcome": f"fallback: {type(ex).__name__}: {ex}"})
            r = self.fallback.parse(line, prior)
            r["notes"].append(f"fallback: {ex}")
            return r


if __name__ == "__main__":
    import argparse
    from pathlib import Path

    ap = argparse.ArgumentParser(description="Parse the 30 official requests with rules (default) or Claude (--llm).")
    ap.add_argument("--llm", action="store_true", help="use Claude; needs DESK_LLM_PROVIDER=anthropic and ANTHROPIC_API_KEY")
    ap.add_argument("--limit", type=int, default=None, help="only parse the first N requests")
    args = ap.parse_args()

    src = Path(__file__).resolve().parent.parent / "data" / "dispatch_requests.txt"
    lines = [ln for ln in src.read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.startswith("#")]
    if args.limit:
        lines = lines[: args.limit]
    client = LLMClient() if args.llm else None
    rules = RuleBasedParser()
    prior: List[Dict] = []
    for line in lines:
        r = client.parse_request(line, prior) if client else rules.parse(line, prior)
        prior.append(r)
        print(json.dumps({k: r[k] for k in ("request_id", "parser", "order_id", "order_ref_hint", "customer", "product", "pieces",
                                            "due_date", "forced_workshop", "excluded_workshops", "constraint_scope", "preference",
                                            "question_type", "references_prior", "missing_fields", "notes")},
                         ensure_ascii=False))
    if client:
        n_ok = sum(1 for c in client.calls if "cost_usd" in c)
        print(f"\nLLM calls: {n_ok}  spent: ${client.spent_usd:.4f}  budget: ${client.budget_usd:.2f}  model: {client.model}")
