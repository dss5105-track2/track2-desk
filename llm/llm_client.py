"""LLM client (OpenAI GPT-5 mini by default, via the Responses API) + the rule-based fallback parser.

The language layer calls `LLMClient.parse_request()`. When the model is unavailable,
over budget, refuses, or returns something unusable, `RuleBasedParser` produces the same
schema (language/schema.md) from regexes, so the desk never depends on the network.

The LLM only *extracts* fields from chat text. It never does arithmetic, never looks up
queues, and never chooses a workshop - those come from kernel/.

Configuration comes from environment variables (or a local, git-ignored `.env` file):
    DESK_LLM_PROVIDER          openai | none      (default none -> rules only)
    DESK_LLM_MODEL             model id           (default gpt-5-mini; gpt-5-nano is about 4x cheaper)
    OPENAI_API_KEY             key from platform.openai.com (DESK_LLM_API_KEY also accepted)
    DESK_LLM_BUDGET_USD        hard stop for one Python process (default 2)
    DESK_LLM_REASONING_EFFORT  reasoning effort sent to the model (default low; empty = omit)
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

LINE_RE = re.compile(r"^([A-Z]\d+)\s+\[(\d\d:\d\d)\]\s+([A-Za-z]+):\s*(.*)$")
ORD_RE = re.compile(r"\bORD-\d{3}\b")
DATE_RE = re.compile(r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+(\d{1,2})(?:st|nd|rd|th)?\b", re.I)
DATE_DM_RE = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\b", re.I)
PIECES_RE = re.compile(r"(?<![\w.-])(\d[\d,]*(?:\.\d+)?k?)\s+(polo shirts?|crewneck sweaters?|vests?|hoodies?|polos?|crewnecks?|cardigans?|scarves|scarf|beanies?)\b", re.I)
EXCLUDE_PATTERNS = [r"keep it away from\s+([A-Za-z &]+)", r"nothing new to\s+([A-Za-z &]+)", r"not\s+([A-Za-z &]+?)\b", r"avoid\s+([A-Za-z &]+)",
                    r"(?:anyone|anybody|anywhere) but\s+([A-Za-z &]+)", r"don'?t (?:send|give|use)\s+([A-Za-z &]+)",
                    r"([A-Za-z]+(?: [A-Z][a-z]+)?)'s [^.]*?don'?t send them"]

# USD per million tokens (input, output), OpenAI standard tier, checked 2026-09-13 at
# developers.openai.com/api/docs/pricing. Reasoning tokens are billed as output tokens.
PRICING: Dict[str, Tuple[float, float]] = {
    "gpt-5-nano": (0.05, 0.40),
    "gpt-5-mini": (0.25, 2.00),
    "gpt-5": (1.25, 10.00),
}
DEFAULT_MODEL = "gpt-5-mini"          # team decision 2026-10-07; see docs/round2_changes.md


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
            raw = pm.group(1).replace(",", "").lower()
            r["pieces"] = int(round(float(raw[:-1]) * 1000)) if raw.endswith("k") else int(float(raw))

        dm, dd = DATE_RE.search(text), DATE_DM_RE.search(text)
        if dm or dd:
            mon, day = (dm.group(1), dm.group(2)) if dm else (dd.group(2), dd.group(1))
            try:
                r["due_date"] = date(self.year, MONTHS[mon.lower()[:3]], int(day)).isoformat()
            except ValueError:
                pass

        # workshops: exclusions first, everything else mentioned is a suggestion
        excluded = set()
        for pat in EXCLUDE_PATTERNS:
            for em in re.finditer(pat, text, re.I):
                for name, wid in WORKSHOP_NAMES.items():
                    if name.lower() in em.group(1).lower():
                        excluded.add(wid)
        mentioned = [wid for name, wid in WORKSHOP_NAMES.items() if name.lower() in low]
        r["excluded_workshops"] = sorted(excluded)
        if excluded and re.search(r"this week|until further notice|for now|anymore|from now on", low):
            r["constraint_scope"] = "session"
        forced = [wid for wid in mentioned if wid not in excluded]
        r["forced_workshop"] = forced[0] if forced else None

        if re.search(r"fastest|quickest|asap|as soon as|as fast as", low):
            r["preference"] = "fastest"
        elif "cheapest" in low or "margin is thin" in low:
            r["preference"] = "cheapest_on_time"
        elif re.search(r"lowest defect|fewest defect|defect rate|rejected a batch|quality", low):
            r["preference"] = "lowest_defect"
        elif "split" in low:
            r["preference"] = "split"

        # history / price questions only; "rejected a batch last month" is context, not a question
        if re.search(r"\bwhich workshop did we use\b|\bwhat price\b|\bdid we quote\b|\bwho made\b.*\blast\b|^how many\b|^who (is|was)\b|"
                     r"\bwhat did\b.*\bpay\b|\b(our|the) margin\b|\blast (quarter|year|month)\b.*\?", low):
            r["question_type"] = "information"
        if re.search(r"any movement|any news|how is|how far along|status", low) and not r["pieces"]:
            r["question_type"] = "status"
        if r["question_type"] != "allocation":
            r["forced_workshop"], r["excluded_workshops"], r["preference"] = None, [], "none"

        # cross-message references
        if prior:
            # a follow-up names the same customer as the sender's earlier message ("the Loom & Leaf stuff" -> R10);
            # "details to follow" points forward, and "that big reorder" names an order, not a message
            explicit = re.search(r"from this morning|earlier today|as mentioned", low)     # says outright that it continues something
            if not r["order_id"] and r["customer"] and (explicit or re.search(r"\bthat (big |last )?(re)?order\b|\bthe (big )?reorder\b|\bstuff\b", low)):
                same = [p for p in prior if (explicit or p.get("requester") == r["requester"]) and p.get("customer") == r["customer"]
                        and not p.get("order_id")]
                if same:
                    r["references_prior"] = same[-1]["request_id"]
            for p in prior:
                if r["order_id"] and p.get("order_id") == r["order_id"] and p.get("question_type") == "allocation":
                    r["notes"].append(f"same order as {p['request_id']}")
                    if r["question_type"] == "allocation":
                        r["references_prior"] = p["request_id"]

        # schema.md: missing = needed for dispatch and not obtainable from the text or from an explicit order id
        missing = []
        if r["question_type"] == "allocation":
            if not r["order_id"]:
                missing.append("order_id")
                # pieces and date come from the order book once the order is identified; they are missing too
                # only when the work is not an existing order, or the message leaves them undefined
                ref = next((p for p in (prior or []) if p.get("request_id") == r["references_prior"]), None)
                undefined = (re.search(r"new rush|details to follow|coming in from|usual quantit|numbers? not final|new customer|a few hundred|"
                                       r"to be confirmed|waiting on quantit|repeat order", low)
)
                if undefined:
                    if r["pieces"] is None:
                        missing.append("pieces")
                    if r["due_date"] is None:
                        missing.append("due_date")
            elif r["due_date"] is None and re.search(r"will confirm|moved up|new date|to be confirmed|\btbc\b|haven'?t said when|sooner than planned", low):
                missing.append("due_date")
        r["missing_fields"] = missing
        return r


# ---------------------------------------------------------------------------------------
# LLM extraction
# ---------------------------------------------------------------------------------------

def _nullable(type_name: str, enum: Optional[List] = None) -> dict:
    """OpenAI strict mode: nullable via a type array; an enum must then also list null."""
    d: dict = {"type": [type_name, "null"]}
    if enum is not None:
        d["enum"] = list(enum) + [None]
    return d


EXTRACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "question_type": {"type": "string", "enum": ["allocation", "status", "information"]},
        "order_id": _nullable("string"),
        "order_ref_hint": _nullable("string"),
        "customer": _nullable("string", CUSTOMERS),
        "product": _nullable("string", PRODUCTS),
        "category": _nullable("string", ["TOPS", "ACCESSORIES"]),
        "pieces": _nullable("integer"),
        "due_date": _nullable("string"),
        "forced_workshop": _nullable("string", list(WORKSHOP_NAMES.values())),
        "excluded_workshops": {"type": "array", "items": {"type": "string", "enum": list(WORKSHOP_NAMES.values())}},
        "constraint_scope": {"type": "string", "enum": ["request", "session"]},
        "preference": {"type": "string", "enum": ["none", "fastest", "cheapest_on_time", "lowest_defect", "split"]},
        "references_prior": _nullable("string"),
        "missing_fields": {"type": "array", "items": {"type": "string", "enum": ["order_id", "pieces", "due_date"]}},
        "notes": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["question_type", "order_id", "order_ref_hint", "customer", "product", "category", "pieces", "due_date",
                 "forced_workshop", "excluded_workshops", "constraint_scope", "preference", "references_prior",
                 "missing_fields", "notes"],
    "additionalProperties": False,
}

INSTRUCTIONS_V1 = f"""You extract structured fields from one message in a knitwear factory's dispatch group chat.
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
- missing_fields: for allocation messages only. If the message names an order id, it is empty unless the message itself says a value is still to come ("will confirm the new date" -> ["due_date"]). If it points at an existing order without its id ("the TrendCart order", "that big reorder", "the vests"), it is ["order_id"] only: pieces and due date are in the order book. If it is about work that is not an existing order, or leaves the quantity or date undefined ("new rush, details to follow", "usual quantities"), list order_id and also pieces and due_date when they are unstated.
- notes: short factual observations about ambiguity in the message, in English. Empty list if none.
"""


INSTRUCTIONS_V2 = f"""You extract structured fields from one message in a knitwear factory's dispatch group chat.
Today is {TODAY}. Dates without a year are in 2026.

Your only job is extraction. Do not look anything up, do not calculate, do not recommend a workshop.
Copy what the message says; when it does not state a field, return null. Never fill a field from a guess.

Fields
- order_id: an explicit ORD-xxx in the message, else null. If the message points at an order without its id
  ("the TrendCart order", "that big reorder"), put that phrase in order_ref_hint.
- customer: one of {json.dumps(CUSTOMERS)} when the message names it; else null.
- product: one of {json.dumps(PRODUCTS)} when the message names it (singular or plural); category follows from it.
- pieces: the quantity, only when stated as a number.
- due_date: the date the batch must be back (ISO yyyy-mm-dd). "back by", "ship date", "deadline", "due", "make <date>",
  "needed <date>" all mean due_date. "Send it out today" or "has to go out today" is when it leaves, NOT a due date.
- forced_workshop: a workshop the sender proposes, asks about or tells you to use for this batch ("to X", "with X",
  "X for ORD-...?", "give X ..."). Only a workshop named in the message. Ids: {json.dumps(WORKSHOP_NAMES)}.
- excluded_workshops: workshops the sender rules out ("keep it away from", "not X", "nothing new to X", "anyone but X").
  A workshop is never both forced and excluded.
- constraint_scope: "session" only when the exclusion is meant to last beyond this order ("this week", "until further
  notice"); otherwise "request".
- preference: "fastest" (fastest, quickest, asap, as fast as you can); "cheapest_on_time" (cheapest that still makes the
  date, tight margin or budget); "lowest_defect" (quality, fewest or lowest defects); "split" (split across shops); else "none".
- question_type:
    "allocation"  the sender wants a batch sent out, placed, moved, booked or lined up. This is the default, also when it is
                  phrased as a question or mentions that the customer is chasing.
    "status"      the sender only asks how an order is progressing and does not ask for it to be dispatched.
    "information" the sender asks about history, prices, money or people, not about dispatching a batch.
- references_prior: almost always null. Give an earlier request_id (only from the list provided) in two cases only:
  the message names the same order id as that earlier message, or it names no order and plainly continues that earlier
  message's topic ("the Loom & Leaf stuff" after "new rush from Loom & Leaf, details to follow").
- missing_fields: for allocation messages only. If the message names an order id it is empty, unless the message itself
  says a value is still to come ("will confirm the new date" -> ["due_date"]). If it points at an existing order without
  its id, it is ["order_id"] only. If it is about work that is not an order yet, or leaves the quantity or date undefined
  ("details to follow", "usual quantities"), list order_id and also pieces and due_date when unstated.
- notes: short factual observations about ambiguity, in English. Empty list if none.

Examples (made up; the values shown are the ones that matter)
1. "ORD-214 — 700 vests for Maple & Co, due May 06."
   -> order_id ORD-214, customer Maple & Co, product Vest, pieces 700, due_date 2026-05-06, allocation, missing []
2. "Can we get the Maple & Co order out the door? They keep calling."
   -> allocation (they want it dispatched), customer Maple & Co, order_ref_hint "the Maple & Co order", missing ["order_id"]
3. "How far along is ORD-311?"                               -> status, order_id ORD-311
4. "Did SteadyHands ever make polos for us before?"          -> information, forced_workshop null
5. "Try Nimble Needle for ORD-402?"                           -> allocation, order_id ORD-402, forced_workshop W6
6. "ORD-150, 400 scarves, due Apr 30 — not Little Loom this time."
   -> excluded_workshops ["W4"], constraint_scope request, forced_workshop null
7. "ORD-277 needs to leave today, 900 cardigans, back by May 2." -> due_date 2026-05-02 (not today), pieces 900
8. "New batch from UrbanThread coming, numbers later — reserve something."
   -> allocation, customer UrbanThread, order_id null, missing ["order_id", "pieces", "due_date"], references_prior null
9. "ORD-390: date is being pulled forward, will let you know. Find a shop meanwhile."
   -> allocation, order_id ORD-390, due_date null, missing ["due_date"]
"""

PROMPTS = {"v1": INSTRUCTIONS_V1, "v2": INSTRUCTIONS_V2}
INSTRUCTIONS = INSTRUCTIONS_V2

DISPATCH_INTENT_RE = re.compile(
    r"\b(send|sent out|sending|go(es)? out|goes? outside|farm out|dispatch|place|placed|allocate|book|line (something|it) up|"
    r"get\b.*\bmoving|needs? a (home|shop|workshop)|ready to dispatch|has to go out)\b", re.I)
DATE_PENDING_RE = re.compile(r"will confirm|moved up|new date|to be confirmed|\btbc\b", re.I)
GROUNDING_VERSION = "2.2"
TIMING_TALK_RE = re.compile(r"\b(date|due|deadline|when|sooner|earlier|later|moved|postpon\w*|delay\w*|confirm\w*|tbc)\b", re.I)
SESSION_SCOPE_RE = re.compile(r"this week|until further notice|for now|anymore", re.I)
PREFERENCE_KEYWORDS = [("fastest", r"fastest|quickest|asap|as soon as"), ("cheapest_on_time", r"cheapest|margin is thin"),
                       ("lowest_defect", r"lowest defect|defect rate|rejected a batch|quality"), ("split", r"\bsplit\b")]
PLAIN_DATE_RE = re.compile(r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{1,2})\b", re.I)
NUM_TOKEN_RE = re.compile(r"(?<![\w.-])(\d[\d,]*(?:\.\d+)?)(k)?\b", re.I)


def _numbers_in(text: str) -> set:
    out = set()
    for num, k in NUM_TOKEN_RE.findall(text):
        try:
            v = float(num.replace(",", ""))
        except ValueError:
            continue
        out.add(int(round(v * 1000)) if k else int(v) if v == int(v) else v)
    return out


def ground(r: Dict, text: str, prior: Optional[List[Dict]] = None) -> Dict:
    """Check an extracted request against the message it came from.

    Closed-vocabulary values that are literally in the text are filled in; values the text does not support are dropped.
    Nothing is looked up and nothing is inferred beyond the message. Every change is recorded in r["grounding"]."""
    low = text.lower()
    changes: List[str] = []

    def setv(field, value, why):
        if r.get(field) != value:
            changes.append(f"{field}: {r.get(field)!r} -> {value!r} ({why})")
            r[field] = value

    ids = ORD_RE.findall(text)
    setv("order_id", ids[0] if ids else None, "order ids are read from the text")
    if r.get("question_type") == "status" and DISPATCH_INTENT_RE.search(text):
        setv("question_type", "allocation", "the message asks for a dispatch")

    customers = [c for c in CUSTOMERS if c.lower() in low]
    if len(customers) == 1:
        setv("customer", customers[0], "named in the text")
    elif r.get("customer") not in customers:
        setv("customer", None, "not named in the text")

    products = []
    for word, (prod, _cat) in PRODUCT_WORDS.items():
        if re.search(r"\b" + re.escape(word) + r"\b", low) and prod not in products:
            products.append(prod)
    if len(products) == 1:
        setv("product", products[0], "named in the text")
    elif r.get("product") not in products:
        setv("product", None, "not named in the text")
    r["category"] = next((cat for _w, (prod, cat) in PRODUCT_WORDS.items() if prod == r.get("product")), None)

    mentioned = [wid for name, wid in WORKSHOP_NAMES.items() if name.lower() in low]
    excluded = [w for w in (r.get("excluded_workshops") or []) if w in mentioned]
    if sorted(excluded) != sorted(r.get("excluded_workshops") or []):
        changes.append(f"excluded_workshops: {r.get('excluded_workshops')!r} -> {excluded!r} (only workshops named in the text)")
    r["excluded_workshops"] = sorted(excluded)
    forced = r.get("forced_workshop")
    if forced is not None and (forced not in mentioned or forced in excluded):
        setv("forced_workshop", None, "not named in the text" if forced not in mentioned else "it is excluded")
    for wid in mentioned:                       # a workshop the message names must end up somewhere
        if wid != r.get("forced_workshop") and wid not in r["excluded_workshops"]:
            name = next(n for n, w in WORKSHOP_NAMES.items() if w == wid).lower()
            ruled_out = any(name in m.group(1).lower() for pat in EXCLUDE_PATTERNS for m in re.finditer(pat, text, re.I))
            if ruled_out:
                r["excluded_workshops"] = sorted(set(r["excluded_workshops"]) | {wid})
                changes.append(f"excluded_workshops: + {wid} (named after an exclusion phrase)")
            elif r.get("forced_workshop") is None and r.get("question_type") == "allocation":
                setv("forced_workshop", wid, "named in the text")
    if not r["excluded_workshops"]:
        setv("constraint_scope", "request", "no exclusion")
    elif SESSION_SCOPE_RE.search(text):
        setv("constraint_scope", "session", "the message says the exclusion lasts beyond this order")

    if (r.get("preference") or "none") == "none" and r.get("question_type") == "allocation":
        for pref, pat in PREFERENCE_KEYWORDS:
            if re.search(pat, low):
                setv("preference", pref, "stated in the text")
                break

    if r.get("pieces") is not None and r["pieces"] not in _numbers_in(text):
        setv("pieces", None, "that number is not in the text")

    if r.get("due_date"):
        ok = False
        try:
            d = date.fromisoformat(r["due_date"])
            months = {MONTHS[m.lower()[:3]] for m in re.findall(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\b", low)}
            days = {int(x) for x in re.findall(r"(?<![\w-])(\d{1,2})(?:st|nd|rd|th)?\b", low)}
            ok = d.day in days and (not months or d.month in months)
        except ValueError:
            pass
        if not ok:
            setv("due_date", None, "no such date in the text")
    if not r.get("due_date") and r.get("question_type") == "allocation" and not DATE_PENDING_RE.search(text):
        plain = {(m.group(1).lower()[:3], int(m.group(2))) for m in PLAIN_DATE_RE.finditer(text)}
        if len(plain) == 1:
            mon, day = next(iter(plain))
            try:
                setv("due_date", date(int(TODAY[:4]), MONTHS[mon], day).isoformat(), "the only date in the text")
            except ValueError:
                pass

    known = {p.get("request_id"): p for p in (prior or [])}
    same_order = [p for p in (prior or []) if r.get("order_id") and p.get("order_id") == r["order_id"] and p.get("question_type") == "allocation"]
    if same_order and r.get("question_type") == "allocation":
        setv("references_prior", same_order[-1]["request_id"], "same order id as an earlier message")
    elif r.get("references_prior") and (r.get("order_id") or r["references_prior"] not in known):
        setv("references_prior", None, "a message that names its own order does not continue another one")
    elif r.get("references_prior"):
        ref = known[r["references_prior"]]
        if not (r.get("customer") and ref.get("customer") == r["customer"]):
            setv("references_prior", None, "the earlier message is about something else")

    missing = [m for m in (r.get("missing_fields") or []) if m in ("order_id", "pieces", "due_date")]
    if r.get("order_id") and not r.get("due_date") and DATE_PENDING_RE.search(text) and "due_date" not in missing:
        missing.append("due_date")           # the message itself says the date is still to come
    if r.get("question_type") != "allocation":
        missing = []
    elif r.get("order_id"):                  # the order book has the date unless the message says the date itself is in question
        missing = [m for m in missing if m == "due_date" and r.get("due_date") is None and TIMING_TALK_RE.search(text)]
    else:
        if "order_id" not in missing:
            missing.insert(0, "order_id")
        missing = [m for m in missing if not (m == "pieces" and r.get("pieces") is not None) and not (m == "due_date" and r.get("due_date"))]
    order = {"order_id": 0, "pieces": 1, "due_date": 2}
    missing = sorted(set(missing), key=order.get)
    if missing != (r.get("missing_fields") or []):
        changes.append(f"missing_fields: {r.get('missing_fields')!r} -> {missing!r} (made consistent with the other fields)")
    r["missing_fields"] = missing

    r["grounding"] = changes
    return r


class LLMClient:
    """Calls OpenAI for extraction, enforces a spend cap, and falls back to rules on any failure."""

    def __init__(self, provider: Optional[str] = None, model: Optional[str] = None, budget_usd: Optional[float] = None,
                 reasoning_effort: Optional[str] = None, max_output_tokens: int = 4000, prompt: str = "v2", grounding: bool = True):
        self.prompt = prompt                # "v1" (round 1) or "v2"; see PROMPTS
        self.grounding = grounding          # check every extracted value against the message text
        self.grounding_changes = 0          # how many values the code corrected, over all calls
        self.provider = (provider or os.getenv("DESK_LLM_PROVIDER", "none")).lower()
        self.model = model or os.getenv("DESK_LLM_MODEL", DEFAULT_MODEL)
        self.api_key = os.getenv("OPENAI_API_KEY") or os.getenv("DESK_LLM_API_KEY", "")
        self.budget_usd = float(budget_usd if budget_usd is not None else os.getenv("DESK_LLM_BUDGET_USD", "2"))
        effort = reasoning_effort if reasoning_effort is not None else os.getenv("DESK_LLM_REASONING_EFFORT", "low")
        self.reasoning_effort = effort or None
        self.max_output_tokens = max_output_tokens    # reasoning tokens count against this, so keep headroom
        self.spent_usd = 0.0
        self.fallback = RuleBasedParser()
        self.calls: List[Dict] = []     # every call: request id, model, tokens, cost, outcome
        self._client = None

    def _openai(self):
        if self._client is None:
            try:
                from openai import OpenAI
            except ImportError as ex:
                raise RuntimeError("openai package not installed: pip install -r requirements.txt") from ex
            self._client = OpenAI(api_key=self.api_key, max_retries=2, timeout=60.0)
        return self._client

    def complete(self, instructions: str, user: str, json_schema: Optional[dict] = None,
                 schema_name: str = "request_fields") -> str:
        """One Responses API call. Returns the output text. Raises RuntimeError on any problem."""
        if self.provider != "openai":
            raise RuntimeError(f"LLM provider is {self.provider!r}; set DESK_LLM_PROVIDER=openai to enable")
        if not self.api_key:
            raise RuntimeError("no API key: set OPENAI_API_KEY")
        if self.spent_usd >= self.budget_usd:
            raise RuntimeError(f"budget of {self.budget_usd} USD exhausted (spent {self.spent_usd:.4f})")

        import openai
        client = self._openai()
        kwargs = dict(model=self.model, instructions=instructions, input=user, max_output_tokens=self.max_output_tokens)
        if self.reasoning_effort:
            kwargs["reasoning"] = {"effort": self.reasoning_effort}
        if json_schema is not None:
            kwargs["text"] = {"format": {"type": "json_schema", "name": schema_name, "schema": json_schema, "strict": True}}
        try:
            response = client.responses.create(**kwargs)
        except openai.AuthenticationError as ex:
            raise RuntimeError("invalid API key") from ex
        except openai.PermissionDeniedError as ex:
            raise RuntimeError("API key lacks permission for this model") from ex
        except openai.NotFoundError as ex:
            raise RuntimeError(f"model {self.model!r} not found") from ex
        except openai.RateLimitError as ex:
            raise RuntimeError("rate limited or out of credit") from ex
        except openai.BadRequestError as ex:
            raise RuntimeError(f"bad request: {ex.message}") from ex
        except openai.APITimeoutError as ex:
            raise RuntimeError("request timed out") from ex
        except openai.APIConnectionError as ex:
            raise RuntimeError("network error") from ex
        except openai.APIStatusError as ex:
            raise RuntimeError(f"API error {ex.status_code}") from ex

        usage = getattr(response, "usage", None)
        in_tok = getattr(usage, "input_tokens", 0) or 0
        out_tok = getattr(usage, "output_tokens", 0) or 0
        price_in, price_out = PRICING.get(self.model, PRICING[DEFAULT_MODEL])
        cost = (in_tok * price_in + out_tok * price_out) / 1_000_000
        self.spent_usd += cost
        self.calls.append({"model": self.model, "input_tokens": in_tok, "output_tokens": out_tok,
                           "cost_usd": round(cost, 6), "status": getattr(response, "status", None),
                           "request_id": getattr(response, "_request_id", None)})

        if getattr(response, "status", None) == "incomplete":
            reason = getattr(getattr(response, "incomplete_details", None), "reason", "unknown")
            raise RuntimeError(f"incomplete response: {reason}")
        for item in getattr(response, "output", None) or []:
            if getattr(item, "type", None) == "message":
                for part in getattr(item, "content", None) or []:
                    if getattr(part, "type", None) == "refusal":
                        raise RuntimeError(f"model refused: {getattr(part, 'refusal', '')}")
        text = getattr(response, "output_text", "") or ""
        if not text.strip():
            raise RuntimeError("empty output")
        return text

    def parse_request(self, line: str, prior: Optional[List[Dict]] = None) -> Dict:
        """Returns a request dict per language/schema.md. Falls back to rules on any failure."""
        rid, ts, who, text = parse_header(line)
        context = [{"request_id": p.get("request_id"), "requester": p.get("requester"), "order_id": p.get("order_id"),
                    "order_ref_hint": p.get("order_ref_hint"), "customer": p.get("customer")}
                   for p in (prior or [])]
        user = (f"Prior messages this morning (for references_prior only):\n{json.dumps(context, ensure_ascii=False)}\n\n"
                f"Message {rid} at {ts} from {who}:\n{text}")
        try:
            data = json.loads(self.complete(PROMPTS[self.prompt], user, EXTRACTION_SCHEMA))
            r = empty_request()
            r.update(data)
            r.update(request_id=rid, timestamp=ts, requester=who, raw_text=text, parser=f"llm:{self.model}")
            if self.grounding:
                r = ground(r, text, prior)
                self.grounding_changes += len(r["grounding"])
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

    ap = argparse.ArgumentParser(description="Parse the 30 official requests with rules (default) or the LLM (--llm, default GPT-5 mini).")
    ap.add_argument("--llm", action="store_true", help="use OpenAI; needs DESK_LLM_PROVIDER=openai and OPENAI_API_KEY")
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
        ok = [c for c in client.calls if "cost_usd" in c]
        fb = [c for c in client.calls if "outcome" in c]
        print(f"\nLLM calls: {len(ok)}  fallbacks: {len(fb)}  spent: ${client.spent_usd:.4f}  "
              f"budget: ${client.budget_usd:.2f}  model: {client.model}")
        for c in fb[:3]:
            print("  ", c["outcome"])
