"""Does a chat message say a workshop has stopped?

Plain patterns, not the model, so the result is the same on every run. A match never acts by itself: a person
confirms it first. The clause that says so is taken out before the message is parsed, so a date in it ("shut until
May 30") is not read as a due date and a workshop named in it is not read as the one asked for. Misreading a
dispatch as a report would lose the dispatch, so anything else in the message keeps it a normal request.
"""
from __future__ import annotations

import re
from typing import Dict, List, Pattern, Tuple

from llm.llm_client import ORD_RE, PIECES_RE

_NEGATABLE = r"closed|closing|shut|stopped|halted|suspended|on strike|down|out of (?:action|service)"
STOP_RE = re.compile(
    r"\b(?:closed|closes|closing|closure|shut|shutting|shutdown|halted|suspended|on strike|broke(?:n)? down|breakdown"
    r"|out of (?:action|service)|not (?:running|operating|working|moving)|nothing moving"
    r"|failed (?:an? |the |its )?(?:inspection|audit)"
    r"|stopped (?:working|running|operating|producing|taking)|stopped(?!\s+\w+ing\b))\b", re.I)
# the opposite meaning, or "closed" said of a piece of business and not of the workshop
NOT_STOPPED_RE = re.compile(
    rf"(?:\bnot|n't|\bnever|\bno longer)\s+(?:been\s+|actually\s+)?(?:{_NEGATABLE})"
    r"|\bre-?open|\bback (?:open|up|online|running)"
    r"|\b(?:closed|suspended|stopped)\s+(?:out\b|off\b|(?:\S+\s+){0,2}?(?:deal|order|ticket|account|sale|contract|case|thread|issue|chat|quote|file|loop|ORD-\d+)\b)", re.I)
OTHER_SUBJECT_RE = re.compile(r"\b(?:office|deal|contract|account|ticket|sale|quote|bank|port|customs|warehouse|road|store|case|thread|chat|issue|client|customer)\b", re.I)
TIME_WORD_RE = re.compile(r"\b(?:before|until|till|after|when|once|by the time)\b", re.I)
PRONOUN_RE = re.compile(r"^\s*(?:they|it|he|she|the (?:shop|workshop|factory))\b", re.I)
# a clause ends at punctuation followed by a space, and before "so" or "but", or "and" followed by an instruction
CLAUSE_RE = re.compile(r".+?(?:[.;,!?]+(?:\s+|$)|\s+(?=(?:so|but)\s)|\s+(?=and\s+(?:send|give|use|put|move|ship)\b)|$)", re.I | re.S)
# what makes the rest of a message a request and not just more about the stop
REQUEST_RE = re.compile(r"\b(?:send\w*|giv\w+|put|ship\w*|dispatch\w*|allocat\w*|assign\w*|move[sd]?|book\w*|need\w*|find|pick|choose"
                        r"|orders?|reorders?|batch\w*|shops?|pieces?|pcs|due|deadline|urgent|rush\w*)\b", re.I)


def _name_pattern(name: str) -> Pattern:
    """'GiantWeave' also matches 'Giant Weave'."""
    words = re.findall(r"[A-Z][a-z]+", name)
    return re.compile(r"\b" + r"\s*".join(words) + r"\b", re.I)


def _names_in(clause: str, names: Dict[str, str]) -> List[Tuple[int, int, str]]:
    return sorted((m.start(), m.end(), wid) for wid, name in names.items() for m in _name_pattern(name).finditer(clause))


def _stopped_in_clause(clause: str, named: List[Tuple[int, int, str]], last_named) -> List[str]:
    stop = STOP_RE.search(clause)
    if not stop or clause.rstrip().endswith("?") or NOT_STOPPED_RE.search(clause):
        return []
    before = clause[:stop.start()]
    if OTHER_SUBJECT_RE.search(before) or TIME_WORD_RE.search(before):
        return []
    prior = [n for n in named if n[1] <= stop.start()]
    if prior:                                   # "GiantWeave and FreshStart have shut"
        hits = [prior[-1][2]]
        for a, b in zip(reversed(prior[:-1]), reversed(prior[1:])):
            if not re.fullmatch(r"\s*(?:and|&)\s*", clause[a[1]:b[0]], re.I):
                break
            hits.append(a[2])
        return hits[::-1]
    if named:                                   # "Production stopped at SteadyHands"
        return [named[0][2]]
    if last_named and PRONOUN_RE.match(clause):     # "Heard from SteadyHands. They've closed."
        return [last_named]
    return []


def read_stops(text: str, names: Dict[str, str]) -> Tuple[List[str], str]:
    """The workshops a message says have stopped, and the message without the clauses that say so.
    `names` maps workshop id to name. A clause that also carries an order keeps that part."""
    stopped: List[str] = []
    rest: List[str] = []
    last_named = None
    for clause in CLAUSE_RE.findall(text):
        named = _names_in(clause, names)
        hits = _stopped_in_clause(clause, named, last_named)
        if hits:
            stopped += [w for w in hits if w not in stopped]
            if ORD_RE.search(clause) or PIECES_RE.search(clause):
                first = min((n[0] for n in named if n[2] in hits), default=len(clause))
                head = clause[:first]
                rest.append(head + " " if ORD_RE.search(head) or PIECES_RE.search(head) else clause)
        else:
            rest.append(clause)
        if named:
            last_named = named[-1][2]
    return stopped, "".join(rest).strip()


def asks_nothing(rest: str, stopped: List[str], names: Dict[str, str]) -> bool:
    """True when what is left of a message is only more about the stop. When unsure, say no: a report read as a
    request still shows the stop to the dispatcher, but a request read as a report is lost."""
    if re.search(r"\d|\?", rest) or REQUEST_RE.search(rest):
        return False
    return all(n[2] in stopped for n in _names_in(rest, names))
