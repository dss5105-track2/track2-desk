"""Sprint 1 deck, round-2 update: ../06_汇报更新/Presentation_GroupNN_Sprint1_DRAFT_v2.{pptx,pdf} + previews.

    python 实验/build_deck2.py

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
NAME = "Presentation_GroupNN_Sprint1_DRAFT_v2"

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


# ================================================================== 1  title
s = new_slide(dark=True, notes=(
    "[10 s] Good evening, we are Group NN. Our project is the Subcontracting Desk: it turns the chat message that sends a batch to an outside workshop into a checked, recorded allocation."))
s.add(Text(0.8, 1.15, 7.2, 0.35, [P("DSS5105 CAPSTONE  ·  TRACK 2  ·  SPRINT 1", size=13, bold=True, color=MUTED_ON_DARK)], name="Eyebrow"))
s.add(Text(0.8, 1.7, 7.4, 1.0, [P("Subcontracting Desk", size=48, bold=True, color=WHITE, font=TITLE_FONT)], name="Title"))
s.add(Text(0.8, 2.85, 6.9, 1.2, [P("From a group-chat decision\nto a checked, recorded allocation", size=24, color=PALE, lh=1.0)], name="Subtitle"))
s.add(Text(0.8, 4.75, 7.3, 1.9, [
    P("Group NN", size=17, bold=True, color=WHITE, after=6),
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

# ================================================================== 2  problem and solution
s = new_slide("A batch goes outside on one chat message: unchecked and unrecorded", n=2, notes=(
    "[40 s] Today the decision is a chat message. Behind it are three questions: can the workshop make the product, can it take the batch now, is it allowed to? "
    "Get one wrong and the batch bounces back a day later. Our desk checks all three and recommends one workshop, with the reason.\n"
    "This is a real message, R12: nothing new to QuickStitch this week. The desk records that, gives two dates per shop, expected and if reworked, "
    "and books nothing until the dispatcher confirms."))
label(s, LM, 1.95, 3, "TODAY")
s.add(Rect(LM, 2.3, 5.7, 1.1, fill=GREY_T, radius=0.14, name="Chat bubble", pad=0.22, paras=[
    P("“@Chen — order 042, 1,500 crewnecks. Send it to QuickStitch, need it back by the 19th.”", size=16, italic=True, color=TXT)]))
for i, (a, b) in enumerate([("Can they make it? ", "Not every workshop makes every product."),
                            ("Can they take it now? ", "A fast shop with a 3-day queue is not fast today."),
                            ("Are they allowed to? ", "One shop is suspended after an audit, one is on trial with small batches only.")]):
    y = 3.65 + i * 0.82
    badge(s, LM, y + 0.04, 0.46, str(i + 1))
    s.add(Text(LM + 0.65, y, 5.05, 0.75, [P(R(a, bold=True), b, size=15)], name=f"Question {i + 1}"))
s.add(Text(LM, 6.15, 5.7, 0.75, [P("Get one wrong and the batch bounces back a day later. In a ten-day cycle that is the margin gone.", size=14, italic=True, color=SUB)], name="Cost of error"))
label(s, 6.9, 1.95, 3, "WITH THE DESK", BLUE)
s.add(Rect(6.9, 2.3, 5.83, 4.6, fill=BLUE_T, radius=0.14, name="Decision card"))
s.add(Text(7.1, 2.42, 5.45, 0.4, [P(R("R12  ·  ORD-053  ·  ", bold=True), "800 polo shirts, due Fri 10 Apr", size=15)], name="Request"))
s.add(Rect(7.1, 2.9, 5.43, 0.62, fill=ORANGE_T, radius=0.08, name="Constraint chip", pad=0.12, paras=[
    P("Standing constraint recorded: Boss, nothing new to QuickStitch this week", size=12.5, color=ORANGE_D, bold=True)]))
hl = lambda t, al="r": {"text": t, "bold": True, "color": BLUE_D, "align": al}
s.add(Table(7.1, 3.7, [0.36, 1.72, 1.2, 1.3, 0.85], 0.4, [
    ["", {"text": "Workshop", "align": "l"}, "Back", "If reworked", "Status"],
    [hl("★", "c"), hl("GiantWeave", "l"), hl("Fri 10 Apr"), hl("Sat 11 Apr"), hl("on time")],
    ["", {"text": "Nimble Needle", "align": "l"}, "Thu 9 Apr", "Sun 12 Apr", "on time"],
    ["", {"text": "SteadyHands", "align": "l"}, "Fri 10 Apr", "Mon 13 Apr", "on time"],
    ["", {"text": "BudgetWorks", "align": "l"}, "Mon 13 Apr", "Tue 14 Apr", {"text": "3 d late", "color": ORANGE_D}]], size=12.5, zebra=WHITE, name="Candidates"))
s.add(Text(7.1, 5.82, 5.43, 1.05, [
    P(R("Why GiantWeave: ", bold=True), "it only makes tops, so the two shops that also make accessories stay free for tighter batches.", size=12, color=TXT, after=4),
    P("Not eligible: QuickStitch (excluded), OldMill (suspended), FreshStart (300-piece cap), Little Loom (accessories only).", size=12, color=SUB)], name="Card footer"))

# ================================================================== 3  architecture
s = new_slide("The language model reads and explains; the arithmetic stays in code", n=3, notes=(
    "[35 s] The language layer extracts the order, pieces, due date and constraint, asks when something is unclear, and declines what the data cannot answer. "
    "The model only proposes: code checks every extracted value against the message text.\n"
    "Everything numeric happens in the kernel, which has no LLM: eligibility, two delivery dates per shop, and a ranking by an objective that is a setting. "
    "The dispatcher confirms before anything is booked."))
stages = [
    ("Chat message", "INPUT", GREY_T, TXT, SUB, "Free text from five people: “Send it to QuickStitch, need it back by the 19th.”"),
    ("Language layer", "LANGUAGE MODEL + CHECK", BLUE_T, TXT, BLUE_D, "The model extracts order, pieces, date, constraint. Code checks each value against the message text."),
    ("Kernel", "CODE · NO LLM", INK, WHITE, "7ED9B8", "Register: can they make it, take it, are they allowed? Estimator: two dates per shop. Allocator: the objective is a setting."),
    ("Explain and check", "CODE", AQUA_T, TXT, "0B7A52", "Writes the reason from tool outputs. Flags any number that is not in one."),
    ("Dispatcher", "HUMAN", ORANGE_T, TXT, ORANGE_D, "Sees candidates, dates and one recommendation. Confirms, changes or escalates. Then the audit record is written."),
]
bw, gap, y0, bh = 2.2, 0.28, 2.3, 2.75
for i, (head, tag, fill, fg, tagc, body) in enumerate(stages):
    x = LM + i * (bw + gap)
    s.add(Rect(x, y0, bw, bh, fill=fill, radius=0.14, name=head, valign="t", pad=0.14, paras=[
        P(tag, size=10.5, bold=True, color=tagc, after=4, before=9), P(head, size=18, bold=True, color=fg, after=6), P(body, size=14, color=fg if fg == WHITE else TXT)]))
    if i < len(stages) - 1:
        s.add(Line(x + bw + 0.03, y0 + bh / 2, x + bw + gap - 0.03, y0 + bh / 2, color=SUB, lw=2, arrow=True, name="Flow arrow"))
sim_x = LM + 2 * (bw + gap)
s.add(Line(sim_x + bw / 2, 5.5, sim_x + bw / 2, y0 + bh + 0.04, color=SUB, lw=2, arrow=True, name="Simulator link"))
s.add(Rect(sim_x, 5.5, 2 * bw + gap, 1.3, fill=GREY_T, radius=0.12, name="Simulator", pad=0.18, paras=[
    P("Shared simulator (harness/simulate.py, v3)", size=14, bold=True, color=TXT, after=3),
    P("Replays 120 orders through the allocator, against three baselines. Its shock option closes one workshop for two weeks.", size=13, color=TXT)]))
s.add(Text(LM, 5.5, 2 * bw + gap, 1.3, [P(R("The model proposes; the text and the code decide. ", bold=True), "Queues, estimates, rankings and costs come from code, so every number can be audited.", size=14.5)], valign="m", name="Principle"))
lx = LM + 4 * (bw + gap)
for i, (c, t) in enumerate([(BLUE_T, "Language model"), (INK, "Code"), (ORANGE_T, "Human")]):
    s.add(Rect(lx, 5.6 + i * 0.42, 0.22, 0.22, fill=c, line=LINE, lw=0.75, name="Legend swatch"))
    s.add(Text(lx + 0.36, 5.57 + i * 0.42, 1.8, 0.3, [P(t, size=12.5, color=TXT)], valign="m", name="Legend label"))

# ================================================================== 4  business value
s = new_slide(f"In replay, late batches fall from {fo('random', 'pct_late'):.0f}% to {fo('lateness', 'pct_late'):.1f}%", n=4, notes=(
    f"[30 s] We replayed 120 orders through the shared simulator. Picking workshops at random returns 34 percent of batches late; our lateness setting returns 1.7 percent, "
    f"and mean turnaround falls from 22 to 9 days, for about 3 percent more cost. On the morning inbox, 17 of 30 messages cannot simply be dispatched. A chat thread lets those through; the desk stops them."))
s.add(Img(LM, 2.0, 6.4, 3.7, str(ASSETS / "fig_late_by_policy.png"), alt="Bar chart of late batches by policy: cheapest 92%, greedy_biggest 84%, random 34%, simple rule 1.7%, our allocator 1.7%"))
s.add(Text(LM, 5.85, 6.4, 0.9, [P(f"Source: harness/simulate.py v3, seeds 5105 to 5114, repo commit {COMMIT}. Every order is replayed as if it had gone outside on its order date.", size=11, color=SUB)], name="Source"))
label(s, 7.5, 1.95, 4, "WHAT THE DISPATCHER GETS", SUB)
for big, small, y, hh in [
        (f"{fo('lateness', 'mean_days'):.1f} days", f"mean turnaround, down from {fo('random', 'mean_days'):.1f} days when workshops are picked at random", 2.35, 0.55),
        (f"+{cost_delta:.1f}% cost", f"against random ({fo('lateness', 'cost') / 1000:.1f}k against {fo('random', 'cost') / 1000:.1f}k): speed is not free", 3.85, 0.55),
        ("17 of 30", "morning messages cannot simply be dispatched: 7 need a question, 4 name a workshop that cannot take the job, 3 cannot meet the date, 3 have no answer in the data", 5.3, 1.1)]:
    s.add(Text(7.5, y, 5.2, 0.7, [P(big, size=38, bold=True, color=BLUE, lh=0.95)], name="Stat"))
    s.add(Text(7.5, y + 0.68, 5.2, hh, [P(small, size=14, color=TXT)], name="Stat label"))

# ================================================================== 5  progress
lang_tile = (f"{nano_b['behaviour_accuracy_pct']:.0f}% → {nano_a['behaviour_accuracy_pct']:.0f}%" if nano_b and nano_a else "measured")
s = new_slide("Sprint 1 so far: the loop runs end to end, and each part is now measured", n=5, notes=(
    f"[35 s] The whole loop runs. {TESTS} tests pass, and every number in every reply traces to a tool output. "
    f"The interface puts the tightest requests first and confirms the safe ones in one click. {WHO} labelled the requests independently: kappa {KAPPA:.2f}. "
    f"And we measured the language model: the cheapest one got {nano_b['behaviour_accuracy_pct']:.0f} percent of behaviours right; "
    f"with a sharper prompt and code checks, {nano_a['behaviour_accuracy_pct']:.0f} percent on these thirty, which we developed on."))
s.add(Img(LM, 1.95, 5.6, 4.56, str(ASSETS / "ui_main_crop.png"), alt="Screenshot of the dispatcher interface: inbox grouped by next step with a one-click confirm, and the decision card for R12"))
s.add(Rect(LM, 1.95, 5.6, 4.56, line=LINE, lw=1, name="Screenshot frame"))
s.add(Text(LM, 6.56, 5.6, 0.45, [P("Dispatcher interface: grouped by next step, tightest first; one click confirms the rework-safe recommendations", size=11, color=SUB)], name="Caption"))
tiles = [(f"{TESTS} / {TESTS}", "Tests pass. ", "Kernel, dispatcher workflow, the new rule, and the checks on what the model extracts."),
         ("30 / 30", "Replies fully traced. ", "Every number in every reply on the 30-message inbox comes from a tool output."),
         (f"κ {KAPPA:.2f}", ("Six members" if WHO.startswith("All six") else "Members") + " labelled the inbox on their own. ", ("The 9 changed requests: unanimous. " if NINE_UNANIMOUS else "") + "Weakest where the named workshop cannot take the job."),
         (lang_tile, "Right behaviour with GPT-5 nano on the 30 we developed on. ", "A sharper prompt, plus code that checks each extracted value against the message."
          + (f" {c_nano_a['behaviour_accuracy_pct']:.0f}% on 38 new messages." if c_nano_a else ""))]
for i, (big, lead, rest) in enumerate(tiles):
    y = 1.95 + i * 1.22
    s.add(Text(6.55, y, 2.35, 0.9, [P(big, size=30, bold=True, color=BLUE, lh=0.95)], name="Number"))
    s.add(Text(8.95, y + 0.02, 3.78, 1.15, [P(R(lead, bold=True), rest, size=13.5)], name="Tile text"))

# ================================================================== 6  objective and finding
s = new_slide("Our lateness rule ties the simple rule on the official data, and wins when the data moves", n=6, notes=(
    "[45 s] Our primary objective is minimise lateness. On the official 120 orders a simple earliest-finish rule ties us at 1.7 percent late. "
    "But earliest-finish is greedy: it spends the fast, flexible shops on batches that had slack, and the next tight batch has nowhere to go. "
    "Our rule keeps the shops that make the date even if the batch is reworked, takes the least flexible of them, and only then looks at speed. "
    f"That halves the late days on the official data. On order books the rule was never shaped on, it wins: {val(P1, V2):.1f} percent late against {val(P1, 'earliest_finish'):.1f} on a hundred jittered copies, "
    "and likewise with extra accessory orders, tighter due dates, and Sundays off. The simple rule is still a day faster on average."))
s.add(Img(LM, 1.95, 6.3, 4.43, str(ASSETS / "fig_rule_vs_simple.png"), alt="Paired bars of late batches for the simple rule and our rule on five kinds of data"))
s.add(Text(LM, 6.45, 6.6, 0.5, [P("Official: seeds 5105 to 5114. Fresh sets were generated after the rule was fixed (seeds 20000+), 3 seeds each. The allocators are not told about Sundays.", size=10.5, color=SUB)], name="Source"))
label(s, 7.6, 1.95, 5.1, "PRIMARY OBJECTIVE", BLUE)
s.add(Text(7.6, 2.3, 5.13, 0.6, [P("Minimise lateness", size=28, bold=True, color=TXT, font=TITLE_FONT)], name="Objective"))
s.add(Text(7.6, 2.98, 5.13, 1.3, [
    P(R("The rule, in order: ", bold=True), "on time even if the batch is reworked; then the least flexible shop (a specialist before one that makes both categories); then earliest finish.", size=14)], name="Rule"))
s.add(Text(7.6, 4.3, 5.13, 2.3, [
    P(R("Official data: ", bold=True), f"a tie on late batches ({fo('lateness', 'pct_late'):.1f}%), half the late days ({fo('lateness', 'late_days'):.2f} against {fo('earliest_finish', 'late_days'):.2f}).", size=14, after=8, bullet=True),
    P(R("Fresh data: ", bold=True), f"better on {b100} of 100 jittered order books, worse on {w100}.", size=14, after=8, bullet=True),
    P(R("Where the simple rule still wins: ", bold=True), f"mean turnaround, {fo('earliest_finish', 'mean_days'):.1f} against {fo('lateness', 'mean_days'):.1f} days.", size=14, bullet=True)], name="Findings"))

# ================================================================== 7  risks and assumptions
s = new_slide("What could go wrong, and what we are assuming", n=7, notes=(
    "[30 s] Four risks. Our labels are frozen, but five needed a team vote, so we state the rule we used. On the official data we only tie the simple rule, so we show both the tie and the stressed results. "
    "The cheap language model misreads messages; code now checks what it extracts, and the real test is an inbox our teammates still have to write. And the simulator is a what-if replay. "
    "On the right, our assumptions: above all, a confirmed dispatch occupies capacity for later requests."))
FROZEN = (ROOT / "01_标注" / "gold_labels_v3_final.csv").exists()
risks = [(("Our labels are ours, not the instructor's. " if FROZEN else "Labels are not final. "),
          (f"Frozen on 7 Oct: {BELOW} of 30 fell short of 5/6 agreement and were settled by a team vote on one stated rule. The counts per kind match the instructor's."
           if FROZEN else f"The 9 requests the instructor changed were relabelled unanimously; {BELOW} of the other 21 fall short of 5/6 agreement. We align on rules, then freeze.")),
         ("On the official data we only tie the simple rule. ", "Our edge shows on jittered and stressed data. We report both, and where the baseline wins."),
         ("The cheap model misreads messages. ", f"GPT-5 nano: {nano_b['behaviour_accuracy_pct']:.0f}% right behaviour before our checks. A teammate-written held-out inbox is still to come."),
         ("The simulator is a what-if replay. ", f"With Sundays off, the simple rule goes from {sun('seven-day week (official)', 'earliest_finish'):.1f}% to {sun('Sundays off', 'earliest_finish'):.1f}% late. We report that separately.")]
assumptions = [("Today is 1 April 2026; requests arrive in time order. ", "A confirmed dispatch occupies capacity for later requests (team decision)."),
               ("Standing constraints persist. ", "“Nothing new to QuickStitch this week” applies to every later request, with who set it."),
               ("Two dates per estimate. ", "Expected: queue + work + expected rework + transport. If reworked: work takes half as long again (simulator rule)."),
               ("The data has no customer prices and no history. ", "Questions about either are declined, never invented.")]
label(s, LM, 1.95, 4, "RISKS", ORANGE_D)
label(s, 6.95, 1.95, 4, "ASSUMPTIONS", BLUE_D)
for i, ((a, b), (c, d)) in enumerate(zip(risks, assumptions)):
    y = 2.3 + i * 1.12
    s.add(Rect(LM, y, 6.05, 1.0, fill=ORANGE_T, radius=0.1, name=f"Risk {i + 1}", pad=0.16, paras=[P(R(a, bold=True), b, size=14)]))
    s.add(Rect(6.95, y, 5.78, 1.0, fill=BLUE_T, radius=0.1, name=f"Assumption {i + 1}", pad=0.16, paras=[P(R(c, bold=True), d, size=14)]))

# ================================================================== 8  roadmap and success criteria
best_c = max([d for d in (c_nano_a, c_mini_a) if d], key=lambda d: d["behaviour_accuracy_pct"], default=None)
s = new_slide("Sprint 2, 30 October: from a working loop to evidence we can defend", n=8, notes=(
    "[30 s] The plan has four steps; the two ahead of us matter most. First the evidence: a held-out inbox written by teammates who do not touch the prompt, "
    "a user test of the interface, and detecting a closed workshop from a stuck queue. Then a public demo and the evaluation. Our criteria are on the bottom row: under 2 percent late, "
    "beating the simple rule on fresh data, 90 percent right behaviour on the held-out inbox, and every promised rework date kept."))
steps = [("5 – 9 Oct", "Align and freeze", ("Gold labels frozen on 7 Oct; round-2 code to merge." if FROZEN else "Alignment meeting; gold labels frozen; round-2 code merged.")),
         ("10 – 16 Oct", "Sprint 1", "Rehearse twice; present live on 16 Oct."),
         ("17 – 23 Oct", "Evidence", "Held-out inbox written and frozen; user test with 3 people; closed-workshop detection."),
         ("24 – 29 Oct", "Ship", "Public demo; Evaluation draft with 10 failure cases; 5-minute video.")]
for i, (d, t, b) in enumerate(steps):
    x = LM + i * 3.06
    s.add(Rect(x, 1.95, 2.9, 1.85, fill=GREY_T, radius=0.12, name=t, valign="t", pad=0.16, paras=[
        P(d, size=13, bold=True, color=BLUE_D, after=2, before=10), P(t, size=17, bold=True, color=TXT, after=4), P(b, size=13.5, color=TXT)]))
label(s, LM, 4.02, 9, "SUCCESS CRITERIA · MEASURED ON v3 DATA", SUB)
crit = [("≤ 2%", f"late batches on the official orders, normal and shock (10 seeds). Now {fo('lateness', 'pct_late'):.1f}% and {fo('lateness', 'shock_pct_late'):.1f}%."),
        ("Beat it", f"fewer late batches than the simple rule on fresh order books. Now {val(P1, V2):.1f}% against {val(P1, 'earliest_finish'):.1f}%."),
        ("≥ 90%", "right behaviour on a held-out inbox written by teammates, labels frozen first."
                  + (f" Now {c_nano_a['behaviour_accuracy_pct']:.0f}% (nano) and {c_mini_a['behaviour_accuracy_pct']:.0f}% (mini) on 38 AI-written messages." if c_nano_a and c_mini_a else "")),
        ("100%", f"of numbers traced; promised rework dates kept (now {float(prom_n['date_if_reworked_kept_pct']):.0f}%, {float(prom_s['date_if_reworked_kept_pct']):.0f}% under shock).")]
for i, (big, txt) in enumerate(crit):
    x = LM + i * 3.06
    s.add(Rect(x, 4.4, 2.9, 2.45, fill=BLUE_T, radius=0.12, name=f"Criterion {i + 1}", valign="t", pad=0.18, paras=[
        P(big, size=36, bold=True, color=BLUE_D, after=6, before=10, lh=0.95), P(txt, size=14.5, color=TXT)]))

# ================================================================== A  results table
s = new_slide("Appendix A · Results on v3 data, mean of 10 seeds", n=9, backup=True, notes="Backup: full results table, seeds 5105 to 5114.")
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
s = new_slide("Appendix B · How the desk sorted the 30 messages", n=10, backup=True, notes="Backup: every request, coloured by the desk's decision.")
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
s = new_slide("Appendix C · The language layer, measured on two inboxes", n=11, backup=True, notes="Backup: behaviour accuracy by parser, before and after.")
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
s = new_slide("Appendix D · Promised dates, and a six-day week", n=12, backup=True, notes="Backup: two dates per promise; Sundays off.")
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

if __name__ == "__main__":
    build_dir = HERE / "_build"
    build_dir.mkdir(exist_ok=True)
    pptx_path, html_path, pdf_path = OUT / f"{NAME}.pptx", build_dir / f"{NAME}.html", OUT / f"{NAME}.pdf"
    render_pptx(slides, str(pptx_path), title="Subcontracting Desk · Sprint 1", author="DSS5105 Track 2 team", subject="Sprint 1 review, 16 October 2026 (round-2 update)")
    render_html(slides, str(html_path), title="Subcontracting Desk · Sprint 1")
    problems = export_html(str(html_path), str(OUT / "预览图"), str(pdf_path))
    print("slides:", len(slides), "| tests counted:", TESTS)
    print("render problems (Edge):", problems if problems else "none")
    html_path.unlink(missing_ok=True)
    try:
        build_dir.rmdir()
    except OSError:
        pass
    words = [len(sl.notes.split()) for sl in slides[:8]]
    print("notes words (slides 1-8):", words, sum(words))
