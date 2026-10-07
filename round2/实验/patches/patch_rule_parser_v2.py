"""Round-2 patch to the rule parser (the offline fallback), after it was run on the challenge inbox.

Honesty note: these fixes were written AFTER seeing the rule parser's errors on the challenge inbox, so
its score there after this patch is not a clean test. The clean numbers are its first run
(03_语言层评估/基线_改进前/) and, later, the teammates' hand-written held-out set.

  dates        "26 Apr", "April 29", "Apr 3rd" as well as "Apr 26"
  quantities   "1.2k hoodies" as well as "1,200 hoodies"
  exclusions   "anyone but X", "don't send X / them anything" as well as "keep it away from X"
  preference   "as fast as you can", "fewest defects"
  questions    "how many ...", "who is ...", "what did ... pay", "margin" are information, "any news" is status
  pending      "haven't said when", "date to be confirmed", "numbers not final", "a few hundred"
"""
import sys
from pathlib import Path

p = Path(sys.argv[1]) / "llm" / "llm_client.py"
s = p.read_text(encoding="utf-8")


def rep(a, b):
    global s
    assert s.count(a) == 1, (s.count(a), a[:70])
    s = s.replace(a, b)


rep(r'''DATE_RE = re.compile(r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{1,2})\b", re.I)''',
    r'''DATE_RE = re.compile(r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+(\d{1,2})(?:st|nd|rd|th)?\b", re.I)
DATE_DM_RE = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\b", re.I)''')

rep(r'''PIECES_RE = re.compile(r"\b(\d[\d,]*)\s+(polo shirts?''', r'''PIECES_RE = re.compile(r"(?<![\w.-])(\d[\d,]*(?:\.\d+)?k?)\s+(polo shirts?''')

rep(r'''EXCLUDE_PATTERNS = [r"keep it away from\s+([A-Za-z &]+)", r"nothing new to\s+([A-Za-z &]+)", r"not\s+([A-Za-z &]+?)\b", r"avoid\s+([A-Za-z &]+)"]''',
    r'''EXCLUDE_PATTERNS = [r"keep it away from\s+([A-Za-z &]+)", r"nothing new to\s+([A-Za-z &]+)", r"not\s+([A-Za-z &]+?)\b", r"avoid\s+([A-Za-z &]+)",
                    r"(?:anyone|anybody|anywhere) but\s+([A-Za-z &]+)", r"don'?t (?:send|give|use)\s+([A-Za-z &]+)",
                    r"([A-Za-z]+(?: [A-Z][a-z]+)?)'s [^.]*?don'?t send them"]''')

rep('''        pm = PIECES_RE.search(text)
        if pm:
            r["pieces"] = int(pm.group(1).replace(",", ""))

        dm = DATE_RE.search(text)
        if dm:
            r["due_date"] = date(self.year, MONTHS[dm.group(1).lower()[:3]], int(dm.group(2))).isoformat()''',
    '''        pm = PIECES_RE.search(text)
        if pm:
            raw = pm.group(1).replace(",", "").lower()
            r["pieces"] = int(round(float(raw[:-1]) * 1000)) if raw.endswith("k") else int(float(raw))

        dm, dd = DATE_RE.search(text), DATE_DM_RE.search(text)
        if dm or dd:
            mon, day = (dm.group(1), dm.group(2)) if dm else (dd.group(2), dd.group(1))
            try:
                r["due_date"] = date(self.year, MONTHS[mon.lower()[:3]], int(day)).isoformat()
            except ValueError:
                pass''')

rep('''        if excluded and re.search(r"this week|until further notice|for now|anymore", low):''',
    '''        if excluded and re.search(r"this week|until further notice|for now|anymore|from now on", low):''')

rep('''        if re.search(r"fastest|quickest|asap|as soon as", low):
            r["preference"] = "fastest"
        elif "cheapest" in low or "margin is thin" in low:
            r["preference"] = "cheapest_on_time"
        elif re.search(r"lowest defect|defect rate|rejected a batch|quality", low):''',
    '''        if re.search(r"fastest|quickest|asap|as soon as|as fast as", low):
            r["preference"] = "fastest"
        elif "cheapest" in low or "margin is thin" in low:
            r["preference"] = "cheapest_on_time"
        elif re.search(r"lowest defect|fewest defect|defect rate|rejected a batch|quality", low):''')

rep('''        if re.search(r"\\bwhich workshop did we use\\b|\\bwhat price\\b|\\bdid we quote\\b|\\bwho made\\b.*\\blast\\b", low):
            r["question_type"] = "information"
        if re.search(r"any movement|how is|status", low) and not r["pieces"]:
            r["question_type"] = "status"''',
    '''        if re.search(r"\\bwhich workshop did we use\\b|\\bwhat price\\b|\\bdid we quote\\b|\\bwho made\\b.*\\blast\\b|^how many\\b|^who (is|was)\\b|"
                     r"\\bwhat did\\b.*\\bpay\\b|\\b(our|the) margin\\b|\\blast (quarter|year|month)\\b.*\\?", low):
            r["question_type"] = "information"
        if re.search(r"any movement|any news|how is|how far along|status", low) and not r["pieces"]:
            r["question_type"] = "status"
        if r["question_type"] != "allocation":
            r["forced_workshop"], r["excluded_workshops"], r["preference"] = None, [], "none"''')

rep('''            elif r["due_date"] is None and re.search(r"will confirm|moved up|new date|to be confirmed|\\btbc\\b", low):
                missing.append("due_date")''',
    '''            elif r["due_date"] is None and re.search(r"will confirm|moved up|new date|to be confirmed|\\btbc\\b|haven'?t said when|sooner than planned", low):
                missing.append("due_date")''')

rep('''                undefined = re.search(r"new rush|details to follow|coming in from|usual quantit", low) or (ref and "pieces" in ref.get("missing_fields", []))''',
    '''                undefined = (re.search(r"new rush|details to follow|coming in from|usual quantit|numbers? not final|new customer|a few hundred|"
                                       r"to be confirmed|waiting on quantit|repeat order", low)
                             or (ref and "pieces" in ref.get("missing_fields", [])))''')

rep(r'''            if not r["order_id"] and r["customer"] and re.search(r"\bthat (big |last )?(re)?order\b|\bthe (big )?reorder\b|\bstuff\b", low):
                same = [p for p in prior if p.get("requester") == r["requester"] and p.get("customer") == r["customer"]]''',
    r'''            explicit = re.search(r"from this morning|earlier today|as mentioned", low)     # says outright that it continues something
            if not r["order_id"] and r["customer"] and (explicit or re.search(r"\bthat (big |last )?(re)?order\b|\bthe (big )?reorder\b|\bstuff\b", low)):
                same = [p for p in prior if (explicit or p.get("requester") == r["requester"]) and p.get("customer") == r["customer"]
                        and not p.get("order_id")]''')

p.write_text(s, encoding="utf-8", newline="")
print("rule parser v2 patched")
