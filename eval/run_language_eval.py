"""Evaluate the language surface on an inbox: extraction, behaviour, decision, explanation. Separately.

    python eval/run_language_eval.py --labels <labels.csv>                       # rule parser, free
    python eval/run_language_eval.py --labels <labels.csv> --parser llm --runs 3 # GPT-5 mini by default, costs money
    python eval/run_language_eval.py --inbox <file> --labels <csv> --parses <json> --out <dir>

Requests are processed in time order; an on-time allocation is confirmed and occupies capacity.
Four things are scored per request and reported separately (Tracks v4):

  extraction   the 12 parsed fields against hand-made parses (language/requests_gold.json)
  behaviour    extract / clarify / refuse / decline-to-answer against the labels
  decision     eligible, constraints honoured, on time when an on-time option exists in the ledger
               state at that moment, 'no on-time option' only when true, preference honoured.
               Checked with eval/independent.py, which shares no code with the system.
  explanation  every number is found in a tool output, and the reply contains what that kind of
               reply must contain (candidate orders listed, refusal reason given, earliest date, ...)

The labels file is a CSV with request_id, official_behaviour, internal_subtype, also_accepted_subtype,
constraint, session_exclusions_in_force, matching_orders (see 01_标注/gold_labels_v3_proposed.csv).
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "eval"))

FIELDS = ["order_id", "customer", "product", "pieces", "due_date", "forced_workshop", "excluded_workshops", "constraint_scope",
          "preference", "question_type", "references_prior", "missing_fields"]
OFFICIAL = {"allocate": "extract", "no_on_time_option": "extract", "ambiguous_reference": "clarify", "missing_fields": "clarify",
            "state_conflict": "clarify", "ineligible_suggestion": "refuse", "not_in_data": "decline-to-answer"}


def same(a, b):
    if a in (None, [], "") and b in (None, [], ""):
        return True
    if isinstance(a, list) and isinstance(b, list):
        return sorted(a) == sorted(b)
    return a == b


def complete(decision: dict, label: dict, names: dict) -> list:
    """Does the reply contain what a reply of this kind must contain? Returns what is missing."""
    text, sub, miss = decision["explanation"], decision["subtype"], []
    rec = decision.get("recommended")
    if sub == "allocate":
        if names.get(rec, "?") not in text:
            miss.append("recommended workshop not named")
        if not re.search(r"back \d{4}-\d{2}-\d{2}", text):
            miss.append("no return date")
    elif sub == "no_on_time_option":
        if "No workshop" not in text and "No eligible workshop" not in text:
            miss.append("does not say that nobody makes the date")
        if not re.search(r"\d+ days? late", text) and "No eligible workshop" not in text:
            miss.append("no 'N days late'")
        if "Options" not in text and "Escalating" not in text:
            miss.append("no options")
    elif sub == "ineligible_suggestion":
        if names.get(decision.get("refused_workshop"), "?") not in text or "can't take" not in text:
            miss.append("refusal or its reason missing")
        if "Alternative" not in text and "No other eligible" not in text:
            miss.append("no alternative")
    elif sub == "ambiguous_reference":
        listed = set(re.findall(r"ORD-\d{3}", text))
        expected = set(re.findall(r"ORD-\d{3}", label.get("matching_orders", "")))
        if expected and len(listed & expected) < min(2, len(expected)):
            miss.append("candidate orders not listed")
        if "?" not in text:
            miss.append("no question asked")
    elif sub == "missing_fields":
        if not re.search(r"due date|order number|piece count", text):
            miss.append("does not say what is missing")
    elif sub == "not_in_data":
        if not re.search(r"can't answer|does not exist|outside this desk", text):
            miss.append("does not say it cannot answer")
    return miss


def run_once(lines, labels, parses, parser, objective, data_dir):
    from desk.pipeline import Desk
    import independent
    workshops, orders = independent.load(data_dir)
    names = {wid: w["name"] for wid, w in workshops.items()}
    desk = Desk(parser=parser, objective=objective)
    rows = []
    for line in lines:
        queues = dict(desk.ledger.queues())                  # the ledger state this request sees
        d = desk.handle(line)
        rid = d["request_id"]
        lab = labels.get(rid, {})
        row = {"request_id": rid, "parser": d["parsed"].get("parser", ""), "subtype": d["subtype"], "behaviour": OFFICIAL[d["subtype"]],
               "recommended": d.get("recommended") or "", "gold_behaviour": lab.get("official_behaviour", ""), "gold_subtype": lab.get("internal_subtype", "")}
        # extraction
        if parses and rid in parses:
            wrong = [f for f in FIELDS if not same(d["parsed"].get(f), parses[rid].get(f))]
            row["fields_wrong"] = ";".join(f"{f}: got {d['parsed'].get(f)!r} want {parses[rid].get(f)!r}" for f in wrong)
            row["n_fields_wrong"] = len(wrong)
        # behaviour
        row["behaviour_ok"] = row["behaviour"] == row["gold_behaviour"] if lab else ""
        row["subtype_ok"] = (d["subtype"] in (lab.get("internal_subtype"), lab.get("also_accepted_subtype") or None)
                             or (d["subtype"] in ("allocate", "no_on_time_option") and lab.get("official_behaviour") == "extract")) if lab else ""
        # decision, against the ledger state at that moment (only where there is a decision to check)
        row["decision_problems"] = ""
        if lab and lab.get("official_behaviour") in ("extract", "refuse"):
            if row["behaviour"] != lab["official_behaviour"]:
                row["decision_ok"] = False
                row["decision_problems"] = "wrong behaviour, no decision to check"
            else:
                order = orders.get(lab.get("order_id") or d.get("order_id") or "")
                excl = set(filter(None, lab.get("session_exclusions_in_force", "").split(",")))
                m = re.match(r"exclude ([W\d,]+)", lab.get("constraint", ""))
                if m:
                    excl |= set(m.group(1).split(","))
                pref = lab.get("constraint", "") if lab.get("constraint", "") in ("fastest", "cheapest_on_time", "lowest_defect") else ""
                problems = independent.sound_decision(d, order, workshops, queues, excl, pref) if order else ["order not found"]
                row["decision_ok"] = not problems
                row["decision_problems"] = "; ".join(problems)
        else:
            row["decision_ok"] = ""
        # explanation
        missing = complete(d, lab, names)
        row["numbers_traced"] = d["number_check"]["ok"]
        row["untraced"] = ";".join(map(str, d["number_check"]["untraced"]))
        row["reply_complete"] = not missing
        row["reply_missing"] = "; ".join(missing)
        row["explanation_ok"] = row["numbers_traced"] and row["reply_complete"]
        row["explanation"] = d["explanation"]
        rows.append(row)
    return rows, desk


def summarise(all_runs, have_parses):
    out = {}
    flat = [r for run in all_runs for r in run]
    n = len(flat)
    if have_parses:
        total_fields = n * len(FIELDS)
        wrong = sum(r.get("n_fields_wrong", 0) for r in flat)
        out["field_accuracy_pct"] = round(100 * (1 - wrong / total_fields), 2)
        out["requests_with_all_fields_right_pct"] = round(100 * sum(1 for r in flat if r.get("n_fields_wrong", 0) == 0) / n, 2)
        per_field = Counter()
        for r in flat:
            for part in filter(None, r.get("fields_wrong", "").split(";")):
                per_field[part.split(":")[0]] += 1
        out["wrong_by_field"] = dict(per_field.most_common())
    lab = [r for r in flat if r["gold_behaviour"]]
    if lab:
        out["behaviour_accuracy_pct"] = round(100 * sum(bool(r["behaviour_ok"]) for r in lab) / len(lab), 2)
        out["subtype_accuracy_pct"] = round(100 * sum(bool(r["subtype_ok"]) for r in lab) / len(lab), 2)
        by = {}
        for r in lab:
            b = by.setdefault(r["gold_behaviour"], [0, 0])
            b[0] += bool(r["behaviour_ok"]); b[1] += 1
        out["behaviour_by_class"] = {k: f"{a}/{b}" for k, (a, b) in sorted(by.items())}
        dec = [r for r in lab if r["decision_ok"] != ""]
        out["decision_sound_pct"] = round(100 * sum(bool(r["decision_ok"]) for r in dec) / len(dec), 2) if dec else None
        out["decisions_checked"] = len(dec)
    out["numbers_traced_pct"] = round(100 * sum(bool(r["numbers_traced"]) for r in flat) / n, 2)
    out["reply_complete_pct"] = round(100 * sum(bool(r["reply_complete"]) for r in flat) / n, 2)
    if len(all_runs) > 1:      # the same request, parsed several times: does the outcome change?
        ids = [r["request_id"] for r in all_runs[0]]
        stable_b = sum(1 for i, _ in enumerate(ids) if len({run[i]["subtype"] for run in all_runs}) == 1)
        stable_r = sum(1 for i, _ in enumerate(ids) if len({(run[i]["subtype"], run[i]["recommended"]) for run in all_runs}) == 1)
        stable_f = sum(1 for i, _ in enumerate(ids) if len({run[i].get("fields_wrong", "") for run in all_runs}) == 1)
        out["consistency"] = {"runs": len(all_runs), "same_subtype_pct": round(100 * stable_b / len(ids), 1),
                              "same_subtype_and_workshop_pct": round(100 * stable_r / len(ids), 1), "same_parse_outcome_pct": round(100 * stable_f / len(ids), 1)}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--inbox", default=str(ROOT / "data" / "dispatch_requests.txt"))
    ap.add_argument("--labels", required=True)
    ap.add_argument("--parses", default=str(ROOT / "language" / "requests_gold.json"), help="hand-made parses; '' to skip extraction scoring")
    ap.add_argument("--parser", choices=["rules", "llm"], default="rules")
    ap.add_argument("--runs", type=int, default=1)
    ap.add_argument("--model", default="", help="LLM model id (default: DESK_LLM_MODEL or gpt-5-mini)")
    ap.add_argument("--prompt", choices=["v1", "v2"], default="v2", help="extraction prompt version (llm/llm_client.py PROMPTS)")
    ap.add_argument("--no-grounding", action="store_true", help="skip the code check of extracted values against the message text")
    ap.add_argument("--objective", default="lateness")
    ap.add_argument("--env", default="", help="path to a .env holding OPENAI_API_KEY (read, never copied)")
    ap.add_argument("--out", default=str(ROOT / "eval" / "runs"))
    ap.add_argument("--tag", default="official30")
    args = ap.parse_args()

    if args.env:
        from dotenv import load_dotenv
        load_dotenv(args.env)
    from llm.llm_client import LLMClient

    lines = [ln for ln in Path(args.inbox).read_text(encoding="utf-8").splitlines() if re.match(r"[A-Z]\d\d ", ln)]
    labels = {r["request_id"]: r for r in csv.DictReader(open(args.labels, encoding="utf-8-sig"))}
    parses = {g["request_id"]: g for g in json.loads(Path(args.parses).read_text(encoding="utf-8"))} if args.parses else {}

    client = (LLMClient(provider="openai", model=args.model or None, prompt=args.prompt, grounding=not args.no_grounding)
              if args.parser == "llm" else None)
    all_runs = []
    for k in range(args.runs):
        rows, desk = run_once(lines, labels, parses, client.parse_request if client else None, args.objective, ROOT / "data")
        for r in rows:
            r["run"] = k + 1
        all_runs.append(rows)
    summary = summarise(all_runs, bool(parses))
    summary.update(parser=args.parser if not client else f"llm:{client.model}", runs=args.runs, requests=len(lines), objective=args.objective, tag=args.tag)
    if client:
        fallbacks = [c for c in client.calls if "outcome" in c]
        from llm.llm_client import GROUNDING_VERSION
        summary.update(prompt=client.prompt, grounding=client.grounding, grounding_version=GROUNDING_VERSION if client.grounding else None,
                       values_corrected_by_grounding=client.grounding_changes)
        summary.update(llm_calls=len([c for c in client.calls if "cost_usd" in c]), fallbacks_to_rules=len(fallbacks),
                       spent_usd=round(client.spent_usd, 4),
                       mean_output_tokens=round(sum(c.get("output_tokens", 0) for c in client.calls) / max(1, len([c for c in client.calls if "cost_usd" in c]))))
        summary["fallback_reasons"] = [c["outcome"][:120] for c in fallbacks][:10]

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    stem = f"language_eval_{args.tag}_{client.model if client else 'rules'}"
    if client:
        stem += f"_prompt-{client.prompt}_{'grounded' if client.grounding else 'raw'}"
    (out / f"{stem}.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    cols = ["run", "request_id", "parser", "gold_behaviour", "behaviour", "behaviour_ok", "gold_subtype", "subtype", "subtype_ok", "recommended",
            "decision_ok", "decision_problems", "numbers_traced", "untraced", "reply_complete", "reply_missing", "n_fields_wrong", "fields_wrong", "explanation"]
    with open(out / f"{stem}_rows.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for run in all_runs:
            w.writerows(run)
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    bad = [r for run in all_runs for r in run if r.get("n_fields_wrong") or r["behaviour_ok"] is False or r["decision_ok"] is False or not r["explanation_ok"]]
    print(f"\nrows with any problem: {len(bad)} of {sum(len(r) for r in all_runs)}")
    for r in bad[:40]:
        print(f"  run {r['run']} {r['request_id']}: behaviour {r['behaviour']}/{r['gold_behaviour']} | decision {r['decision_problems'] or 'ok'} | "
              f"reply {r['reply_missing'] or 'ok'} | fields {r.get('fields_wrong', '')[:160]}")


if __name__ == "__main__":
    main()
