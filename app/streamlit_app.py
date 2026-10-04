"""SweaterCo Subcontracting Desk - dispatcher interface.

    streamlit run app/streamlit_app.py

Everything the dispatcher sees comes from desk/pipeline.py and kernel/. This file only
lays it out and turns clicks into Desk calls. It never computes an estimate itself.

Round 2 layout, built for a dispatcher with thirty messages and an hour:
  * the inbox is grouped by what the dispatcher has to do next, tightest first
  * each row already says the decision: workshop, return date, days to spare
  * one click confirms every recommendation that is safe even if the batch is reworked;
    tight ones are never bulk-confirmed
  * the card leads with three lines: what was asked, what the desk recommends, why
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "harness"))

from desk.pipeline import Desk, inbox_lines, HUMAN_STATUSES  # noqa: E402
from kernel.allocator import OBJECTIVES  # noqa: E402
from kernel.orders import TODAY  # noqa: E402
from kernel.register import eligibility_table  # noqa: E402
from llm.llm_client import LLMClient  # noqa: E402

st.set_page_config(page_title="SweaterCo Subcontracting Desk", page_icon="🧶", layout="wide")

STATUS_LABEL = {
    "awaiting_confirmation": ("Confirm", "green"),
    "awaiting_decision": ("No on-time option", "orange"),
    "refused": ("Refused · alternative", "red"),
    "needs_reply": ("Ask requester", "blue"),
    "answered": ("Can't answer", "gray"),
    "committed": ("Dispatched", "violet"),
    "reply_sent": ("Reply sent", "gray"),
    "answer_sent": ("Answer sent", "gray"),
    "escalated": ("Escalated", "gray"),
    "renegotiating": ("Renegotiating", "gray"),
    "dismissed": ("Dismissed", "gray"),
}
GROUPS = [  # (key, label, statuses) in the order a dispatcher works through them
    ("confirm", "To confirm", {"awaiting_confirmation"}),
    ("decide", "Needs a decision", {"awaiting_decision", "refused"}),
    ("ask", "Ask requester", {"needs_reply"}),
    ("answer", "Can't answer", {"answered"}),
    ("done", "Done", {"committed"} | HUMAN_STATUSES),
]
OBJECTIVE_HELP = {
    "lateness": "Primary. On time even if reworked, specialist shop first, then earliest finish.",
    "use_slack": "Same rule, but takes the latest safe finish: slower turnaround, lower cost.",
    "hybrid": "Lateness with a weight on defects and on spreading the work.",
    "defects": "Lowest defect rate among shops that make the date.",
    "fairness": "Spreads work across shops, never at the price of a late batch.",
    "cost": "Cheapest shop that makes the date.",
    "lateness_v1": "Round-1 setting (equals earliest finish). Kept for comparison.",
    "hybrid_v0": "Round-1 hybrid weights. Kept for comparison.",
}
SENDERS = ["Boss", "Chen", "Ravi", "Priya", "Mei"]


# ------------------------------------------------------------------ session
def new_desk(objective: str, use_llm: bool) -> Desk:
    client = LLMClient(provider="openai") if use_llm else None
    st.session_state.llm_client = client
    return Desk(parser=client.parse_request if client else None, objective=objective)


if "desk" not in st.session_state:
    st.session_state.use_llm = False
    st.session_state.desk = new_desk("lateness", False)
    st.session_state.selected = None
desk: Desk = st.session_state.desk


def flash(msg: str, kind: str = "success") -> None:
    st.session_state.flash = (kind, msg)


def act(fn, *args, ok: str = "", **kwargs):
    try:
        out = fn(*args, **kwargs)
        if ok:
            flash(ok)
        return out
    except (ValueError, KeyError) as ex:
        flash(str(ex), "error")
        return None


def fmt_date(s) -> str:
    return pd.Timestamp(s).strftime("%a %d %b") if s else "-"


def chosen(d: dict):
    """The candidate row of the recommended (or confirmed) workshop, straight from the kernel output."""
    wid = d.get("confirmed_workshop") or d.get("recommended")
    return next((c for c in d["candidates"] if c["workshop_id"] == wid), None)


def margin(c: dict, d: dict) -> int:
    """Days between the promised date and the due date; negative when late. Both dates come from the kernel."""
    return (date.fromisoformat(d["batch"]["due_date"]) - date.fromisoformat(c["promised_date"])).days


def group_of(d: dict) -> str:
    return next(k for k, _, statuses in GROUPS if d["status"] in statuses)


def next_open(after: str):
    ids = [r for r in desk.decisions if desk.is_open(desk.decisions[r])]
    same = [r for r in ids if group_of(desk.decisions[r]) == st.session_state.get("group", "confirm")]
    pool = same or ids
    later = [r for r in pool if desk.arrival.get(r, 0) > desk.arrival.get(after, -1)]
    return (later or pool or [None])[0]


# ------------------------------------------------------------------ sidebar
with st.sidebar:
    st.title("🧶 Subcontracting Desk")
    st.caption(f"SweaterCo · today {TODAY:%a %d %b %Y}")

    objective = st.selectbox("Objective", list(OBJECTIVES), index=list(OBJECTIVES).index(desk.alloc.objective),
                             format_func=lambda o: o.replace("_", " "), help="How eligible workshops are ranked. Changing it re-ranks every open request.")
    st.caption(OBJECTIVE_HELP.get(objective, ""))
    if objective != desk.alloc.objective:
        desk.set_objective(objective)
        flash(f"Objective set to {objective}; open requests re-ranked")
        st.rerun()

    has_key = bool(os.getenv("OPENAI_API_KEY") or os.getenv("DESK_LLM_API_KEY"))
    parser_choice = st.radio("Message parser", ["Rules (free, offline)", "GPT-5 nano"], index=1 if st.session_state.use_llm else 0,
                             disabled=not has_key, help="Changing the parser starts a new session." if has_key else "Add OPENAI_API_KEY to .env to enable")
    want_llm = parser_choice == "GPT-5 nano"
    if want_llm != st.session_state.use_llm:
        st.session_state.use_llm = want_llm
        st.session_state.desk = new_desk(desk.alloc.objective, want_llm)
        st.session_state.selected = None
        st.rerun()

    c1, c2 = st.columns(2)
    if c1.button("Load morning inbox", type="primary", width="stretch", disabled=any(r.startswith("R") for r in desk.decisions)):
        with st.spinner("Reading 30 messages…"):
            for ln in inbox_lines():
                desk.propose(ln)
        st.session_state.selected = None
        flash("30 messages received. Nothing is dispatched until you confirm.")
        st.rerun()
    if c2.button("Reset", width="stretch"):
        st.session_state.desk = new_desk(desk.alloc.objective, st.session_state.use_llm)
        st.session_state.selected = None
        st.rerun()

    st.subheader("Standing constraints")
    if not desk.session_excl:
        st.caption("None")
    for wid, src in list(desk.session_excl.items()):
        cc1, cc2 = st.columns([3, 1])
        cc1.markdown(f"⛔ **{desk.name(wid)}** · no new work  \n<small>{src['by']} in {src['source']} at {src.get('time', '')} · applies to every open request</small>",
                     unsafe_allow_html=True)
        if cc2.button("Lift", key=f"lift_{wid}"):
            desk.lift_constraint(wid)
            flash(f"Lifted the constraint on {desk.name(wid)}; open requests re-ranked")
            st.rerun()

    st.subheader("Workshop queues")
    q = desk.ledger.queues()
    sent = {}
    for r in desk.ledger.records:
        if r["status"] == "committed":
            sent[r["workshop_id"]] = sent.get(r["workshop_id"], 0) + r["pieces"]
    st.dataframe(pd.DataFrame([{"Workshop": desk.name(w) + (" ⛔" if (desk.W[w].status != "ACTIVE" or w in desk.session_excl) else ""),
                                "Queue": round(v, 1), "Sent": sent.get(w, 0)} for w, v in q.items()]),
                 hide_index=True, width="stretch",
                 column_config={"Queue": st.column_config.NumberColumn("Queue d", format="%.1f", width=62, help="Days of work the shop is holding now"),
                                "Sent": st.column_config.NumberColumn("Sent", format="%d", width=52, help="Pieces confirmed in this session")})
    if st.session_state.get("llm_client"):
        c = st.session_state.llm_client
        st.caption(f"GPT-5 nano spend this session: ${c.spent_usd:.4f} of ${c.budget_usd:.2f}")

if "flash" in st.session_state:
    kind, msg = st.session_state.pop("flash")
    (st.error if kind == "error" else st.success)(msg)

tab_desk, tab_ws, tab_audit, tab_sim, tab_eval = st.tabs(["Dispatch", "Workshops", "Audit log", "Simulator", "Evaluation"])


# ------------------------------------------------------------------ dispatch
def inbox_row(d: dict) -> dict:
    c = chosen(d)
    decision, back, spare = "", "", None
    if d["status"] == "committed":
        decision, back, spare = f"Sent → {desk.name(d['confirmed_workshop'])}", fmt_date(d["final_estimate"]["promised_date"]), margin(d["final_estimate"], d)
    elif d["subtype"] == "allocate":
        decision = f"★ {c['name']}" + ("" if c.get("safe") else "  ·  tight")
        back, spare = fmt_date(c["promised_date"]), margin(c, d)
    elif d["subtype"] == "no_on_time_option":
        decision = "No on-time option" + (f"  ·  earliest {c['name']}" if c else "")
        back, spare = (fmt_date(c["promised_date"]), margin(c, d)) if c else ("", None)
    elif d["subtype"] == "ineligible_suggestion":
        decision = f"✕ {desk.name(d['refused_workshop'])}" + (f"  →  {c['name']}" if c else "")
        back, spare = (fmt_date(c["promised_date"]), margin(c, d)) if c else ("", None)
    elif d["official_behaviour"] == "clarify":
        decision = "Ask: which order?" if d["subtype"] == "ambiguous_reference" else "Ask: missing details"
    else:
        decision = "Not in the data"
    if d["status"] in HUMAN_STATUSES:
        decision = STATUS_LABEL[d["status"]][0]
    return {"ID": d["request_id"], "Order": d["order_id"] or "?", "Decision": decision, "Back": back, "Spare": "" if spare is None else f"{spare} d"}


def candidate_frame(d: dict) -> pd.DataFrame:
    rows = []
    for c in d["candidates"]:
        rows.append({
            "": "★" if c["workshop_id"] == d["recommended"] else "",
            "Workshop": c["name"],
            "Back": fmt_date(c["promised_date"]),
            "Days to spare": margin(c, d),
            "If reworked": fmt_date(c["worst_date"]) + ("" if c["safe"] else "  (late)"),
            "Days": round(c["finish_days"], 1),
            "Queue": round(c["queue_days"], 1),
            "Work": round(c["work_days"], 1),
            "Transport": int(c["lead_days"]),
            "Cost": int(round(c["cost"])),
            "Defect": f"{c['defect_rate']:.0%}",
        })
    return pd.DataFrame(rows)


def render_card(d: dict) -> None:
    rid = d["request_id"]
    label, color = STATUS_LABEL[d["status"]]
    p = d["parsed"]
    with st.container(border=True):
        h1, h2 = st.columns([4, 2])
        h1.markdown(f"#### {rid} · {d['timestamp']} · {d['requester']}")
        h2.badge(label, color=color)
        st.markdown(f"> {d['raw_text']}")

        # line 1: what was asked
        facts = [x for x in [
            f"**{d['order_id']}**" if d["order_id"] else None,
            (f"**{d['batch']['pieces']}** pcs {d['batch']['category']} · due **{fmt_date(d['batch']['due_date'])}** "
             f"({(date.fromisoformat(d['batch']['due_date']) - TODAY).days} days)") if d["batch"] else None,
            f"wants **{p['preference'].replace('_', ' ')}**" if p["preference"] != "none" else None,
            f"asked for **{desk.name(p['forced_workshop'])}**" if p["forced_workshop"] else None,
            "avoid " + ", ".join(f"**{desk.name(w)}**" for w in p["excluded_workshops"]) if p["excluded_workshops"] else None,
        ] if x]
        st.caption(" · ".join(facts) + f"  ·  parsed by {p['parser']}")

        # line 2: the decision, with the numbers a dispatcher quotes to the customer
        c = chosen(d)
        if d["status"] == "committed":
            fe = d["final_estimate"]
            st.success(f"**Dispatched to {desk.name(d['confirmed_workshop'])}** · back {fmt_date(fe['promised_date'])}"
                       + ("" if fe["on_time"] else f" · {fe['late_days']} days late (accepted)") + f" · audit {d['committed']}")
        elif d["subtype"] == "allocate":
            spare = margin(c, d)
            msg = (f"★ **{c['name']}** · back **{fmt_date(c['promised_date'])}** · on time, {spare} day{'s' if spare != 1 else ''} to spare · "
                   f"if reworked: {fmt_date(c['worst_date'])}" + ("" if c["safe"] else " (**late**)") + f" · cost {c['cost']:.0f}")
            (st.success if c["safe"] else st.warning)(msg)
        elif d["subtype"] == "no_on_time_option":
            if c:
                st.warning(f"▲ **No workshop makes {fmt_date(d['batch']['due_date'])}.** Earliest: **{c['name']}**, "
                           f"back {fmt_date(c['promised_date'])}, **{c['late_days']} days late**")
            else:
                st.warning("▲ No eligible workshop at all")
        elif d["subtype"] == "ineligible_suggestion":
            st.error(f"✕ **{desk.name(d['refused_workshop'])} can't take this.** "
                     + (f"Alternative: **{c['name']}**, back {fmt_date(c['promised_date'])}"
                        + ("" if c["on_time"] else f", {c['late_days']} days late") if c else "No eligible alternative."))
        elif d["official_behaviour"] == "clarify":
            st.info("? **Ask the requester before dispatching**")
        else:
            st.info("ⓘ **The data can't answer this**")

        # line 3: why
        if d.get("why") and d["subtype"] == "allocate" and (d["status"] != "committed" or d.get("confirmed_workshop") == d.get("recommended")):
            st.markdown(f"**Why:** {d['why']}.")
        nc = d["number_check"]
        st.caption(("✅ every number comes from a tool output" if nc["ok"] else f"⚠ untraced numbers: {nc['untraced']}")
                   + (f" · {len(d['tool_calls'])} tool calls" if d["tool_calls"] else ""))
        ar = d.get("as_received")
        if ar and desk.is_open(d) and (ar["recommended"] != d["recommended"] or ar["subtype"] != d["subtype"]):
            st.caption(f"↻ When it arrived at {d['timestamp']} the answer was {ar['subtype'].replace('_', ' ')}"
                       + (f" / {desk.name(ar['recommended'])}" if ar["recommended"] else "") + "; it changed with the ledger or a later constraint.")
        for fl in d["flags"]:
            if fl.startswith("updated since received") or (fl.startswith("standing constraint") and not desk.is_open(d)):
                continue
            st.caption(f"• {fl}")

    # ---- candidates and who is out
    if d["candidates"]:
        st.markdown("**Eligible workshops** · ranked by `" + desk.alloc.objective + "`"
                    + (f" · preference `{p['preference']}`" if p["preference"] in ("fastest", "cheapest_on_time", "lowest_defect") else ""))
        st.dataframe(candidate_frame(d), hide_index=True, width="stretch")
    blocked = [e for e in d["eligibility"] if not e["eligible"]]
    if blocked:
        st.caption("Not eligible: " + " · ".join(f"**{e['name']}** ({e['reason']})" for e in blocked))

    # ---- actions
    if d["status"] == "committed":
        rec = next(r for r in desk.ledger.records if r["audit_id"] == d["committed"])
        others = [x for x in d["candidates"] if x["workshop_id"] != d["confirmed_workshop"]]
        if others:
            a1, a2 = st.columns([3, 2])
            target = a1.selectbox("Reassign to", [x["workshop_id"] for x in others], format_func=desk.name, key=f"re_{rid}")
            if a2.button("Reassign", key=f"reb_{rid}", width="stretch"):
                act(desk.reassign, rec["audit_id"], target, ok=f"Reassigned to {desk.name(target)}")
                st.rerun()
        with st.expander("Explanation recorded with this dispatch"):
            st.write(rec["reason"])
        with st.expander("Audit record"):
            st.json(rec, expanded=False)

    elif d["subtype"] in ("allocate", "ineligible_suggestion", "no_on_time_option") and d["candidates"] and desk.is_open(d):
        best = d["candidates"][0]
        late = not best["on_time"]
        b1, b2 = st.columns(2)
        primary = (f"Accept delay · send to {best['name']}" if late else f"Confirm {best['name']}")
        if b1.button(primary, type="primary", key=f"ok_{rid}", width="stretch"):
            if act(desk.confirm, rid, best["workshop_id"], accept_late=late, ok=f"{rid} dispatched to {best['name']}"):
                st.session_state.selected = next_open(rid)
            st.rerun()
        alt = d["candidates"][1:]
        if alt:
            target = b2.selectbox("Or choose", [x["workshop_id"] for x in alt], format_func=lambda w: next(
                f"{x['name']} · back {fmt_date(x['promised_date'])}" + ("" if x["on_time"] else f" · {x['late_days']}d late")
                for x in alt if x["workshop_id"] == w), key=f"alt_{rid}", label_visibility="collapsed")
            tc = next(x for x in alt if x["workshop_id"] == target)
            if b2.button(f"Send to {tc['name']}", key=f"altb_{rid}", width="stretch"):
                if act(desk.confirm, rid, target, accept_late=not tc["on_time"], ok=f"{rid} dispatched to {tc['name']}"):
                    st.session_state.selected = next_open(rid)
                st.rerun()
        if late:
            l1, l2 = st.columns(2)
            if l1.button("Renegotiate due date", key=f"neg_{rid}", width="stretch"):
                act(desk.mark, rid, "renegotiating", ok=f"{rid} marked: renegotiating with the customer")
                st.rerun()
            if l2.button("Escalate to Boss", key=f"esc_{rid}", width="stretch"):
                act(desk.mark, rid, "escalated", ok=f"{rid} escalated")
                st.rerun()
        with st.expander("Message for the group chat"):
            st.code(d["explanation"], language=None, wrap_lines=True)

    elif d["official_behaviour"] == "clarify" and desk.is_open(d):
        st.markdown("**Message for the group chat**")
        st.code(d["explanation"], language=None, wrap_lines=True)
        if d["order_candidates"]:
            o1, o2 = st.columns([3, 2])
            pick = o1.selectbox("Requester means", d["order_candidates"], format_func=lambda o: (
                f"{o} · {desk.O[o].customer} · {desk.O[o].product} · {desk.O[o].pieces} pcs · due {fmt_date(desk.O[o].due_date.isoformat())}"),
                key=f"pick_{rid}")
            if o2.button("Use this order", key=f"pickb_{rid}", width="stretch", type="primary"):
                new = act(desk.follow_up, rid, pick, ok=f"{rid} resolved to {pick}")
                if new:
                    st.session_state.selected = new["request_id"]
                    st.session_state.group_pending = group_of(new)
                st.rerun()
        with st.form(f"reply_{rid}", clear_on_submit=True):
            ans = st.text_input(f"{d['requester']}'s answer", placeholder="e.g. ORD-066, new due date Apr 20")
            r1, r2 = st.columns(2)
            if r1.form_submit_button("Process answer", type="primary", width="stretch") and ans.strip():
                new = act(desk.follow_up, rid, ans.strip())
                if new:
                    st.session_state.selected = new["request_id"]
                    st.session_state.group_pending = group_of(new)
                st.rerun()
            if r2.form_submit_button("Question sent, wait", width="stretch"):
                act(desk.mark, rid, "reply_sent", ok=f"{rid}: waiting for {d['requester']}")
                st.rerun()

    elif d["subtype"] == "not_in_data" and desk.is_open(d):
        st.markdown("**Message for the group chat**")
        st.code(d["explanation"], language=None, wrap_lines=True)
        if st.button("Answer sent", key=f"ans_{rid}", type="primary"):
            act(desk.mark, rid, "answer_sent", ok=f"{rid} closed")
            st.session_state.selected = next_open(rid)
            st.rerun()
    else:
        st.caption(f"Closed: {STATUS_LABEL[d['status']][0]}")

    with st.expander("Tool calls behind this recommendation"):
        for t in d["tool_calls"]:
            st.markdown(f"`{t['tool']}` · input `{json.dumps(t.get('input'), default=str)}`")
            st.json(t.get("output"), expanded=False)


with tab_desk:
    if not desk.decisions:
        st.info("Click **Load morning inbox** in the sidebar to receive the 30 chat messages from 1 April, or type a new message below.")
    desk.refresh_all()
    decisions = list(desk.decisions.values())
    counts = {k: sum(1 for d in decisions if d["status"] in statuses) for k, _, statuses in GROUPS}

    # which group is shown: follow a pending jump (a follow-up landed in another group), else keep the user's choice
    if "group_pending" in st.session_state:
        st.session_state.group = st.session_state.pop("group_pending")
    if st.session_state.get("group") not in dict((k, 1) for k, _, _ in GROUPS):
        st.session_state.group = next((k for k, _, _ in GROUPS if counts[k]), "confirm")
    labels = {k: f"{lab} ({counts[k]})" for k, lab, _ in GROUPS}
    picked = st.segmented_control("Inbox", [k for k, _, _ in GROUPS], format_func=lambda k: labels[k], default=st.session_state.group,
                                  key=f"group_ctl_{st.session_state.group}", label_visibility="collapsed")
    if picked and picked != st.session_state.group:
        st.session_state.group = picked
        st.session_state.selected = None
        st.rerun()
    group = st.session_state.group
    view = [d for d in decisions if group_of(d) == group]

    def urgency(d):          # tightest first: fewest days to spare, then arrival
        c = chosen(d)
        return (margin(c, d) if (c and d.get("batch")) else 99, desk.arrival.get(d["request_id"], 0))
    view.sort(key=urgency)

    left, right = st.columns([6, 7], gap="large")
    with left:
        if group == "confirm" and view:
            plan = desk.bulk_plan()
            n_go, held = len(plan["confirm"]), plan["held"]
            if n_go and st.button(f"Confirm {n_go} safe recommendation{'s' if n_go != 1 else ''} in one click", type="primary", width="stretch",
                                  help="Safe = on time even if the batch is reworked. Each one is re-checked against the ledger as it is confirmed."):
                out = desk.confirm_all(by="dispatcher")
                left = len(out["skipped"])
                flash(f"{len(out['confirmed'])} dispatched: " + ", ".join(f"{x['request_id']} → {desk.name(x['workshop_id'])}" for x in out["confirmed"])
                      + (f". {left} left for you to decide." if left else "."))
                st.session_state.selected = None
                st.rerun()
            if held:
                n_tight = sum(1 for h in held if h["reason"].startswith("tight"))
                st.caption(("Held back for you: " if n_go else "Decide these one by one: ")
                           + f"{n_tight} tight (a rework would make them late), listed first"
                           + (f", and {len(held) - n_tight} that would take a workshop a tight one needs." if len(held) > n_tight else "."))
        inbox = pd.DataFrame([inbox_row(d) for d in view])
        if len(inbox):
            ev = st.dataframe(inbox, hide_index=True, width="stretch", on_select="rerun", selection_mode="single-row",
                              # the key changes with every ledger write or human action, so a stale row selection cannot outlive the list it pointed into
                              key=f"inbox_{group}_{len(desk.ledger.records)}_{len(desk.actions)}", height=min(38 + 35 * len(inbox), 600),
                              column_config={"ID": st.column_config.TextColumn("ID", width=48),
                                             "Order": st.column_config.TextColumn("Order", width=76),
                                             "Decision": st.column_config.TextColumn("Decision", width=178),
                                             "Back": st.column_config.TextColumn("Back", width=84),
                                             "Spare": st.column_config.TextColumn("Spare", width=74,
                                                                                  help="Days between the promised date and the due date; negative = late")})
            rows = ev.selection.rows if ev and ev.selection else []
            if rows:
                st.session_state.selected = inbox.iloc[rows[0]]["ID"]
            if st.session_state.selected not in {d["request_id"] for d in view}:
                st.session_state.selected = inbox.iloc[0]["ID"]
        else:
            st.caption("Nothing here.")
            st.session_state.selected = None

        with st.form("new_message", clear_on_submit=True):
            st.markdown("**New message**")
            fc1, fc2 = st.columns([1, 3])
            sender = fc1.selectbox("From", SENDERS, label_visibility="collapsed")
            text = fc2.text_input("Message", placeholder="e.g. ORD-066 — 1000 polo shirts, due Apr 20", label_visibility="collapsed")
            if st.form_submit_button("Send to desk") and text.strip():
                nd = desk.new_message(sender, text.strip())
                st.session_state.selected = nd["request_id"]
                st.session_state.group_pending = group_of(nd)
                st.rerun()

    with right:
        rid = st.session_state.selected
        if not rid or rid not in desk.decisions:
            st.caption("Select a message to see the recommendation.")
        else:
            render_card(desk.decisions[rid])


# ------------------------------------------------------------------ workshops
with tab_ws:
    st.subheader("Workshop register")
    q = desk.ledger.queues()
    reg = pd.DataFrame([{
        "ID": w.workshop_id, "Name": w.name, "Makes": " + ".join(sorted(w.makes)), "Status": w.status,
        "Pcs/day": w.capacity, "Transport days": w.lead_days, "Defect": f"{w.defect_rate:.0%}", "Cost/pc": w.cost,
        "Max batch": str(w.max_batch) if w.max_batch else "no cap", "Queue now (days)": round(q[w.workshop_id], 1),
        "Sent today (pcs)": sent.get(w.workshop_id, 0),
        "Standing constraint": (f"no new work ({desk.session_excl[w.workshop_id]['by']}, {desk.session_excl[w.workshop_id]['source']} "
                                f"at {desk.session_excl[w.workshop_id].get('time', '')})") if w.workshop_id in desk.session_excl else "",
        "Notes": w.notes,
    } for w in desk.W.values()])
    st.dataframe(reg, hide_index=True, width="stretch")
    st.bar_chart(reg, x="Name", y="Queue now (days)", horizontal=True, height=280)

    st.subheader("Who can take a batch?")
    wc1, wc2 = st.columns(2)
    cat = wc1.selectbox("Category", ["TOPS", "ACCESSORIES"])
    pcs = wc2.number_input("Pieces", min_value=1, max_value=5000, value=1500, step=100)
    elig = eligibility_table(desk.W, cat, int(pcs), exclude=set(desk.session_excl))
    st.dataframe(pd.DataFrame([{"Workshop": e["name"], "Can take": "✅" if e["eligible"] else "❌", "Reason": e["reason"]} for e in elig]),
                 hide_index=True, width="stretch")


# ------------------------------------------------------------------ audit
with tab_audit:
    st.subheader("Ledger")
    if desk.ledger.records:
        st.dataframe(pd.DataFrame([{
            "Audit": r["audit_id"], "Status": r["status"], "Request": r["request_id"], "Requester": r["requester"],
            "Order": r["order_id"], "Pieces": r["pieces"], "Workshop": desk.name(r["workshop_id"]),
            "Back": r["estimate"]["promised_date"], "If reworked": r["estimate"].get("worst_date", ""), "Due": r["due_date"],
            "Late days": r["estimate"]["late_days"], "Confirmed by": r["confirmed_by"], "At": r["written_at"],
        } for r in desk.ledger.records]), hide_index=True, width="stretch")
        st.download_button("Download audit.json", json.dumps(desk.ledger.records, ensure_ascii=False, indent=2, default=str),
                           file_name="audit.json", mime="application/json")
    else:
        st.caption("No dispatches yet.")
    st.subheader("Dispatcher actions")
    if desk.actions:
        st.dataframe(pd.DataFrame(desk.actions), hide_index=True, width="stretch")
    else:
        st.caption("No actions yet.")


# ------------------------------------------------------------------ simulator
@st.cache_data(show_spinner=False)
def run_sim(seed: int, shock: bool, seeds: int) -> pd.DataFrame:
    from simulate import Simulator, random_choice, greedy_biggest, cheapest
    from kernel.allocator import Allocator, earliest_finish
    pols = [("random", random_choice, "official baseline"), ("greedy_biggest", greedy_biggest, "official baseline"),
            ("cheapest", cheapest, "official baseline"), ("earliest_finish", earliest_finish, "simple rule-based allocator")]
    pols += [(o, Allocator(o), "our allocator") for o in OBJECTIVES]
    acc = {}
    for s in range(seed, seed + seeds):
        sim = Simulator(shock=shock, seed=s)
        for name, pol, kind in pols:
            if hasattr(pol, "reset"):
                pol.reset()
            m = Simulator.metrics(sim.run(pol, name))
            a = acc.setdefault(name, {"Kind": kind})
            for k, v in m.items():
                a[k] = a.get(k, 0.0) + v / seeds
    return pd.DataFrame([{"Policy": n, "Kind": a["Kind"], "% late": round(a["% late"], 2), "Late days": round(a["late days"], 2),
                          "Mean days": round(a["mean days"], 1), "P90 days": round(a["p90 days"], 1), "% def pcs": round(a["% def pcs"], 1),
                          "Cost": round(a["cost"]), "Max share %": round(a["max share"], 1)} for n, a in acc.items()])


with tab_sim:
    st.subheader("Shared simulator · 120 orders replayed")
    st.caption("Runs the untouched harness/simulate.py (v3): the three official baselines, the simple rule-based allocator (earliest finish) "
               "and every objective setting.")
    s1, s2, s3 = st.columns([1, 1, 2])
    seed = s1.number_input("First seed", value=5105, step=1)
    ten = s2.toggle("Average 10 seeds", value=True, help="Tracks v4 asks for shock results averaged over ten seeds (5105–5114).")
    shock = s3.toggle("Shock (one workshop closes for two weeks, 31 Jan – 14 Feb)")
    df = run_sim(int(seed), bool(shock), 10 if ten else 1)
    st.dataframe(df, hide_index=True, width="stretch")
    st.bar_chart(df, x="Policy", y="% late", color="Kind", horizontal=True, height=max(360, 42 * len(df)))
    st.caption("Command-line equivalent: `python harness/run_baselines.py --seed " + str(int(seed))
               + (" --shock" if shock else "") + (" --seeds 10`" if ten else " --seeds 1`"))


# ------------------------------------------------------------------ evaluation
with tab_eval:
    st.subheader("Evaluation")
    st.markdown("The language surface is scored on four things, separately: **extraction** (12 parsed fields), **behaviour** "
                "(extract / clarify / refuse / decline), **decision** (checked by a second implementation that shares no code with the system) "
                "and **explanation** (every number traced; the reply contains what that kind of reply must contain).")
    labels = ROOT / "eval" / "gold_labels.csv"
    if labels.exists():
        st.code(f"python eval/run_language_eval.py --labels {labels.relative_to(ROOT)}", language="bash")
    else:
        st.info("The gold labels are not frozen yet (`eval/gold_labels.csv` is missing), so nothing is scored here. "
                "Once they are, run `python eval/run_language_eval.py --labels eval/gold_labels.csv` (add `--parser llm --runs 3` for GPT-5 nano).")
    replay = Desk(objective=desk.alloc.objective)
    for ln in inbox_lines():
        replay.handle(ln)
    traced = sum(1 for d in replay.decisions.values() if d["number_check"]["ok"])
    e1, e2, e3 = st.columns(3)
    e1.metric("Replies with every number traced", f"{traced}/{len(replay.decisions)}")
    e2.metric("Dispatched in an unattended replay", len(replay.ledger.records))
    e3.metric("Objective", desk.alloc.objective)
    st.caption("An unattended replay processes the 30 messages in time order and confirms every on-time recommendation; it is what the evaluation scripts run.")
