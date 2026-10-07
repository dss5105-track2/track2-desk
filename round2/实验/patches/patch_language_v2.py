"""Round-2 patch to llm/llm_client.py: prompt v2 and grounding. Kept for the record.

Designed from the GPT-5 nano errors on the official 30 only (03_语言层评估/基线_改进前/):
  * customer / product left null although the message names them
  * references_prior pointing at the previous message for no reason
  * a dispatch request read as a progress question ("get the TrendCart order moving")
  * a named workshop missed, or one invented from "somewhere good"
  * "sent out today" read as the due date

Two changes, both switchable so each can be measured on its own:
  prompt v2   sharper definitions and nine made-up examples (none taken from an evaluation inbox)
  grounding   code checks every extracted value against the message text: closed-vocabulary values
              that are literally there are filled in, values the text does not support are dropped.
              The model proposes; the text decides. Same principle as "the LLM does no arithmetic".
"""
import sys
from pathlib import Path

p = Path(sys.argv[1]) / "llm" / "llm_client.py"
s = p.read_text(encoding="utf-8")


def rep(a, b):
    global s
    assert s.count(a) == 1, (s.count(a), a[:70])
    s = s.replace(a, b)


rep('INSTRUCTIONS = f"""You extract structured fields', 'INSTRUCTIONS_V1 = f"""You extract structured fields')

rep('''class LLMClient:
    """Calls OpenAI for extraction, enforces a spend cap, and falls back to rules on any failure."""
''', r'''INSTRUCTIONS_V2 = f"""You extract structured fields from one message in a knitwear factory's dispatch group chat.
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

    if r.get("question_type") == "status" and DISPATCH_INTENT_RE.search(text):
        setv("question_type", "allocation", "the message asks for a dispatch")

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
    elif r.get("order_id"):
        missing = [m for m in missing if m == "due_date" and r.get("due_date") is None]
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
''')

rep('''    def __init__(self, provider: Optional[str] = None, model: Optional[str] = None, budget_usd: Optional[float] = None,
                 reasoning_effort: Optional[str] = None, max_output_tokens: int = 4000):''',
    '''    def __init__(self, provider: Optional[str] = None, model: Optional[str] = None, budget_usd: Optional[float] = None,
                 reasoning_effort: Optional[str] = None, max_output_tokens: int = 4000, prompt: str = "v2", grounding: bool = True):
        self.prompt = prompt                # "v1" (round 1) or "v2"; see PROMPTS
        self.grounding = grounding          # check every extracted value against the message text
        self.grounding_changes = 0          # how many values the code corrected, over all calls''')

rep('''            data = json.loads(self.complete(INSTRUCTIONS, user, EXTRACTION_SCHEMA))
            r = empty_request()
            r.update(data)
            r.update(request_id=rid, timestamp=ts, requester=who, raw_text=text, parser=f"llm:{self.model}")''',
    '''            data = json.loads(self.complete(PROMPTS[self.prompt], user, EXTRACTION_SCHEMA))
            r = empty_request()
            r.update(data)
            r.update(request_id=rid, timestamp=ts, requester=who, raw_text=text, parser=f"llm:{self.model}")
            if self.grounding:
                r = ground(r, text, prior)
                self.grounding_changes += len(r["grounding"])''')

rep('''        context = [{"request_id": p.get("request_id"), "requester": p.get("requester"),
                    "order_id": p.get("order_id"), "order_ref_hint": p.get("order_ref_hint")}
                   for p in (prior or [])]''',
    '''        context = [{"request_id": p.get("request_id"), "requester": p.get("requester"), "order_id": p.get("order_id"),
                    "order_ref_hint": p.get("order_ref_hint"), "customer": p.get("customer")}
                   for p in (prior or [])]''')

p.write_text(s, encoding="utf-8", newline="")
print("language v2 patched")
