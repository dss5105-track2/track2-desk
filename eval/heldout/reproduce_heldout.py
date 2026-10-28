"""Reproduce the held-out first run on the recorded commit, and compare it with the record.

Run from the root of track2-desk, on main, after `git pull`:

    python reproduce_heldout.py --name liyan            # rules parser only: free, must match exactly
    python reproduce_heldout.py --name liyan --llm      # also GPT-5 mini x3: about $0.17, needs OPENAI_API_KEY in .env

What it does:
  1. checks out the recorded commit (7918ac3) into a temporary git worktree, so your own checkout is never touched;
  2. runs the same commands as eval/heldout/README.md, writing to eval/heldout/reproduce_<name>/ (never to first_run/);
  3. compares the rules run row by row with eval/heldout/first_run/, and the GPT run by configuration and score;
  4. writes eval/heldout/reproduce_<name>/REPRODUCE.md, the record to commit.
"""
from __future__ import annotations

import argparse
import csv
import datetime
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

COMMIT = "7918ac3"            # main at the first run (held-out freeze merged; system code = 3e9f2ee)
TAG = "heldout43"
RULES = f"language_eval_{TAG}_rules"
LLM = f"language_eval_{TAG}_gpt-5-mini_prompt-v2_grounded"
FIRST = {"rules": (37, 43), "llm": (115, 129)}     # recorded in eval/heldout/first_run.md


def git(*args, cwd=None) -> str:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True).stdout.strip()


def right(summary: dict) -> tuple[int, int]:
    pairs = [tuple(map(int, v.split("/"))) for v in summary["behaviour_by_class"].values()]
    return sum(a for a, _ in pairs), sum(b for _, b in pairs)


def wrong_ids(rows_csv: Path) -> dict:
    out = {}
    with open(rows_csv, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            if r["behaviour_ok"] != "True":
                out[r["request_id"]] = out.get(r["request_id"], 0) + 1
    return dict(sorted(out.items()))


def run_eval(code_dir: Path, out: Path, extra: list[str]) -> None:
    cmd = [sys.executable, "eval/run_language_eval.py", "--inbox", "eval/heldout/requests.txt", "--labels", "eval/heldout/gold_labels.csv",
           "--parses", "", "--tag", TAG, "--objective", "use_slack", "--out", str(out), *extra]
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8")
    subprocess.run(cmd, cwd=code_dir, check=True, env=env, stdout=subprocess.DEVNULL)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--name", required=True, help="your name in pinyin, e.g. liyan; used for the output folder")
    ap.add_argument("--llm", action="store_true", help="also run GPT-5 mini x3 (about $0.17; needs OPENAI_API_KEY in .env)")
    a = ap.parse_args()

    root = Path.cwd()
    record = root / "eval" / "heldout" / "first_run"
    if not (record / f"{RULES}_rows.csv").exists():
        print("Run this from the root of track2-desk, on main, after `git pull` (eval/heldout/first_run/ not found).")
        return 1
    if a.llm and not (root / ".env").exists():
        print("--llm needs a .env with OPENAI_API_KEY in the repo root.")
        return 1
    out = root / "eval" / "heldout" / f"reproduce_{a.name}"
    if out.exists() and any(out.iterdir()):
        print(f"{out} already has files; delete it or use another --name.")
        return 1
    out.mkdir(parents=True, exist_ok=True)

    git("fetch", "origin")
    code = Path(tempfile.mkdtemp(prefix="heldout_repro_")) / "code"
    git("worktree", "add", "--detach", str(code), COMMIT)
    try:
        commit_full = git("rev-parse", "HEAD", cwd=code)
        print(f"[1/3] rules parser on {COMMIT} ...")
        run_eval(code, out, ["--parser", "rules"])
        if a.llm:
            print(f"[2/3] GPT-5 mini x3 on {COMMIT} (a few minutes) ...")
            run_eval(code, out, ["--parser", "llm", "--model", "gpt-5-mini", "--runs", "3", "--env", str(root / ".env")])
    finally:
        git("worktree", "remove", "--force", str(code))

    print("[3/3] comparing with the record ...")
    rec_rows = (record / f"{RULES}_rows.csv").read_text(encoding="utf-8-sig").splitlines()
    new_rows = (out / f"{RULES}_rows.csv").read_text(encoding="utf-8-sig").splitlines()
    diff = [i for i, (x, y) in enumerate(zip(rec_rows, new_rows), 1) if x != y] + ([0] if len(rec_rows) != len(new_rows) else [])
    rules_ok = not diff
    rr, rn = right(json.loads((out / f"{RULES}.json").read_text(encoding="utf-8")))

    lines = [f"# 留出集首轮复现核对：{a.name}", "",
             f"- 日期：{datetime.date.today().isoformat()}",
             f"- 代码版本：`{commit_full[:7]}`（首轮运行时的 main，系统代码等同 `3e9f2ee`）",
             "- 输入：`eval/heldout/requests.txt`（43 条），答案：`eval/heldout/gold_labels.csv`，派单目标 use_slack",
             "- 脚本：`reproduce_heldout.py`（临时 worktree 运行，没有改动任何文件）", "",
             "## 规则解析器（结果确定，要求逐行一致）", "",
             f"- 复现：{rr}/{rn} = {100 * rr / rn:.1f}%；首轮记录：{FIRST['rules'][0]}/{FIRST['rules'][1]} = {100 * FIRST['rules'][0] / FIRST['rules'][1]:.1f}%",
             f"- 与首轮逐行比对（43 行）：**{'完全一致' if rules_ok else '不一致，见行号 ' + ', '.join(map(str, diff))}**",
             f"- 判错的消息：{', '.join(wrong_ids(out / f'{RULES}_rows.csv'))}", ""]
    if a.llm:
        s = json.loads((out / f"{LLM}.json").read_text(encoding="utf-8"))
        lr, ln = right(s)
        cfg_ok = (s["parser"] == "llm:gpt-5-mini" and s["runs"] == 3 and s["prompt"] == "v2" and s["grounding"] and str(s["grounding_version"]) == "2.2"
                  and s["objective"] == "use_slack" and s["requests"] == 43)
        lines += ["## GPT-5 mini × 3（模型输出有波动，核对配置、口径和范围，不要求逐字一致）", "",
                  f"- 配置：{s['parser']}，prompt {s['prompt']}，grounding {s['grounding_version']}，{s['runs']} 遍，目标 {s['objective']}："
                  f"**{'与首轮相同' if cfg_ok else '与首轮不同，请检查'}**",
                  f"- 退回规则解析器的次数：{s['fallbacks_to_rules']}（应为 0；不为 0 说明 API key 有问题，这次 GPT 结果无效）",
                  f"- 复现：{lr}/{ln} = {100 * lr / ln:.1f}%；首轮记录：{FIRST['llm'][0]}/{FIRST['llm'][1]} = {100 * FIRST['llm'][0] / FIRST['llm'][1]:.1f}%",
                  f"- 判错的消息（次数）：{', '.join(f'{k}×{v}' for k, v in wrong_ids(out / f'{LLM}_rows.csv').items())}",
                  "- 首轮判错的消息（次数）：" + ", ".join(f"{k}×{v}" for k, v in wrong_ids(record / f"{LLM}_rows.csv").items()),
                  f"- 花费：{s['spent_usd']} 美元", ""]
    lines += ["## 结论", "", "（复现人填写：是否认为首轮记录可信；有不一致时写明原因。）", ""]
    (out / "REPRODUCE.md").write_text("\n".join(lines), encoding="utf-8")

    print()
    print(f"Rules parser: {rr}/{rn} ({100 * rr / rn:.1f}%), row-by-row vs record: {'IDENTICAL' if rules_ok else 'DIFFERENT at rows ' + str(diff)}")
    if a.llm:
        print(f"GPT-5 mini x3: {lr}/{ln} ({100 * lr / ln:.1f}%), config {'same' if cfg_ok else 'DIFFERENT'}, fallbacks {s['fallbacks_to_rules']}")
    print(f"Record written: {out / 'REPRODUCE.md'}")
    return 0 if rules_ok else 2


if __name__ == "__main__":
    sys.exit(main())
