"""One chat message, more than one order.

The parsers read one request from a message, so a second order used to vanish without a word. Here plain code cuts a
message at each order number before it is parsed. If the orders are only listed ("ORD-053, ORD-066 to BudgetWorks"),
everything else in the message is said of all of them. If each order is followed by its own words, those stay with it.
Patterns cannot read every way of writing this, so anything else is not applied at all: every order still gets a card,
the card shows the whole message and says to read it. A shop or date on the wrong order is worse than none.
"""
from __future__ import annotations

import re
from typing import List, Tuple

from desk.stop_reports import CLAUSE_RE
from llm.llm_client import DATE_DM_RE, DATE_RE, ORD_RE, PIECES_RE, WORKSHOP_NAMES, order_ids

# an order said to be at a workshop already, not one to send
HELD_RE = re.compile(r"\b(?:holds?|holding|held(?! up)|(?:stuck|sitting) (?:there|at|with)|was (?:making|doing|working on|running)"
                     r"|in (?:its|their) queue|(?:is|are|was|were)(?: all)? (?:there|in there|with them|at (?:it|[A-Z]\w+))|(?:it|they) (?:has|have|had)(?! to))\b", re.I)
# about orders, but not asking to send them all: "Don't send ...", "Send ORD-053, not ORD-066", "were already sent"
NOT_A_REQUEST_RE = re.compile(r"\b(?:don'?t|do not|hold|leave|wait|stop|pause|check|whether|cancel|sorry|i meant|instead|already|yet|did we|have we|(?:was|were) sent|not ORD)\b", re.I)
DISPATCH_WORD_RE = re.compile(r"\b(?:send\w*|giv\w+|put|place|ship\w*|dispatch\w*|allocat\w*|assign\w*|move[sd]?|book\w*|find|pick|choose"
                              r"|needs?\s+(?:a\s+|an\s+|to\s+)?(?:shop|workshop|go|leave|be sent|ship))\b", re.I)
ALSO_RE = re.compile(r"\b(?:and also|plus|as well as|along with|together with|and the)\b", re.I)
OTHER_TOPIC_RE = re.compile(r"\b(?:price|cost|quoted?|how much|invoice|payment|pay|paid|charged?|margin|revenue|status|how is|how's|how far)\b", re.I)
PCS_RE = re.compile(r"(?<![\w.-])\d[\d,]*\s*(?:pcs|pieces)\b", re.I)
# order numbers written in a way that cannot be read reliably: "ORD-053-066", "ORD-050 to ORD-053", "ORD-053, 066 and 120"
SUSPECT_IDS_RE = re.compile(r"\bORD-\d{1,3}\s*(?:-|\u2013|to\b|through\b|thru\b|,|and\b|&|/)\s*(?:ORD-)?(\d{1,3})\b", re.I)
_LINK_EDGE = r"(?:\s|,|;|:|/|&|\+|\.|\b(?:and|plus|also|both|then|first)\b)+"
# words that point at the order number after them: "GiantWeave for ORD-053", "BudgetWorks: ORD-053"
POINTS_AHEAD_RE = re.compile(r"(?:\b(?:for|to|on|of|with|at|from)|:)\s*$", re.I)
SAME_AS_LAST_RE = re.compile(r"^(?:too|ditto|as well|also|(?:the )?same)\W*$", re.I)
_EDGES_RE = re.compile(rf"^{_LINK_EDGE}|{_LINK_EDGE}$", re.I)
SAME_RE = re.compile(r"(?:[\s.,;]|\bthe\b)*(?:same\s+(?:for|goes\s+for|with)|likewise(?:\s+for)?|so\s+does|also\s+for)\s*$", re.I)
_MONTH_END_RE = re.compile(r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\.$")
CORRECTED_RE = re.compile(r"\b(?:was|not|instead of|rather than|from|previously|formerly|originally)\s+$", re.I)


def normalise_ids(text: str) -> str:
    """'ORD 66' and 'ORD066' are order numbers too."""
    return re.sub(r"\bORD[- ]?(\d{1,3})\b", lambda m: f"ORD-{int(m.group(1)):03d}", text, flags=re.I)


def suspect_ids(text: str, known_orders) -> bool:
    """A bare number beside an order number that is itself an order in the book, and is not a quantity."""
    for m in SUSPECT_IDS_RE.finditer(text):
        whole = "ORD-" in m.group(0)[4:].upper()
        if not whole and f"ORD-{int(m.group(1)):03d}" in known_orders and not PIECES_RE.match(text, m.start(1)) and not PCS_RE.match(text, m.start(1)):
            return True
        if re.search(r"\b(?:to|through|thru)\b", m.group(0), re.I):
            return True
    return False


def _has_pieces(text: str) -> bool:
    return bool(PIECES_RE.search(text) or PCS_RE.search(text))


def _has_date(text: str) -> bool:
    return bool(DATE_RE.search(text) or DATE_DM_RE.search(text))


def has_details(text: str) -> bool:
    return _has_pieces(text) or _has_date(text)


def _tidy(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"\b(?:due|by|before)\s*(?=[.,;!?]|$)", " ", text, flags=re.I)).strip()


def _without_pieces(text: str) -> str:
    return _tidy(PCS_RE.sub(" ", PIECES_RE.sub(" ", text)))


def _without_date(text: str) -> str:
    return _tidy(DATE_DM_RE.sub(" ", DATE_RE.sub(" ", text)))


def _sentences(text: str) -> List[str]:
    out: List[str] = []
    for piece in re.split(r"(?<=[.;!?])\s+", text.strip()):
        if out and _MONTH_END_RE.search(out[-1]):   # "due Apr. 12" is one sentence
            out[-1] += " " + piece
        elif piece:
            out.append(piece)
    return out


def take_held(text: str) -> Tuple[List[str], str]:
    """Orders a message says are held at a workshop, and the message without saying so."""
    held: List[str] = []
    rest: List[str] = []

    def is_held(part: str) -> bool:
        return bool(ORD_RE.search(part) and HELD_RE.search(part) and not DISPATCH_WORD_RE.search(part))

    for sentence in _sentences(text):
        if is_held(sentence):
            held += [o for o in order_ids(sentence) if o not in held]
            continue
        for clause in CLAUSE_RE.findall(sentence):
            if is_held(clause):
                held += [o for o in order_ids(clause) if o not in held]
            else:
                rest.append(clause)
        rest.append(" ")
    return held, re.sub(r"\s+", " ", "".join(rest)).strip()


def looks_like_dispatch(text: str, question_type: str) -> bool:
    """Worth one card per order? Not a question about them, and not a remark that a workshop has them."""
    if question_type != "allocation" or HELD_RE.search(text) or NOT_A_REQUEST_RE.search(text):
        return False
    return not text.rstrip().endswith("?") or bool(DISPATCH_WORD_RE.search(text))


def split_orders(text: str) -> Tuple[List[Tuple[str, str]], bool, List[str]]:
    """(order id, text) per order number; whether a quantity or date was dropped as unclear; further batches left unread."""
    text = re.sub(r"\s+/\s+", ", ", text.strip())
    text = re.sub(r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\.\s+(?=\d)", r"\1 ", text)     # "Apr. 28" is not two sentences
    marks = list(ORD_RE.finditer(text))
    words: dict = {}
    for i, m in enumerate(marks):
        oid = f"ORD-{int(m.group(1)):03d}"
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        words[oid] = f"{words.get(oid, '')} {text[m.end():end]}".strip()
    ids = list(words)
    raw_before = [text[:marks[0].start()]] + [words[o] for o in ids[:-1]]
    segs = [_EDGES_RE.sub("", words[o]) for o in ids]
    listed = not any(re.search(r"[A-Za-z0-9]", s) for s in segs[:-1])
    prefix = text[:marks[0].start()]
    same_said = any(SAME_RE.search(b) for b in raw_before)
    words_come_first = (any(n.lower() in prefix.lower() for n in WORKSHOP_NAMES) or has_details(prefix)  # "OldMill gets ORD-053 and ..."
                        or (not segs[-1] and not same_said)                                               # nothing follows the last number
                        or any(POINTS_AHEAD_RE.search(b) and not SAME_RE.search(b) for b in raw_before))  # "GiantWeave for ORD-053, ..."
    if not listed and words_come_first:
        return [(o, o) for o in ids], True, []
    for i in range(1, len(segs)):                   # "ORD-053 to BudgetWorks, ORD-066 too"
        if SAME_AS_LAST_RE.match(segs[i]):
            segs[i] = segs[i - 1]
    for i in range(len(segs) - 1):                  # "ORD-053 to BudgetWorks. Same for ORD-066."
        same = SAME_RE.search(segs[i])
        if same:
            segs[i] = _EDGES_RE.sub("", segs[i][:same.start()])
            segs[i + 1] = f"{segs[i]} {segs[i + 1]}".strip()
    shared = [_EDGES_RE.sub("", text[:marks[0].start()])]
    unclear = False
    if listed:                                      # only a list: the rest is said of all of them
        shared.append(segs[-1])
        segs = [""] * len(segs)
    else:
        last = _sentences(segs[-1]) or [""]
        segs[-1], later = last[0], last[1:]
        shared += later
        # words right after the last number are its own. A later clause with a quantity or date is too, if every other
        # order has its own; with neither it is said of them all: "ORD-053 rush, ORD-066 rush, both to BudgetWorks"
        clauses = CLAUSE_RE.findall(segs[-1]) or [""]
        own, tail = [clauses[0]], []
        for clause in clauses[1:]:
            if not has_details(clause):
                tail.append(clause)
            elif (not _has_pieces(clause) or all(_has_pieces(s) for s in segs[:-1])) and (not _has_date(clause) or all(_has_date(s) for s in segs[:-1])):
                own.append(clause)
            else:
                tail.append(_without_date(_without_pieces(clause)))
                unclear = True
        segs[-1] = "".join(own)
        shared.append("".join(tail))
    common = " ".join(s for s in shared if s)
    if has_details(common):
        common, unclear = _without_date(_without_pieces(common)), True
    common = _tidy(re.sub(r"\b(?:both|each|all)\b", " ", common, flags=re.I))
    extras = [b for s in segs for b in other_batches(s)[1:]]
    if any(PCS_RE.search(s) for s in segs):         # the parsers do not read "500 pcs"
        unclear = True
    return [(o, _tidy(f"{o} {s} {common}")) for o, s in zip(ids, segs)], unclear, extras


def other_batches(text: str) -> List[str]:
    """Quantities in a message, as written: '800 polo shirts'. A figure being corrected ('was 700 polo shirts') is not one."""
    found = list(PIECES_RE.finditer(text)) + [m for m in PCS_RE.finditer(text)]
    return [m.group(0) for m in sorted(found, key=lambda m: m.start()) if not CORRECTED_RE.search(text[:m.start()])]


def unhandled_question(text: str) -> str:
    """A question about something else, beside a request: the clause, or '' if there is none."""
    clauses = CLAUSE_RE.findall(text)
    for clause in clauses:
        if (clause.rstrip().endswith("?") or re.match(r"\s*what(?:'s| is)\b", clause, re.I)) and OTHER_TOPIC_RE.search(clause) \
                and any(ORD_RE.search(c) or PIECES_RE.search(c) for c in clauses if c is not clause):
            return clause.strip()
    return ""
