"""Round-2 charts for the updated deck, drawn from the round-2 result files.

    python 实验/make_figures2.py     ->  ../06_汇报更新/assets/fig_*.png

Colour roles as in round 1 (dataviz reference palette): blue = ours, orange = the simple rule
(earliest finish), grey = the official baselines. Text never wears a data colour.
"""
from __future__ import annotations

import csv
import glob
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "06_汇报更新" / "assets"
OUT.mkdir(parents=True, exist_ok=True)
for fn in ("calibri.ttf", "calibrib.ttf"):
    font_manager.fontManager.addfont(f"C:/Windows/Fonts/{fn}")
plt.rcParams.update({"font.family": "Calibri", "font.size": 12, "axes.edgecolor": "#c9c8c3", "axes.linewidth": 0.8, "xtick.color": "#52514e",
                     "ytick.color": "#52514e", "axes.labelcolor": "#52514e", "text.color": "#0b0b0b", "savefig.facecolor": "white"})
INK, SECOND, GRID = "#0b0b0b", "#52514e", "#e6e5e1"
BLUE, ORANGE, GREY, AQUA = "#2a78d6", "#eb6834", "#9aa3ab", "#1baf7a"


def rows(p):
    return list(csv.DictReader(open(p, encoding="utf-8-sig")))


def clean(ax, axis="x"):
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.grid(axis=axis, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.tick_params(length=0)


def fig_late():
    off = {r["policy"]: r for r in rows(ROOT / "02_分配器" / "official_10seeds.csv")}
    items = [("cheapest", "cheapest", GREY), ("greedy_biggest", "greedy_biggest", GREY), ("random", "random", GREY),
             ("earliest_finish", "simple rule\n(earliest finish)", ORANGE), ("lateness", "our allocator\n(lateness)", BLUE)]
    fig, ax = plt.subplots(figsize=(5.7, 3.3), dpi=300)
    ys = list(range(len(items)))[::-1]
    for y, (k, lab, col) in zip(ys, items):
        v = float(off[k]["pct_late"])
        ax.barh(y, v, height=0.52, color=col)
        ax.text(v + 1.6, y, f"{v:.0f}%" if v >= 10 else f"{v:.1f}%", va="center", fontsize=13, fontweight="bold", color=INK)
    ax.set_yticks(ys); ax.set_yticklabels([i[1] for i in items], fontsize=12, color=INK)
    ax.set_xlim(0, 105); ax.set_xticks([0, 25, 50, 75, 100]); ax.set_xticklabels(["0", "25", "50", "75", "100%"], fontsize=11)
    ax.set_xlabel("Batches returned late (120 orders, mean of 10 seeds)", fontsize=11)
    clean(ax); ax.spines["left"].set_visible(False)
    fig.tight_layout(); fig.savefig(OUT / "fig_late_by_policy.png"); plt.close(fig)


def fig_rule_vs_simple():
    """% late, simple rule against our rule, on the official orders and on four kinds of data it was not shaped on."""
    val = rows(ROOT / "02_分配器" / "validation_means.csv")
    sun = rows(ROOT / "05_模拟器假设" / "sunday_closed.csv")
    off = {r["policy"]: r for r in rows(ROOT / "02_分配器" / "official_10seeds.csv")}

    def v(data, pol):
        return float(next(r for r in val if r["data"] == data and r["policy"] == pol)["pct_late"])

    def s(pol):
        return float(next(r for r in sun if r["calendar"] == "Sundays off" and r["shock"] == "False" and r["policy"] == pol)["pct_late"])
    groups = [("Official 120 orders", float(off["earliest_finish"]["pct_late"]), float(off["lateness"]["pct_late"])),
              ("Orders jittered\n(100 fresh sets)", v("fresh perturbed (100 sets)", "earliest_finish"), v("fresh perturbed (100 sets)", "lateness (v2 rule)")),
              ("Extra accessory orders\n(50 fresh sets)", v("fresh +10 accessory orders (50 sets)", "earliest_finish"), v("fresh +10 accessory orders (50 sets)", "lateness (v2 rule)")),
              ("Sundays off\n(Primer's calendar)", s("earliest_finish"), s("lateness (v2 rule)")),
              ("Tighter due dates\n(50 fresh sets)", v("fresh tight due dates 10-21 days (50 sets)", "earliest_finish"), v("fresh tight due dates 10-21 days (50 sets)", "lateness (v2 rule)"))]
    fig, ax = plt.subplots(figsize=(6.4, 4.5), dpi=300)
    h = 0.34
    for i, (lab, ef, ours) in enumerate(groups):
        y = len(groups) - 1 - i
        ax.barh(y + h / 2 + 0.02, ef, height=h, color=ORANGE)
        ax.barh(y - h / 2 - 0.02, ours, height=h, color=BLUE)
        ax.text(ef + 0.08, y + h / 2 + 0.02, f"{ef:.1f}%", va="center", fontsize=11.5, color=INK)
        ax.text(ours + 0.08, y - h / 2 - 0.02, f"{ours:.1f}%", va="center", fontsize=11.5, fontweight="bold", color=INK)
    ax.set_yticks(range(len(groups))); ax.set_yticklabels([g[0] for g in groups][::-1], fontsize=11.5, color=INK)
    ax.set_xlim(0, 7.2); ax.set_xlabel("Late batches, %", fontsize=11.5)
    handles = [plt.Rectangle((0, 0), 1, 1, color=ORANGE), plt.Rectangle((0, 0), 1, 1, color=BLUE)]
    ax.legend(handles, ["simple rule (earliest finish)", "our lateness rule"], loc="lower center", bbox_to_anchor=(0.36, 1.0), ncol=2, frameon=False,
              fontsize=11.5, handlelength=1.1, columnspacing=1.8)
    clean(ax); ax.spines["left"].set_visible(False)
    fig.tight_layout(); fig.savefig(OUT / "fig_rule_vs_simple.png"); plt.close(fig)
    return groups


def fig_language():
    """Behaviour accuracy by parser, first run on each inbox (before round-2 changes) and after."""
    E = ROOT / "03_语言层评估"
    runs = []
    for folder, stage in (("基线_改进前", "before"), ("改进后_核对2.2", "after"), ("改进后_核对2.1", "after"), ("改进后", "after")):   # the latest improved run wins
        for p in sorted(glob.glob(str(E / folder / "*.json"))):
            d = json.loads(Path(p).read_text(encoding="utf-8")); d["stage"] = stage; runs.append(d)

    def b(stage, tag, parser):
        d = next((r for r in runs if r["stage"] == stage and r["tag"] == tag and r["parser"] == parser), None)
        return d["behaviour_accuracy_pct"] if d else None
    cats = [("rules", "Rule parser\n(offline)"), ("llm:gpt-5-nano", "GPT-5 nano"), ("llm:gpt-5-mini", "GPT-5 mini")]
    fig, axes = plt.subplots(1, 2, figsize=(11.6, 3.5), dpi=300, sharey=True)
    for ax, (tag, title) in zip(axes, (("official30", "Official 30 messages (seen during development)"), ("challenge38", "38 new messages (AI-written challenge set)"))):
        for i, (parser, lab) in enumerate(cats):
            bef, aft = b("before", tag, parser), b("after", tag, parser)
            if bef is not None:
                ax.bar(i - 0.19, bef, width=0.34, color=GREY)
                ax.text(i - 0.19, bef + 1.2, f"{bef:.0f}%", ha="center", fontsize=11.5, color=INK)
            if aft is not None:
                ax.bar(i + 0.19, aft, width=0.34, color=BLUE)
                ax.text(i + 0.19, aft + 1.2, f"{aft:.0f}%", ha="center", fontsize=11.5, fontweight="bold", color=INK)
        ax.set_xticks(range(len(cats))); ax.set_xticklabels([c[1] for c in cats], fontsize=11.5, color=INK)
        ax.set_ylim(0, 112); ax.set_yticks([0, 25, 50, 75, 100]); ax.set_title(title, fontsize=12.5, color=INK, loc="left")
        clean(ax, "y"); ax.spines["bottom"].set_visible(False)
    axes[0].set_ylabel("Right behaviour, % of messages", fontsize=11.5)
    handles = [plt.Rectangle((0, 0), 1, 1, color=GREY), plt.Rectangle((0, 0), 1, 1, color=BLUE)]
    fig.legend(handles, ["first run, before round-2 changes", "after: sharper prompt + code checks (rule parser: after its fixes)"], loc="lower center", ncol=2,
               frameon=False, fontsize=11.5, handlelength=1.1, columnspacing=2.0)
    fig.tight_layout(rect=(0, 0.09, 1, 1)); fig.savefig(OUT / "fig_language.png"); plt.close(fig)


if __name__ == "__main__":
    fig_late()
    g = fig_rule_vs_simple()
    fig_language()
    print("figures:", sorted(p.name for p in OUT.glob("fig_*.png")))
    for lab, ef, ours in g:
        print(f"  {lab.splitlines()[0]:<26} simple {ef:.2f}  ours {ours:.2f}")
