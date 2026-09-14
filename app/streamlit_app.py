"""SweaterCo Subcontracting Desk - dispatcher interface.

    streamlit run app/streamlit_app.py

Everything the dispatcher sees comes from desk/pipeline.py and kernel/. This file only
lays it out and turns clicks into Desk calls. It never computes an estimate itself.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "harness"))

from desk.pipeline import Desk, inbox_lines, score, HUMAN_STATUSES  # noqa: E402
from kernel.allocator import OBJECTIVES  # noqa: E402
from kernel.orders import TODAY  # noqa: E402
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
OPEN_FIRST = ["awaiting_confirmation", "awaiting_decision", "refused", "needs_reply", "answered"]
SENDERS = ["Boss", "Chen", "Ravi", "Priya", "Mei"]


# ------------------------------------------------------------------ session
def new_desk(objective: str, use_llm: bool) -> Desk:
    client = LLMClient(provider="openai") if use_llm else None
    st.session_state.llm_client = client
    return Desk(parser=client.parse_request if client else None, objective=objective)


if "desk" not in st.session_state:
    st.session_state.objective = "lateness"
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


# ------------------------------------------------------------------ sidebar
with st.sidebar:
    st.title("🧶 Subcontracting Desk")
    st.caption(f"SweaterCo · today {TODAY:%a %d %b %Y}")

    objective = st.selectbox("Objective", list(OBJECTIVES), index=list(OBJECTIVES).index(desk.alloc.objective),
                             help="Weights used to rank eligible workshops. Changing it re-ranks every open request.")
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
        cc1.markdown(f"⛔ **{desk.name(wid)}** · no new work  \n<small>set by {src['by']} in {src['source']}</small>", unsafe_allow_html=True)
        if cc2.button("Lift", key=f"lift_{wid}"):
            desk.lift_constraint(wid)
            flash(f"Lifted the constraint on {desk.name(wid)}; open requests re-ranked")
            st.rerun()

    st.subheader("Workshop queues")
    q = desk.ledger.queues()
    st.dataframe(pd.DataFrame([{"Workshop": desk.name(w), "Queue days": round(v, 1), "Status": desk.W[w].status} for w, v in q.items()]),
                 hide_index=True, width="stretch")
    if st.session_state.get("llm_client"):
        c = st.session_state.llm_client
        st.caption(f"GPT-5 nano spend this session: ${c.spent_usd:.4f} of ${c.budget_usd:.2f}")

if "flash" in st.session_state:
    kind, msg = st.session_state.pop("flash")
    (st.error if kind == "error" else st.success)(msg)

tab_desk, tab_ws, tab_audit, tab_sim, tab_dev = st.tabs(["Dispatch", "Workshops", "Audit log", "Simulator", "Dev check"])


# ------------------------------------------------------------------ dispatch
def fmt_date(s: str) -> str:
    return pd.Timestamp(s).strftime("%a %d %b") if s else "-"


def candidate_frame(d: dict) -> pd.DataFrame:
    rows = []
    for i, c in enumerate(d["candidates"]):
        rows.append({
            "": "★" if c["workshop_id"] == d["recommended"] else "",
            "Workshop": c["name"],
            "Back": fmt_date(c["promised_date"]),
            "On time": "✅" if c["on_time"] else f"❌ {c['late_days']}d late",
            "Days": round(c["finish_days"], 1),
            "Queue": round(c["queue_days"], 1),
            "Work": round(c["work_days"], 1),
            "Rework": round(c["rework_days"], 1),
            "Transport": int(c["lead_days"]),
            "Cost": int(round(c["cost"])),
            "Defect": f"{c['defect_rate']:.0%}",
        })
    return pd.DataFrame(rows)


with tab_desk:
    if not desk.decisions:
        st.info("Click **Load morning inbox** in the sidebar to receive the 30 chat messages from 1 April, or type a new message below.")
    desk.refresh_all()
    decisions = list(desk.decisions.values())

    left, right = st.columns([5, 7], gap="large")
    with left:
        counts = {s: sum(1 for d in decisions if d["status"] == s) for s in STATUS_LABEL}
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("To confirm", counts["awaiting_confirmation"])
        m2.metric("Need decision", counts["awaiting_decision"] + counts["refused"])
        m3.metric("Ask requester", counts["needs_reply"])
        m4.metric("Dispatched", counts["committed"])

        show = st.segmented_control("Show", ["Open", "All", "Done"], default="Open", key="inbox_filter")
        if show == "Open":
            view = [d for d in decisions if desk.is_open(d)]
        elif show == "Done":
            view = [d for d in decisions if not desk.is_open(d)]
        else:
            view = decisions
        view.sort(key=lambda d: (OPEN_FIRST.index(d["status"]) if d["status"] in OPEN_FIRST else 9, d["timestamp"] or ""))

        inbox = pd.DataFrame([{
            "ID": d["request_id"], "Time": d["timestamp"], "From": d["requester"],
            "Order": d["order_id"] or "?",
            "Next step": STATUS_LABEL[d["status"]][0],
            "Message": (d["raw_text"][:70] + "…") if len(d["raw_text"]) > 70 else d["raw_text"],
        } for d in view])
        if len(inbox):
            ev = st.dataframe(inbox, hide_index=True, width="stretch", on_select="rerun", selection_mode="single-row",
                              key=f"inbox_{show}", height=min(38 + 35 * len(inbox), 560))
            rows = ev.selection.rows if ev and ev.selection else []
            if rows:
                st.session_state.selected = inbox.iloc[rows[0]]["ID"]
            if st.session_state.selected not in desk.decisions:
                st.session_state.selected = inbox.iloc[0]["ID"]
        else:
            st.caption("Nothing here.")

        with st.form("new_message", clear_on_submit=True):
            st.markdown("**New message**")
            fc1, fc2 = st.columns([1, 3])
            sender = fc1.selectbox("From", SENDERS, label_visibility="collapsed")
            text = fc2.text_input("Message", placeholder="e.g. ORD-066 — 1000 polo shirts, due Apr 20", label_visibility="collapsed")
            if st.form_submit_button("Send to desk") and text.strip():
                d = desk.new_message(sender, text.strip())
                st.session_state.selected = d["request_id"]
                st.rerun()

    with right:
        rid = st.session_state.selected
        if not rid or rid not in desk.decisions:
            st.caption("Select a message to see the recommendation.")
        else:
            d = desk.decisions[rid]
            label, color = STATUS_LABEL[d["status"]]
            with st.container(border=True):
                h1, h2 = st.columns([4, 2])
                h1.markdown(f"#### {d['request_id']} · {d['timestamp']} · {d['requester']}")
                h2.badge(label, color=color)
                st.markdown(f"> {d['raw_text']}")
                p = d["parsed"]
                facts = [x for x in [
                    f"Order **{d['order_id']}**" if d["order_id"] else None,
                    f"{d['batch']['category']} · **{d['batch']['pieces']}** pcs · due **{fmt_date(d['batch']['due_date'])}**" if d["batch"] else None,
                    f"wants **{p['preference'].replace('_', ' ')}**" if p["preference"] != "none" else None,
                    f"suggested **{desk.name(p['forced_workshop'])}**" if p["forced_workshop"] else None,
                    "avoid " + ", ".join(f"**{desk.name(w)}**" for w in p["excluded_workshops"]) if p["excluded_workshops"] else None,
                ] if x]
                st.caption(" · ".join(facts) + f"  ·  parsed by {p['parser']}")

                # the one line the dispatcher must see in three seconds
                if d["status"] == "committed":
                    fe = d["final_estimate"]
                    st.success(f"**Dispatched to {desk.name(d['confirmed_workshop'])}** · back {fmt_date(fe['promised_date'])}"
                               + ("" if fe["on_time"] else f" · {fe['late_days']} days late (accepted)") + f" · audit {d['committed']}")
                elif d["subtype"] == "allocate":
                    best = d["candidates"][0]
                    st.success(f"★ **{best['name']}** · back **{fmt_date(best['promised_date'])}** · on time · "
                               f"{best['finish_days']:.1f} days · cost {best['cost']:.0f}")
                elif d["subtype"] == "no_on_time_option":
                    if d["candidates"]:
                        best = d["candidates"][0]
                        st.warning(f"▲ **No workshop makes {fmt_date(d['batch']['due_date'])}.** Earliest: **{best['name']}**, "
                                   f"back {fmt_date(best['promised_date'])}, **{best['late_days']} days late**")
                    else:
                        st.warning("▲ No eligible workshop at all")
                elif d["subtype"] == "ineligible_suggestion":
                    st.error(f"✕ **{desk.name(d['refused_workshop'])} can't take this.** "
                             + (f"Alternative: **{d['candidates'][0]['name']}**, back {fmt_date(d['candidates'][0]['promised_date'])}"
                                + ("" if d["candidates"][0]["on_time"] else f", {d['candidates'][0]['late_days']} days late")
                                if d["candidates"] else "No eligible alternative."))
                elif d["official_behaviour"] == "clarify":
                    st.info("? **Need an answer from the requester before dispatching**")
                else:
                    st.info("ⓘ **The data can't answer this**")

                st.write(d["explanation"])
                nc = d["number_check"]
                st.caption(("✅ every number above comes from a tool output" if nc["ok"] else f"⚠ untraced numbers: {nc['untraced']}")
                           + (f" · {len(d['tool_calls'])} tool calls" if d["tool_calls"] else ""))
                for fl in d["flags"]:
                    st.caption(f"• {fl}")

            # ---- candidates
            if d["candidates"]:
                st.markdown("**Eligible workshops** · ranked by objective " + f"`{desk.alloc.objective}`")
                st.dataframe(candidate_frame(d), hide_index=True, width="stretch")
            blocked = [e for e in d["eligibility"] if not e["eligible"]]
            if blocked:
                with st.expander(f"Not eligible ({len(blocked)})"):
                    for e in blocked:
                        st.markdown(f"- **{e['name']}** — {e['reason']}")

            # ---- actions
            st.markdown("**Action**")
            if d["status"] == "committed":
                rec = next(r for r in desk.ledger.records if r["audit_id"] == d["committed"])
                others = [c for c in d["candidates"] if c["workshop_id"] != d["confirmed_workshop"]]
                if others:
                    a1, a2 = st.columns([3, 2])
                    target = a1.selectbox("Reassign to", [c["workshop_id"] for c in others], format_func=desk.name, key=f"re_{rid}")
                    if a2.button("Reassign", key=f"reb_{rid}", width="stretch"):
                        act(desk.reassign, rec["audit_id"], target, ok=f"Reassigned to {desk.name(target)}")
                        st.rerun()
                with st.expander("Audit record"):
                    st.json(rec, expanded=False)

            elif d["subtype"] in ("allocate", "ineligible_suggestion", "no_on_time_option") and d["candidates"]:
                best = d["candidates"][0]
                late = not best["on_time"]
                b1, b2 = st.columns(2)
                primary = (f"Accept delay · send to {best['name']}" if late else f"Confirm {best['name']}")
                if b1.button(primary, type="primary", key=f"ok_{rid}", width="stretch"):
                    act(desk.confirm, rid, best["workshop_id"], accept_late=late, ok=f"{rid} dispatched to {best['name']}")
                    st.rerun()
                alt = [c for c in d["candidates"][1:]]
                if alt:
                    target = b2.selectbox("Or choose", [c["workshop_id"] for c in alt], format_func=lambda w: next(
                        f"{c['name']} · back {fmt_date(c['promised_date'])}" + ("" if c["on_time"] else f" · {c['late_days']}d late")
                        for c in alt if c["workshop_id"] == w), key=f"alt_{rid}", label_visibility="collapsed")
                    tc = next(c for c in alt if c["workshop_id"] == target)
                    if b2.button(f"Send to {tc['name']}", key=f"altb_{rid}", width="stretch"):
                        act(desk.confirm, rid, target, accept_late=not tc["on_time"], ok=f"{rid} dispatched to {tc['name']}")
                        st.rerun()
                if late:
                    c1, c2 = st.columns(2)
                    if c1.button("Renegotiate due date", key=f"neg_{rid}", width="stretch"):
                        act(desk.mark, rid, "renegotiating", ok=f"{rid} marked: renegotiating with the customer")
                        st.rerun()
                    if c2.button("Escalate to Boss", key=f"esc_{rid}", width="stretch"):
                        act(desk.mark, rid, "escalated", ok=f"{rid} escalated")
                        st.rerun()

            elif d["official_behaviour"] == "clarify" and desk.is_open(d):
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
                        st.rerun()
                with st.form(f"reply_{rid}", clear_on_submit=True):
                    ans = st.text_input(f"{d['requester']}'s answer", placeholder="e.g. ORD-066, new due date Apr 20")
                    r1, r2 = st.columns(2)
                    if r1.form_submit_button("Process answer", type="primary", width="stretch") and ans.strip():
                        new = act(desk.follow_up, rid, ans.strip())
                        if new:
                            st.session_state.selected = new["request_id"]
                        st.rerun()
                    if r2.form_submit_button("Question sent, wait", width="stretch"):
                        act(desk.mark, rid, "reply_sent", ok=f"{rid}: waiting for {d['requester']}")
                        st.rerun()

            elif d["subtype"] == "not_in_data" and desk.is_open(d):
                st.code(d["explanation"], language=None, wrap_lines=True)
                if st.button("Answer sent", key=f"ans_{rid}", type="primary"):
                    act(desk.mark, rid, "answer_sent", ok=f"{rid} closed")
                    st.rerun()
            else:
                st.caption(f"Closed: {STATUS_LABEL[d['status']][0]}")

            with st.expander("Tool calls behind this recommendation"):
                for t in d["tool_calls"]:
                    st.markdown(f"`{t['tool']}` · input `{json.dumps(t.get('input'), default=str)}`")
                    st.json(t.get("output"), expanded=False)


# ------------------------------------------------------------------ workshops
with tab_ws:
    st.subheader("Workshop register")
    q = desk.ledger.queues()
    committed = {}
    for r in desk.ledger.records:
        if r["status"] == "committed":
            committed[r["workshop_id"]] = committed.get(r["workshop_id"], 0) + r["pieces"]
    reg = pd.DataFrame([{
        "ID": w.workshop_id, "Name": w.name, "Makes": " + ".join(sorted(w.makes)), "Status": w.status,
        "Pcs/day": w.capacity, "Transport days": w.lead_days, "Defect": f"{w.defect_rate:.0%}", "Cost/pc": w.cost,
        "Max batch": str(w.max_batch) if w.max_batch else "no cap", "Queue now (days)": round(q[w.workshop_id], 1),
        "Sent today (pcs)": committed.get(w.workshop_id, 0),
        "Standing constraint": f"no new work ({desk.session_excl[w.workshop_id]['by']})" if w.workshop_id in desk.session_excl else "",
        "Notes": w.notes,
    } for w in desk.W.values()])
    st.dataframe(reg, hide_index=True, width="stretch")
    st.bar_chart(reg, x="Name", y="Queue now (days)", horizontal=True, height=280)

    st.subheader("Who can take a batch?")
    wc1, wc2 = st.columns(2)
    cat = wc1.selectbox("Category", ["TOPS", "ACCESSORIES"])
    pcs = wc2.number_input("Pieces", min_value=1, max_value=5000, value=1500, step=100)
    from kernel.register import eligibility_table  # noqa: E402
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
            "Back": r["estimate"]["promised_date"], "Due": r["due_date"],
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
def run_sim(seed: int, shock: bool) -> pd.DataFrame:
    from simulate import Simulator, random_choice, greedy_biggest, cheapest
    from run_baselines import summarise
    from kernel.allocator import Allocator, earliest_finish
    sim = Simulator(shock=shock, seed=seed)
    pols = [("random", random_choice, "official baseline"), ("greedy_biggest", greedy_biggest, "official baseline"),
            ("cheapest", cheapest, "official baseline"), ("earliest_finish", earliest_finish, "ten-line heuristic")]
    pols += [(f"cfg:{o}", Allocator(o), "our allocator") for o in OBJECTIVES]
    rows = []
    for name, pol, kind in pols:
        r = summarise(name, sim.run(pol, name))
        rows.append({"Policy": name, "Kind": kind, "% late": r["pct_late"], "Mean days": r["mean_days"], "P90 days": r["p90_days"],
                     "% defect": r["pct_defect"], "Cost": r["cost"], "Max share %": r["max_share"]})
    return pd.DataFrame(rows)


with tab_sim:
    st.subheader("Shared simulator · 120 orders replayed")
    st.caption("Runs the untouched harness/simulate.py. Official baselines, the ten-line heuristic and every objective configuration.")
    s1, s2, s3 = st.columns([1, 1, 2])
    seed = s1.number_input("Seed", value=5105, step=1)
    shock = s2.toggle("Shock (a workshop closes days 30–44)")
    df = run_sim(int(seed), bool(shock))
    st.dataframe(df, hide_index=True, width="stretch")
    st.bar_chart(df, x="Policy", y="% late", color="Kind", horizontal=True, height=320)
    st.caption("Command-line equivalent: `python harness/run_baselines.py --seed " + str(int(seed)) + (" --shock`" if shock else "`"))


# ------------------------------------------------------------------ dev check
with tab_dev:
    st.subheader("Development check against the draft gold")
    st.warning("This shows the expected answer for all 30 messages. **Don't open it before independent classification is handed in.** "
               "The draft gold and the router share an author, so agreement here is not an evaluation result.")
    if st.checkbox("I have handed in my independent classification"):
        replay = Desk(objective=desk.alloc.objective)
        for ln in inbox_lines():
            replay.handle(ln)
        s = score(replay.decisions)
        if not s["available"]:
            st.caption("No draft gold found in eval/draft/.")
        else:
            d1, d2, d3 = st.columns(3)
            d1.metric("Behaviour", f"{s['behaviour']}/{s['n']}")
            d2.metric("Workshop", f"{s['workshop']}/{s['workshop_n']}")
            d3.metric("Numbers traced", f"{s['numbers']}/{s['n']}")
            st.dataframe(pd.DataFrame(s["rows"]), hide_index=True, width="stretch")
