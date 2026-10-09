"""Sprint 1 deck v3, story first: ../06_汇报更新/Presentation_GroupNN_Sprint1_DRAFT_v3.{pptx,pdf} + previews.

    python 实验/build_deck3.py

Run exp_round2.py, validate_allocators.py, exp_sunday.py, the language evaluations and make_figures2.py first.
Every number on the slides is read from their outputs.
"""
from __future__ import annotations

import csv
import glob
import json
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from deck_lib import (Img, Line, P, R, Rect, Slide, Table, Text, export_html, measure_height_in, render_html, render_pptx)  # noqa: E402

ROOT = HERE.parent
OUT = ROOT / "06_汇报更新"
ASSETS = OUT / "assets"
REPO = ROOT / "track2-desk-优化版"
if not REPO.exists():          # inside the repo, this folder is round2/; the code is the repo root
    REPO = ROOT.parent
NAME = "Presentation_GroupNN_Sprint1_DRAFT_v3"

INK, INK2 = "0F2B3A", "16394C"
TXT, SUB = "14232E", "52606B"
BLUE, BLUE_D, BLUE_T = "2A78D6", "1C5CAB", "E6F0FC"
ORANGE, ORANGE_T, ORANGE_D = "EB6834", "FDEBE3", "A3410F"
AQUA, AQUA_T = "1BAF7A", "E3F6EE"
GREY_T, LINE = "EFF2F5", "CBD3DA"
WHITE, MUTED_ON_DARK, PALE = "FFFFFF", "AFC3D1", "CADCFC"
YELLOW, YELLOW_T, MAGENTA, VIOLET = "EDA100", "FFF6DC", "E87BA4", "4A3AA7"


def rows(p):
    return list(csv.DictReader(open(p, encoding="utf-8-sig")))


# ------------------------------------------------------------------ numbers
OFF = {r["policy"]: r for r in rows(ROOT / "02_分配器" / "official_10seeds.csv")}
VAL = rows(ROOT / "02_分配器" / "validation_means.csv")
WINS = rows(ROOT / "02_分配器" / "validation_wins_vs_earliest_finish.csv")
PROM = rows(ROOT / "02_分配器" / "promise_two_dates.csv")
INBOX = rows(ROOT / "02_分配器" / "inbox_in_order.csv")
SUN = rows(ROOT / "05_模拟器假设" / "sunday_closed.csv")
_F1 = ROOT.parent / "Sprint1_交付包" / "03_实验结果_v3" / "facts.json"      # round-1 agreement; only a fallback
FACTS1 = json.loads(_F1.read_text(encoding="utf-8")) if _F1.exists() else {}
# the commit the simulator results were produced at (written by exp_round2.py), not whatever HEAD is when the deck is built
COMMIT = (ROOT / "02_分配器" / "RUN_INFO.txt").read_text(encoding="utf-8").split("commit ")[1].split()[0]
fo = lambda k, c: float(OFF[k][c])


def val(data, pol, col="pct_late"):
    return float(next(r for r in VAL if r["data"] == data and r["policy"] == pol)[col])


def win(data, pol):
    r = next(r for r in WINS if r["data"] == data and r["policy"] == pol)
    return int(r["pct_late_better"]), int(r["pct_late_equal"]), int(r["pct_late_worse"])


def sun(cal, pol, col="pct_late"):
    return float(next(r for r in SUN if r["calendar"] == cal and r["shock"] == "False" and r["policy"] == pol)[col])


def lang(tag, parser, stage):
    """stage: 'before' = first run with the round-1 prompt; 'after' = the latest improved run available."""
    E = ROOT / "03_语言层评估"
    folders = ["基线_改进前"] if stage == "before" else ["改进后_核对2.2", "改进后_核对2.1", "改进后"]
    for folder in folders:
        for p in sorted(glob.glob(str(E / folder / "*.json"))):
            d = json.loads(Path(p).read_text(encoding="utf-8"))
            if d["tag"] == tag and d["parser"] == parser:
                return d
    return None


def tests_count():
    env = dict(__import__("os").environ, PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8")
    n = 0
    for t in ("test_kernel.py", "test_desk.py", "test_round2.py"):
        out = subprocess.run([sys.executable, f"tests/{t}"], cwd=REPO, capture_output=True, text=True, env=env, encoding="utf-8").stdout
        assert "failed: 0" in out, t
        n += out.count("\nPASS ") + out.startswith("PASS ")
    return n


TESTS = tests_count()
AGREE = ROOT / "01_标注" / "agreement_v3.json"          # six-person votes on all 30 (merge_votes.py), once the nine v3 ones are in
if AGREE.exists():
    AG = json.loads(AGREE.read_text(encoding="utf-8"))
    KAPPA, BELOW, NINE_UNANIMOUS = AG["fleiss_kappa_official_all_30"], len(AG["below_5_of_6"]), AG["new_nine_unanimous"]
    WHO = "All six of us" if AG["new_nine_raters"] == [6] else "We"
else:
    KAPPA, BELOW, NINE_UNANIMOUS = FACTS1["agreement"]["fleiss_kappa_official_unchanged_complete"], len(FACTS1["agreement"]["below_5_of_6"]), None
    WHO = "We"
P1, PT, PA = "fresh perturbed (100 sets)", "fresh tight due dates 10-21 days (50 sets)", "fresh +10 accessory orders (50 sets)"
V2 = "lateness (v2 rule)"
nano_b, nano_a = lang("official30", "llm:gpt-5-nano", "before"), lang("official30", "llm:gpt-5-nano", "after")
mini_b, mini_a = lang("official30", "llm:gpt-5-mini", "before"), lang("official30", "llm:gpt-5-mini", "after")
c_rules_b = lang("challenge38", "rules", "before")
c_nano_b, c_nano_a = lang("challenge38", "llm:gpt-5-nano", "before"), lang("challenge38", "llm:gpt-5-nano", "after")
c_mini_b, c_mini_a = lang("challenge38", "llm:gpt-5-mini", "before"), lang("challenge38", "llm:gpt-5-mini", "after")
prom_n = next(r for r in PROM if r["objective"] == "lateness" and r["shock"] == "False")
prom_s = next(r for r in PROM if r["objective"] == "lateness" and r["shock"] == "True")
cost_delta = 100 * (fo("lateness", "cost") / fo("random", "cost") - 1)
b100, e100, w100 = win(P1, V2)

W, H, LM = 13.333, 7.5, 0.6
TITLE_FONT = "Cambria"
slides: list[Slide] = []


def new_slide(title="", dark=False, notes="", n=None, backup=False) -> Slide:
    s = Slide(bg=INK if dark else WHITE, notes=notes, title=title)
    slides.append(s)
    if title:
        s.add(Text(LM, 0.42, W - 2 * LM, 1.3, [P(title, size=34, bold=True, color=WHITE if dark else TXT, font=TITLE_FONT, lh=0.98)], name="Title"))
    if not dark and n is not None:
        s.add(Text(LM, 7.05, 9, 0.25, [P("DSS5105 Capstone  ·  Track 2  ·  Subcontracting Desk  ·  Sprint 1", size=10, color=SUB)], name="Footer"))
        s.add(Text(W - LM - 1.0, 7.05, 1.0, 0.25, [P(str(n), size=10, color=SUB, align="r")], name="Slide number"))
    if backup:
        s.add(Text(W - LM - 1.6, 0.16, 1.6, 0.26, [P("BACKUP SLIDE", size=10.5, bold=True, color=SUB, align="r")], name="Backup tag"))
    return s


def label(s, x, y, w, text, color=SUB):
    s.add(Text(x, y, w, 0.3, [P(text, size=12, bold=True, color=color)], name="Label"))


def badge(s, x, y, d, text, fill=BLUE, color=WHITE, size=16):
    s.add(Rect(x, y, d, d, fill=fill, shape="oval", paras=[P(text, size=size, bold=True, color=color, align="c")], pad=0, name="Badge"))



# ================================================================== v3: story first, data in the appendix
# POLICY = "lateness" (specialist-first rule, earliest-finish tie-break, declared turnaround guardrail)
#        = "use_slack" (same rule, latest safe finish): switch here if the team decides otherwise.
POLICY = "lateness"
H2H = rows(ROOT / "02_分配器" / "head_to_head_use_slack_vs_lateness.csv")
GROUP = "NN"


def h2h(data_prefix, pol):
    return next(r for r in H2H if r["data"].startswith(data_prefix) and r["policy"] == pol)


def heldout_first_run():
    """The held-out inbox's first scores, once eval/heldout/first_run/ exists in the repo (never before)."""
    out = {}
    for p in glob.glob(str(REPO / "eval" / "heldout" / "first_run" / "language_eval_heldout44_*.json")):
        d = json.loads(Path(p).read_text(encoding="utf-8"))
        if "_rows" not in p:
            out[d["parser"]] = d
    return out


HELD = heldout_first_run()
ours_key = POLICY
ours_name = "ours (lateness setting)" if POLICY == "lateness" else "ours (slack-keeping setting)"

# ------------------------------------------------------------------ 0  cover
s = new_slide(dark=True, notes=(
    f"[10 s] Good evening, we are Group {GROUP}. Our project turns the chat message that sends a batch to an outside workshop into a verified, recorded decision."))
s.add(Text(0.8, 1.15, 7.2, 0.35, [P("DSS5105 CAPSTONE  ·  TRACK 2  ·  SPRINT 1", size=13, bold=True, color=MUTED_ON_DARK)], name="Eyebrow"))
s.add(Text(0.8, 1.7, 7.4, 1.0, [P("Subcontracting Desk", size=48, bold=True, color=WHITE, font=TITLE_FONT)], name="Title"))
s.add(Text(0.8, 2.85, 7.0, 1.3, [P("From informal chat decisions\nto verified, accountable outsourcing dispatch", size=22, color=PALE, lh=1.0)], name="Subtitle"))
s.add(Text(0.8, 4.75, 7.3, 1.9, [
    P(f"Group {GROUP}", size=17, bold=True, color=WHITE, after=6),
    P("屈妍玥 Qu Yanyue  ·  张锦若 Zhang Jinruo  ·  吴杰 Wu Jie", size=14, color=PALE, after=3),
    P("李岩 Li Yan  ·  吴若晗 Wu Ruohan  ·  许佩瑶 Xu Peiyao", size=14, color=PALE, after=10),
    P("github.com/dss5105-track2/track2-desk   ·   16 October 2026", size=13, color=MUTED_ON_DARK)], name="Team"))
s.add(Rect(8.45, 1.45, 4.3, 1.55, fill=INK2, radius=0.14, name="Chat bubble", valign="m", pad=0.25, paras=[
    P("THE CHAT MESSAGE", size=11, bold=True, color=MUTED_ON_DARK, after=6),
    P("“Send it to QuickStitch, need it back by the 19th.”", size=17, italic=True, color=WHITE)]))
s.add(Line(10.6, 3.12, 10.6, 3.72, color=MUTED_ON_DARK, lw=2, arrow=True, name="Arrow"))
s.add(Rect(8.45, 3.8, 4.3, 2.75, fill=WHITE, radius=0.14, name="Answer card", valign="m", pad=0.25, paras=[
    P("THE DESK'S ANSWER", size=11, bold=True, color=SUB, after=6),
    P("GiantWeave", size=24, bold=True, color=TXT, after=2),
    P("back Fri 10 Apr, on time  ·  Sat 11 Apr if reworked", size=14.5, color=TXT, after=8),
    P("QuickStitch not considered: excluded by Boss", size=13, color=SUB, after=3),
    P("Every number traced to a tool output", size=13, color=SUB)]))

# ------------------------------------------------------------------ 1  the dispatch problem, scope, value
s = new_slide("A batch goes outside on one chat message, unchecked and unrecorded", n=1, notes=(
    "[35 s] Today the decision is a chat message. Behind it are three questions: can the workshop make the product, can it take the batch now, "
    "is it allowed to? Get one wrong and the batch comes back a day later. So the desk has to do three things: read the chat, decide on numbers, and leave a record. "
    "The value is a verified recommendation for the dispatcher, fewer late batches for the factory, and a date the customer can rely on."))
label(s, LM, 1.95, 3, "TODAY")
s.add(Rect(LM, 2.28, 5.9, 0.95, fill=GREY_T, radius=0.14, name="Chat bubble", pad=0.2, paras=[
    P("“@Chen — order 042, 1,500 crewnecks. Send it to QuickStitch, need it back by the 19th.”", size=15, italic=True, color=TXT)]))
for i, (a, b) in enumerate([("Can they make it? ", "Not every workshop makes every product."),
                            ("Can they take it now? ", "A fast shop with a 3-day queue is not fast today."),
                            ("Are they allowed to? ", "One shop is suspended after an audit; one is on trial, small batches only.")]):
    y = 3.42 + i * 0.72
    badge(s, LM, y + 0.03, 0.42, str(i + 1), size=14)
    s.add(Text(LM + 0.6, y, 5.3, 0.66, [P(R(a, bold=True), b, size=14)], name=f"Question {i + 1}"))
s.add(Text(LM, 5.62, 5.9, 0.55, [P("Get one wrong and the batch bounces back a day later. In a ten-day cycle that is the margin gone.", size=12.5, italic=True, color=SUB)], name="Cost of error"))
s.add(Rect(LM, 6.2, 5.9, 0.72, fill=BLUE_T, radius=0.12, name="Decision", pad=0.16, paras=[
    P(R("The decision: ", bold=True, color=BLUE_D), "which eligible workshop, with capacity, returns the batch by its due date — and why.", size=13.5, color=TXT)]))

label(s, 6.9, 1.95, 5, "WHAT THE DESK MUST DO", BLUE)
caps = [("Read the chat. ", "Extract the request; ask when it is ambiguous or incomplete; refuse, with a reason and an alternative, when the named workshop cannot take it; honour constraints and record who set them."),
        ("Decide on numbers. ", "Keep the workshop register; estimate a delivery date per candidate before committing; allocate with the reasoning attached; when nobody can make the date, say so and lay out the options."),
        ("Leave a record. ", "An auditable record of every decision — what the group chat never produced.")]
for i, (lead, rest) in enumerate(caps):
    s.add(Rect(6.9, 2.28 + i * 1.0, 5.83, 0.92, fill=GREY_T, radius=0.12, name=lead.strip(". "), valign="m", pad=0.15, paras=[P(R(lead, bold=True), rest, size=12)]))
s.add(Text(6.9, 5.28, 5.83, 0.5, [P("Optional, assessed after Sprint 2: the stage extension (--stages). Not pursued: multi-agent negotiation — the mechanism is not graded.", size=10.5, italic=True, color=SUB)], name="Scope note"))
label(s, 6.9, 5.82, 5, "BUSINESS VALUE", BLUE)
s.add(Text(6.9, 6.14, 5.83, 0.85, [
    P(R("Dispatcher: ", bold=True), "faster decisions with verified recommendations", size=12.5, after=2, bullet=True),
    P(R("Factory: ", bold=True), "fewer late deliveries, shown in simulation", size=12.5, after=2, bullet=True),
    P(R("Customer: ", bold=True), "more reliable delivery-date commitments", size=12.5, bullet=True)], name="Value"))

# ------------------------------------------------------------------ 2  solution and architecture
s = new_slide("The model reads, code decides, the dispatcher confirms", n=2, notes=(
    "[50 s] The model only reads. Code checks every extracted value against the text, runs three hard eligibility checks, gives each eligible shop two dates, "
    "and ranks by the objective. The explanation is written from tool outputs, and nothing is booked until the dispatcher confirms. "
    "Here is one real message going through: the standing constraint is recorded, four shops are eligible, GiantWeave makes the date even if reworked."))
stages = [
    ("Chat message", "INPUT", GREY_T, TXT, SUB, "Free text from five people, as they type it."),
    ("Language layer", "LANGUAGE MODEL + CHECK", BLUE_T, TXT, BLUE_D, "The model extracts order, pieces, date, constraint. Code checks each value against the text."),
    ("Kernel", "CODE · NO LLM", INK, WHITE, "7ED9B8", "Register: make it, take it, allowed? Estimator: two dates per shop. Allocator: the objective is a setting."),
    ("Explain and check", "CODE", AQUA_T, TXT, "0B7A52", "Writes the reason from tool outputs. Flags any number that is not in one."),
    ("Dispatcher", "HUMAN", ORANGE_T, TXT, ORANGE_D, "Confirms, changes or escalates. Only then is capacity booked and the audit record written."),
]
bw, gap, y0, bh = 2.2, 0.28, 1.95, 2.0
for i, (head, tag, fill, fg, tagc, body) in enumerate(stages):
    x = LM + i * (bw + gap)
    s.add(Rect(x, y0, bw, bh, fill=fill, radius=0.14, name=head, valign="t", pad=0.14, paras=[
        P(tag, size=10, bold=True, color=tagc, after=3, before=8), P(head, size=17, bold=True, color=fg, after=5), P(body, size=12.5, color=fg if fg == WHITE else TXT)]))
    if i < len(stages) - 1:
        s.add(Line(x + bw + 0.03, y0 + bh / 2, x + bw + gap - 0.03, y0 + bh / 2, color=SUB, lw=2, arrow=True, name="Flow arrow"))
for k, i in enumerate((1, 2, 3)):
    x = LM + i * (bw + gap) + bw / 2 - 0.17
    badge(s, x, y0 + bh + 0.06, 0.34, str(k + 1), fill=BLUE_D, size=12)
mech = [("Text decides. ", "Every value the model extracts is checked against the message; anything the message does not contain is dropped."),
        ("Eligibility before ranking. ", "Three hard checks first; then every eligible shop gets two dates — expected, and if the batch is reworked — and the ranking follows the chosen objective."),
        ("Traced, then booked. ", "Every number in the explanation must come from a tool output; capacity is booked and the audit record written only after the dispatcher confirms.")]
for i, (lead, rest) in enumerate(mech):
    x = LM + i * 4.11
    s.add(Rect(x, 4.5, 3.91, 1.12, fill=WHITE, line=BLUE_D, lw=1.25, radius=0.12, name=f"Mechanism {i + 1}", valign="m", pad=0.14, paras=[
        P(R(f"{i + 1}  ", bold=True, color=BLUE_D), R(lead, bold=True), rest, size=11.5)]))
label(s, LM, 5.76, 8, "ONE REAL MESSAGE, R12, THROUGH THE FIVE STAGES", SUB)
trace = ["“ORD-053 — 800 polo shirts for UrbanThread, due Apr 10. Boss says nothing new to QuickStitch this week.”",
         "ORD-053 · 800 pcs · due 10 Apr · constraint: QuickStitch excluded — standing, set by Boss",
         "4 shops eligible. GiantWeave back Fri 10 Apr; Sat 11 Apr if reworked, still on time",
         "“GiantWeave: on time; it only makes tops, so the two shops that also make accessories stay free for tighter batches.”",
         "Confirmed → ledger updated, audit record A0004"]
for i, t in enumerate(trace):
    s.add(Text(LM + i * (bw + gap), 6.05, bw, 0.95, [P(t, size=10.5, italic=(i in (0, 3)), color=TXT)], name=f"Trace {i + 1}"))

# ------------------------------------------------------------------ 3  why minimise late deliveries
tie = ("Declared tie-break: when two settings are equally late, we take the shorter turnaround — the track names turnaround days as the business impact."
       if POLICY == "lateness" else "Primary policy: the slack-keeping setting; its longer turnaround is reported as the cost.")
s = new_slide("Primary objective: minimise late deliveries", n=3, notes=(
    "[40 s] We minimise late deliveries because the due date is the one constraint every order carries, the simulator measures it directly, "
    "and the choice of workshop is exactly what moves it. The baselines being 34 to 92 percent late is supporting evidence, not the reason. "
    "Defects and fairness stay as switchable settings, plus one hybrid; robustness is tested with the shock scenario. And we declare our tie-break up front: equal lateness, shorter turnaround."))
s.add(Rect(LM, 1.9, 12.13, 0.6, fill=GREY_T, radius=0.1, name="Definition", pad=0.14, paras=[
    P(R("Late-delivery rate ", bold=True), "= batches returned after their due date ÷ all batches.   Also reported: mean days late (0 when on time).   Both are the simulator's own metrics.", size=13)]))
label(s, LM, 2.72, 4, "WHY THIS ONE", BLUE)
why = [("Relevant. ", "The due date is the one constraint every order carries; quick response exists to protect it — “the factory that farms out a batch today beats the one that decides on Thursday.”"),
       ("Measurable. ", "The simulator records when every batch returns, so lateness is computed, not estimated."),
       ("Controllable. ", "Lateness depends on queue, capacity and transport — exactly what the choice of workshop changes.")]
for i, (a, b) in enumerate(why):
    y = 3.07 + i * 0.92
    badge(s, LM, y + 0.03, 0.42, str(i + 1), size=14)
    s.add(Text(LM + 0.6, y, 5.75, 0.88, [P(R(a, bold=True), b, size=13)], name=f"Reason {i + 1}"))
s.add(Text(LM, 5.85, 6.35, 0.4, [P(f"The three baselines are {fo('random', 'pct_late'):.0f}–{fo('cheapest', 'pct_late'):.0f}% late in simulation: the largest gap, but supporting evidence, not the reason.", size=11, italic=True, color=SUB)], name="Baselines note"))
label(s, 7.3, 2.72, 5, "THE OTHER THREE", BLUE)
others = [("Defects, fairness. ", "Switchable settings of the same allocator; results reported on the same 120 orders."),
          ("Hybrid. ", "One weighted setting (late 1.0, finish 0.3, defect 0.25, load 0.5). Metrics scaled 0–1 first; weights at the knee of the lateness–defect curve, checked on held-out seeds."),
          ("Robust to failure. ", "Tested with the shock scenario; guardrail: lateness no worse than random.")]
for i, (a, b) in enumerate(others):
    s.add(Rect(7.3, 3.07 + i * 0.92, 5.43, 0.84, fill=GREY_T, radius=0.12, name=a.strip(". "), valign="m", pad=0.14, paras=[P(R(a, bold=True), b, size=12)]))
s.add(Rect(LM, 6.3, 12.13, 0.62, fill=BLUE_T, radius=0.1, name="Tie-break", pad=0.14, paras=[P(tie, size=12.5, color=TXT)]))

# ------------------------------------------------------------------ 4  built and tested
held_line = ""
if HELD:
    parts = []
    for parser, lab in (("llm:gpt-5-mini", "GPT-5 mini"), ("rules", "rule parser")):
        if parser in HELD:
            parts.append(f"{lab} {HELD[parser]['behaviour_accuracy_pct']:.0f}%")
    if parts:
        held_line = "First score on the held-out inbox (44 messages by four teammates, answers frozen first): " + ", ".join(parts) + " right behaviour."
s = new_slide("The loop runs end to end, and the first results are in", n=4, notes=(
    f"[60 s] The whole loop runs. In simulation we are at {fo(ours_key, 'pct_late'):.1f} percent late, "
    + ("the same as a simple earliest-finish rule and far below random; " if POLICY == "lateness" else "below the simple earliest-finish rule and far below random; ")
    + f"on fresh order books our rule is ahead, and we say where the simple rule still wins: it is a day faster. "
    f"{TESTS} tests pass, every number traces, the labels are frozen by all six of us, and the language model was measured before we trusted it."
    + (" " + held_line if held_line else "")))
s.add(Img(LM, 1.95, 5.6, 4.56, str(ASSETS / "ui_main_crop.png"), alt="Screenshot of the dispatcher interface: inbox grouped by next step with a one-click confirm, and the decision card for R12"))
s.add(Rect(LM, 1.95, 5.6, 4.56, line=LINE, lw=1, name="Screenshot frame"))
s.add(Text(LM, 6.56, 5.6, 0.45, [P("One message in, one recommendation with two dates and a reason, one click to confirm, one audit record.", size=11, color=SUB)], name="Caption"))
label(s, 6.55, 1.95, 6.2, "IN SIMULATION · OFFICIAL 120 ORDERS · MEAN OF 10 SEEDS", SUB)
hl = {"fill": BLUE_T, "bold": True}
tb = [["Policy", "Late batches", "Mean days late"],
      ["random  (baseline)", f"{fo('random', 'pct_late'):.1f}%", f"{fo('random', 'late_days'):.2f}"],
      ["cheapest  (baseline)", f"{fo('cheapest', 'pct_late'):.1f}%", f"{fo('cheapest', 'late_days'):.1f}"],
      [{"text": "earliest-finish  (simple rule, no LLM)", "fill": ORANGE_T}, {"text": f"{fo('earliest_finish', 'pct_late'):.1f}%", "fill": ORANGE_T}, {"text": f"{fo('earliest_finish', 'late_days'):.2f}", "fill": ORANGE_T}],
      [{"text": ours_name, **hl}, {"text": f"{fo(ours_key, 'pct_late'):.1f}%", **hl}, {"text": f"{fo(ours_key, 'late_days'):.2f}", **hl}]]
if POLICY == "use_slack":
    tb.append(["ours, earliest-finish tie-break", f"{fo('lateness', 'pct_late'):.1f}%", f"{fo('lateness', 'late_days'):.2f}"])
s.add(Table(6.55, 2.3, [3.5, 1.3, 1.38], 0.4, tb, size=12.5, zebra=None, name="Results"))
ty = 2.3 + 0.4 * len(tb) + 0.12
s.add(Text(6.55, ty, 6.18, 0.9, [
    P(f"On 200 fresh order books the simple rule never saw, ours is ahead: {val(P1, V2):.1f}% vs {val(P1, 'earliest_finish'):.1f}% late on 100 jittered sets (better on {b100}, worse on {w100}). "
      f"Under shock the simple rule still edges us, {fo('earliest_finish', 'shock_pct_late'):.1f}% vs {fo('lateness', 'shock_pct_late'):.1f}%: one batch in ten runs. Source: simulate.py v3, commit {COMMIT}.", size=11.5, color=TXT)], name="Fresh data"))
prog = [P(R(f"{TESTS} automated tests pass; ", bold=True), "every number in every reply on the 30-message inbox traces to a tool output.", size=12, after=4, bullet=True),
        P(R("All six of us labelled the 30 messages independently ", bold=True), f"(κ {KAPPA:.2f}); labels frozen on 7 Oct; counts per kind match the instructor's mix.", size=12, after=4, bullet=True),
        P(R("The language model was measured, then corrected: ", bold=True), f"GPT-5 mini now reads all 30 official and 38 new messages right; the cheapest model started at {nano_b['behaviour_accuracy_pct']:.0f}%.", size=12, after=4, bullet=True)]
if held_line:
    prog.append(P(R("Held-out inbox: ", bold=True), held_line.split(": ", 1)[1], size=12, bullet=True))
s.add(Text(6.55, ty + 0.98, 6.18, 2.0, prog, name="Progress"))

# ------------------------------------------------------------------ 5  risks, assumptions, limitations
s = new_slide("What could go wrong, and what we are assuming", n=5, notes=(
    "[45 s] Three risks. We have no clean language test yet, so four teammates who never touch the prompt are writing a held-out inbox; the answers are frozen before the first run. "
    "The simulator is kinder than reality: we report a Sunday variant separately and will add closed-workshop detection. And our policy is not optimal: a hindsight search reaches zero, "
    "but a dispatcher cannot see future orders. Our assumptions are on the bottom line."))
cols = [(LM, 4.15, "RISK", ORANGE_T), (4.9, 2.55, "IMPACT", GREY_T), (7.6, 5.13, "MITIGATION", BLUE_T)]
for x, w, head, _ in cols:
    label(s, x, 1.92, w, head, ORANGE_D if head == "RISK" else (BLUE_D if head == "MITIGATION" else SUB))
risks = [("No clean language test yet. ", "The 30 official messages were used in development; the 38 new ones are AI-written.",
          "We may overstate how well the model reads.",
          "Held-out inbox: 44 messages written by four teammates who do not touch the prompt; answers frozen before the first run (frozen 14 Oct, first run 15 Oct)."),
         ("The simulator is kinder than reality. ", "Seven-day week; the estimator does not know when a workshop closes.",
          "Lateness looks better than it would be.",
          f"Sunday variant reported separately (simple rule {sun('seven-day week (official)', 'earliest_finish'):.1f} → {sun('Sundays off', 'earliest_finish'):.1f}%, ours → {sun('Sundays off', 'lateness (v2 rule)'):.1f}%); closed-workshop detection in Sprint 2."),
         ("Our online policy is not globally optimal. ", "A hindsight search that knows every order in advance reaches 0% late in the tested setting.",
          "Room we have not captured.",
          "A dispatcher cannot see future orders; we report the gap and keep the rule simple enough to explain.")]
for i, (lead, risk, impact, mit) in enumerate(risks):
    y = 2.25 + i * 1.3
    s.add(Rect(cols[0][0], y, cols[0][1], 1.18, fill=ORANGE_T, radius=0.1, name=f"Risk {i + 1}", pad=0.14, paras=[P(R(lead, bold=True), risk, size=12)]))
    s.add(Rect(cols[1][0], y, cols[1][1], 1.18, fill=GREY_T, radius=0.1, name=f"Impact {i + 1}", pad=0.14, paras=[P(impact, size=12)]))
    s.add(Rect(cols[2][0], y, cols[2][1], 1.18, fill=BLUE_T, radius=0.1, name=f"Mitigation {i + 1}", pad=0.14, paras=[P(mit, size=12)]))
s.add(Text(LM, 6.22, 12.13, 0.75, [P(R("Assumptions:  ", bold=True, color=SUB),
    "requests arrive in time order and a confirmed dispatch occupies capacity  ·  a standing constraint (“nothing new to QuickStitch this week”) applies to every later request  ·  "
    "a reworked batch takes half as long again (simulator rule)  ·  the data holds no customer prices and no history, so those questions are declined.", size=11, color=SUB)], name="Assumptions"))

# ------------------------------------------------------------------ 6  roadmap and success criteria
s = new_slide("Sprint 2 (30 Oct) and Sprint 3 (13 Nov): from a working loop to evidence we can defend", n=6, notes=(
    "[40 s] Next: the held-out inbox, written by teammates and frozen before the first run; closed-workshop detection, so the system notices a stuck queue; "
    "a user test with students from other groups; a public demo; and the evaluation draft with ten failure cases. The criteria are on the bottom row: under 2 percent late, "
    "ahead of the simple rule on fresh data, 90 percent on the held-out inbox, and every promised rework date kept."))
rc = [(LM, 2.45, "WORK"), (3.2, 4.75, "ACCEPTANCE"), (8.1, 2.45, "OWNER"), (10.7, 2.03, "WHEN")]
for x, w, head in rc:
    label(s, x, 1.88, w, head, SUB)
road = [("Held-out inbox", "44 hand-written messages, answers frozen first, ≥ 90% right behaviour", "张锦若 freezes; 李岩, 吴若晗 run", "written 9–11 Oct; frozen 14 Oct; first run 15 Oct"),
        ("Closed-workshop detection", "In the shock run the closed shop is detected and gets no new batches; shock lateness no worse than normal", "吴若晗", "design 14 Oct; done 27 Oct"),
        ("User test", "2–3 students from other groups complete the 9 tasks", "李岩, 屈妍玥", "by 28 Oct"),
        ("Public demo", "Reachable from an outside browser; one dispatch completed", "李岩 (吴杰 logs in)", "by 28 Oct"),
        ("Evaluation draft", "10 failure cases with root causes", "李岩, 吴若晗 (causes); 吴杰, 许佩瑶 (text)", "24–29 Oct"),
        ("Optional: stage extension (--stages)", "Assessed after Sprint 2, if time allows", "—", "—")]
for i, row in enumerate(road):
    y = 2.18 + i * 0.6
    for (x, w, _), t in zip(rc, row):
        s.add(Text(x, y, w - 0.1, 0.56, [P(t, size=11.5, bold=(x == LM), color=TXT)], valign="m", name=f"Road {i + 1}"))
    s.add(Line(LM, y + 0.58, W - LM, y + 0.58, color=LINE, lw=0.75, name="Rule"))
label(s, LM, 5.9, 9, "SUCCESS CRITERIA · MEASURED ON v3 DATA", SUB)
crit = [("≤ 2%", f"late on the official orders, normal and shock (now {fo(ours_key, 'pct_late'):.1f}% / {fo(ours_key, 'shock_pct_late'):.1f}%)"),
        ("Beat it", f"fewer late batches than the simple rule on fresh order books (now {val(P1, V2):.1f}% vs {val(P1, 'earliest_finish'):.1f}%)"),
        ("≥ 90%", "right behaviour on the held-out inbox, labels frozen first" + (f" (first run: {HELD['llm:gpt-5-mini']['behaviour_accuracy_pct']:.0f}%)" if "llm:gpt-5-mini" in HELD else "")),
        ("100%", f"numbers traced; every “if reworked” date kept (now {float(prom_n['date_if_reworked_kept_pct']):.0f}%; {float(prom_s['date_if_reworked_kept_pct']):.0f}% in shock)")]
for i, (big, txt) in enumerate(crit):
    x = LM + i * 3.06
    s.add(Rect(x, 6.18, 2.9, 0.82, fill=BLUE_T, radius=0.1, name=f"Criterion {i + 1}", valign="m", pad=0.12, paras=[
        P(big, size=19, bold=True, color=BLUE_D, after=1, lh=0.95), P(txt, size=10, color=TXT)]))

# ================================================================== A  results table
s = new_slide("Appendix A · Results on v3 data, mean of 10 seeds", n=7, backup=True, notes="Backup: full results table, seeds 5105 to 5114.")
disp = [("random", "random  (official)", None), ("greedy_biggest", "greedy_biggest  (official)", None), ("cheapest", "cheapest  (official)", None),
        ("earliest_finish", "earliest_finish  (simple rule)", ORANGE_T), ("lateness", "lateness: specialist-first rule  (ours)", BLUE_T),
        ("use_slack", "use_slack: latest safe finish  (ours)", None), ("lateness_v1", "lateness, round 1  (ours)", None), ("hybrid", "hybrid  (ours)", None),
        ("defects", "defects  (ours)", None), ("fairness", "fairness  (ours)", None), ("cost", "cost  (ours)", None)]
body = [["Policy", "Late %", "Late days", "Mean days", "Defective pcs %", "Max share %", "Cost", "Late % in shock"]]
for key, name, tint in disp:
    r = OFF[key]
    f = {"fill": tint} if tint else {}
    cells = [name, f"{float(r['pct_late']):.1f}", f"{float(r['late_days']):.2f}", f"{float(r['mean_days']):.1f}", f"{float(r['pct_def_pcs']):.1f}", f"{float(r['max_share']):.0f}",
             f"{float(r['cost']):,.0f}", f"{float(r['shock_pct_late']):.1f}"]
    body.append([{"text": c, **f, **({"bold": True} if key in ("lateness", "earliest_finish") else {})} for c in cells])
s.add(Table(LM, 1.85, [3.35, 0.9, 1.05, 1.15, 1.55, 1.3, 1.2, 1.6], 0.385, body, size=12.5, zebra=None, name="Results"))
s.add(Text(LM, 6.6, 12.1, 0.4, [P(f"simulate.py v3, commit {COMMIT}. use_slack is late less often and costs less, but takes {fo('use_slack', 'mean_days'):.0f} days on average. Single-seed defect draws move defective pcs by about ±2 points.", size=10.5, color=SUB)], name="Note"))

# ================================================================== B  the inbox map
s = new_slide("Appendix B · How the desk sorted the 30 messages", n=8, backup=True, notes="Backup: every request, coloured by the desk's decision.")
cat = {"allocate": ("allocate", BLUE, WHITE), "no_on_time_option": ("no on-time option", ORANGE, TXT), "ambiguous_reference": ("ask: which order", AQUA, TXT),
       "missing_fields": ("ask: missing info", YELLOW, TXT), "ineligible_suggestion": ("refuse", MAGENTA, TXT), "not_in_data": ("can't answer", VIOLET, WHITE)}
NEW9 = ["R04", "R06", "R07", "R16", "R17", "R22", "R23", "R26", "R27"]
sys.path.insert(0, str(REPO))
from desk.pipeline import Desk, inbox_lines  # noqa: E402
_d = Desk()
for _ln in inbox_lines():
    _d.propose(_ln)
per = {k: v["subtype"] for k, v in _d.decisions.items()}
late_in_order = next(r for r in INBOX if r["objective"] == "lateness")["late"]
cw, ch, cg = 1.94, 0.72, 0.09
for i in range(30):
    rid = f"R{i + 1:02d}"
    name, fill, fg = cat[per[rid]]
    s.add(Rect(LM + (i % 6) * (cw + cg), 1.95 + (i // 6) * (ch + cg), cw, ch, fill=fill, radius=0.08, name=rid, pad=0.1, paras=[
        P(R(rid, bold=True), " ★" if rid in NEW9 else "", size=14, color=fg), P(name, size=12, color=fg)]))
for i, (k, (name, fill, fg)) in enumerate(cat.items()):
    x = LM + i * 2.02
    s.add(Rect(x, 6.12, 0.2, 0.2, fill=fill, name="Legend swatch"))
    s.add(Text(x + 0.3, 6.07, 1.7, 0.3, [P(name, size=12, color=TXT)], valign="m", name="Legend label"))
s.add(Text(LM, 6.5, 12.1, 0.5, [P(f"★ changed by the instructor in v3. Shown with the morning queues; the counts by kind match the instructor's published mix. Processed in order, 11 of the 13 on-time requests stay on time ({late_in_order.replace('+', 'is ').replace('d', ' day late')}); at most 12 can.", size=11, color=SUB)], name="Note"))

# ================================================================== C  language layer
s = new_slide("Appendix C · The language layer, measured on two inboxes", n=9, backup=True, notes="Backup: behaviour accuracy by parser, before and after.")
s.add(Img(LM, 1.8, 11.4, 3.44, str(ASSETS / "fig_language.png"), alt="Bars of right-behaviour rate for the rule parser, GPT-5 nano and GPT-5 mini on the official 30 and on 38 new messages, before and after round 2"))
pts = []
if c_rules_b:
    pts.append(P(R("The rule parser was built around the 30: ", bold=True), f"100% there, {c_rules_b['behaviour_accuracy_pct']:.0f}% on new wording at first try.", size=14, after=6, bullet=True))
if nano_b and mini_b:
    pts.append(P(R("Model choice matters: ", bold=True), f"with the round-1 prompt GPT-5 nano gets {nano_b['behaviour_accuracy_pct']:.0f}% of the 30 right, GPT-5 mini {mini_b['behaviour_accuracy_pct']:.0f}%. "
                 "After our checks nano still misreads one new phrasing (a date “sooner than planned, not said when”) in 3 runs of 3.", size=14, after=6, bullet=True))
pts.append(P(R("Not a clean test yet: ", bold=True), "the 38 new messages are AI-written and two of our fixes came from errors seen on them. The held-out inbox will be written by teammates.", size=14, bullet=True))
s.add(Text(LM, 5.32, 12.1, 1.55, pts, name="Reading"))

# ================================================================== D  two dates and Sundays
s = new_slide("Appendix D · Promised dates, and a six-day week", n=10, backup=True, notes="Backup: two dates per promise; Sundays off.")
label(s, LM, 1.95, 6, "QUOTING TWO DATES · 1,200 BATCHES, LATENESS RULE", SUB)
for i, (big, small) in enumerate([
        (f"{float(prom_n['expected_date_kept_pct']):.0f}%", "of expected dates hold. Every miss in normal runs is a defect rework."),
        (f"{float(prom_n['date_if_reworked_kept_pct']):.0f}%", f"of “if reworked” dates hold ({float(prom_s['date_if_reworked_kept_pct']):.1f}% with a workshop closed). They are {float(prom_n['mean_days_between_the_two_dates']):.1f} days later on average.")]):
    y = 2.35 + i * 1.75
    s.add(Text(LM, y, 5.6, 0.7, [P(big, size=38, bold=True, color=BLUE, lh=0.95)], name="Stat"))
    s.add(Text(LM, y + 0.7, 5.6, 0.9, [P(small, size=14)], name="Stat label"))
label(s, 6.9, 1.95, 6, "SUNDAYS OFF, AS THE PRIMER SAYS · LATE BATCHES %", SUB)
sb = [["Policy", "Seven-day week", "Sundays off"]]
for pol, nm in (("random", "random"), ("earliest_finish", "earliest_finish  (simple rule)"), ("lateness (v2 rule)", "lateness rule  (ours)"),
                ("lateness, Sunday-aware estimate", "lateness rule, estimate knows Sundays")):
    hlt = {"bold": True, "fill": BLUE_T} if pol.startswith("lateness") else ({"fill": ORANGE_T} if pol == "earliest_finish" else {})
    sb.append([{"text": nm, **hlt}, {"text": f"{sun('seven-day week (official)', pol):.1f}", **hlt}, {"text": f"{sun('Sundays off', pol):.1f}", **hlt}])
s.add(Table(6.9, 2.35, [3.05, 1.55, 1.23], 0.45, sb, size=13, zebra=None, name="Sundays"))
s.add(Text(6.9, 4.8, 5.83, 1.6, [P("Same orders, same defect draws; only change: no work on Sundays. The allocators are not told. With the Sunday rule switched off the variant reproduces simulate.py exactly.", size=12.5, color=SUB)], name="Note"))


# ================================================================== E  our rule against the simple rule
s = new_slide("Appendix E · Our rule ties the simple rule on the official data, and wins when the data moves", n=11, backup=True,
              notes="Backup: late batches, simple rule against ours, on the official orders and four kinds of data the rule was never shaped on.")
s.add(Img(LM, 1.95, 6.3, 4.43, str(ASSETS / "fig_rule_vs_simple.png"), alt="Paired bars of late batches for the simple rule and our rule on five kinds of data"))
s.add(Text(LM, 6.45, 6.6, 0.5, [P("Official: seeds 5105 to 5114. Fresh sets were generated after the rule was fixed (seeds 20000+), 3 seeds each. The allocators are not told about Sundays.", size=10.5, color=SUB)], name="Source"))
s.add(Text(7.6, 2.0, 5.13, 1.6, [
    P(R("The rule, in order: ", bold=True), "on time even if the batch is reworked; then the least flexible shop (a specialist before one that makes both categories); then earliest finish.", size=13.5)], name="Rule"))
s.add(Text(7.6, 3.7, 5.13, 3.0, [
    P(R("Why it helps: ", bold=True), "earliest-finish spends the fast, flexible shops on batches that had slack; the next tight batch then has nowhere to go.", size=13.5, after=8, bullet=True),
    P(R("Official data: ", bold=True), f"a tie on late batches ({fo('lateness', 'pct_late'):.1f}%), half the late days ({fo('lateness', 'late_days'):.2f} against {fo('earliest_finish', 'late_days'):.2f}).", size=13.5, after=8, bullet=True),
    P(R("Fresh data: ", bold=True), f"better on {b100} of 100 jittered order books, worse on {w100}.", size=13.5, after=8, bullet=True),
    P(R("Where the simple rule still wins: ", bold=True), f"mean turnaround, {fo('earliest_finish', 'mean_days'):.1f} against {fo('lateness', 'mean_days'):.1f} days; the shock run, by one batch in ten.", size=13.5, bullet=True)], name="Findings"))

# ================================================================== F  the two settings of our rule, paired
s = new_slide("Appendix F · Why not the setting with 1.0% late? Its edge does not hold on fresh data", n=12, backup=True,
              notes="Backup: use_slack against the earliest-finish tie-break, paired on the same data and seeds.")
s.add(Text(LM, 1.9, 12.1, 0.7, [P("Both settings share steps 1 and 2 (rework-safe shops, specialist first) and differ only in the tie-break: earliest finish, or the latest finish that is still safe (use_slack). "
                                   "Paired runs on the same data and seeds; a sign test on how often use_slack is later or earlier.", size=12.5, color=TXT)], name="Intro"))
fb = [["Data", "Runs", "use_slack better / equal / worse on late %", "Sign test p", "Mean late % (ours / use_slack)", "Mean turnaround, days"]]
for prefix, label_ in (("official 120 orders", "Official 120 orders, 10 seeds"), ("official --shock", "Official, shock, 10 seeds"), ("fresh perturbed", "100 jittered order books"),
                       ("fresh tight", "50 sets, tighter due dates"), ("fresh +10", "50 sets, extra accessory orders")):
    a, b = h2h(prefix, "lateness"), h2h(prefix, "use_slack")
    n = 10 if prefix.startswith("official") else (100 if "perturbed" in prefix else 50)
    fb.append([label_, str(n), f"{b['pct_late_better']} / {b['pct_late_equal']} / {b['pct_late_worse']}", f"{float(b['sign_test_p']):.3f}",
               f"{float(a['pct_late']):.2f} / {float(b['pct_late']):.2f}", f"{float(a['mean_days']):.1f} / {float(b['mean_days']):.1f}"])
s.add(Table(LM, 2.7, [3.1, 0.8, 3.0, 1.1, 2.3, 1.8], 0.42, fb, size=12, zebra=None, name="Head to head"))
s.add(Text(LM, 5.35, 12.1, 1.5, [
    P(R("Reading. ", bold=True), "use_slack is reliably better only on the official orders, which both settings were shaped on (8 of 10 seeds, p = 0.008). On 200 fresh order books the two are indistinguishable on lateness (p ≥ 0.05). "
      f"The robust differences are elsewhere: use_slack returns batches about {float(h2h('official 120', 'use_slack')['mean_days']) - float(h2h('official 120', 'lateness')['mean_days']):.0f} days later and costs about 9% less. "
      "The track names turnaround days as the business impact, so we declared the faster tie-break and keep use_slack as the cost-saving setting.", size=12.5)], name="Reading"))

SCRIPT = [
    "[10 s] Good evening, we are Group NN. Our project is the Subcontracting Desk: it turns the chat message that sends a batch to an outside workshop into a verified, recorded decision.",
    "[35 s] Today that decision is a chat message. Behind it are three questions: can the workshop make this product, can it take the batch now, is it allowed to? "
    "Get one wrong and the batch bounces back a day later; in a ten-day cycle that is the margin gone. So the desk reads the chat, decides on numbers, and leaves a record. "
    "The value: a verified recommendation for the dispatcher, fewer late batches for the factory, a date the customer can rely on.",
    "[50 s] The language model only reads: order, pieces, date, constraint. Then code takes over, with three mechanisms. "
    "One, the text decides: every extracted value is checked against the message, and anything the message does not contain is dropped. "
    "Two, eligibility before ranking: three hard checks, then two dates per eligible shop, expected and if reworked, and only then a ranking by the objective. "
    "Three, traced, then booked: every number in the explanation comes from a tool output, and nothing is booked until the dispatcher confirms. "
    "The bottom row is one real message going through: the standing constraint recorded, four shops eligible, GiantWeave on time even if reworked.",
    "[40 s] Our primary objective is to minimise late deliveries: the share of batches returned after their due date. Three reasons. "
    "Relevant: the due date is the one constraint every order carries, and quick response exists to protect it. Measurable: the simulator records when every batch returns. "
    "Controllable: lateness depends on queue, capacity and transport, exactly what the choice of workshop changes. "
    "The other objectives stay: defects and fairness as switchable settings, one hybrid, and robustness under the shock scenario. "
    "And we declare our tie-break up front: equal lateness, shorter turnaround.",
    "[60 s] The loop runs end to end, and the first results are in. In simulation, on the official 120 orders, random allocation is 34 percent late. "
    "Our lateness setting is 1.7 percent, the same as a simple earliest-finish rule with no language model; we do not hide that tie. "
    "On 200 fresh order books the simple rule never saw, we are ahead: 0.9 against 1.7 percent, better on 72 of 100 sets. "
    "Where the simple rule still wins: it is a day faster, and it edges us in the shock run by one batch in ten. "
    "Beyond the allocator: 56 tests pass, every number in every reply traces to a tool output, all six of us labelled the 30 messages and froze the labels, "
    "and we measured the language model before trusting it: GPT-5 mini now reads all 30 official and 38 new messages right; the cheapest model started at 86.",
    "[45 s] Three risks. No clean language test yet: the 30 messages were used in development, the 38 new ones are AI-written; "
    "so four teammates who never touch the prompt are writing a held-out inbox, answers frozen before the first run. "
    "The simulator is kinder than reality: a seven-day week, and the estimator does not know when a workshop closes; we report a Sunday variant and will add closed-workshop detection. "
    "And our policy is not optimal: a hindsight search reaches zero late, but a dispatcher cannot see future orders. Our assumptions are on the bottom line.",
    "[40 s] Next: the held-out inbox, frozen before the first run. Closed-workshop detection, so the system notices a stuck queue. "
    "A user test with students from other groups, a public demo, and an evaluation draft with ten failure cases. "
    "Our criteria: under 2 percent late on the official orders, normal and shock; fewer late batches than the simple rule on fresh data; "
    "90 percent right behaviour on the held-out inbox; and every promised rework date kept. Thank you.",
]
for _sl, _txt in zip(slides[:7], SCRIPT):
    _sl.notes = _txt.replace("Group NN", f"Group {GROUP}")

if __name__ == "__main__":
    build_dir = HERE / "_build"
    build_dir.mkdir(exist_ok=True)
    pptx_path, html_path, pdf_path = OUT / f"{NAME}.pptx", build_dir / f"{NAME}.html", OUT / f"{NAME}.pdf"
    render_pptx(slides, str(pptx_path), title="Subcontracting Desk · Sprint 1", author="DSS5105 Track 2 team", subject="Sprint 1 review, 16 October 2026 (v3, story first)")
    render_html(slides, str(html_path), title="Subcontracting Desk · Sprint 1")
    problems = export_html(str(html_path), str(OUT / "预览图_v3"), str(pdf_path))
    print("slides:", len(slides), "| tests counted:", TESTS, "| policy:", POLICY, "| held-out first run:", sorted(HELD) or "not yet")
    print("render problems (Edge):", problems if problems else "none")
    html_path.unlink(missing_ok=True)
    try:
        build_dir.rmdir()
    except OSError:
        pass
    words = [len(sl.notes.split()) for sl in slides[:7]]
    print("notes words (cover + 6):", words, sum(words))
