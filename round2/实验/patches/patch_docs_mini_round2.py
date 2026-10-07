"""2026-10-07: README and docs/round2_changes.md follow the team's decisions (GPT-5 mini by default; both lateness
rules kept for now) and point to the round2/ folder that now ships with the repo.

    python 实验/patches/patch_docs_mini_round2.py <repo>
"""
import sys
from pathlib import Path

R = Path(sys.argv[1])


def patch(rel, pairs):
    p = R / rel
    s = p.read_text(encoding="utf-8")
    for a, b in pairs:
        assert s.count(a) == 1, (rel, s.count(a), a[:60])
        s = s.replace(a, b)
    p.write_text(s, encoding="utf-8", newline="")


patch("README.md", [
    ("> **2026-10-05：第二轮（分支 `claude/round2`，未合并）。**",
     "> **2026-10-05：第二轮（分支 `claude/round2`）。** 2026-10-07 起：30 条标签已定稿（`eval/gold_labels.csv`），语言层默认用 GPT-5 mini。"
     "第二轮的全部结果、汇报稿和失败案例清单在 [`round2/`](round2/README.md)。"),
    ("| `--llm` | 改用 GPT-5 nano 解析，需要 `.env`，会产生费用 |",
     "| `--llm` | 改用 LLM 解析（默认 GPT-5 mini），需要 `.env`，会产生费用 |"),
    ("语言层用 OpenAI 的 GPT-5 nano 从群聊里提取字段，", "语言层用 OpenAI 的 GPT-5 mini 从群聊里提取字段，"),
    ("**模型。** 默认 `gpt-5-nano`，是 GPT-5 系列里最便宜的，足够完成字段提取。",
     "**模型。** 默认 `gpt-5-mini`（2026-10-07 全组定）：第二轮实测在官方 30 条和 38 条新消息上行为和决策全对，每 30 条约 3.6 美分。"
     "`gpt-5-nano` 便宜约 4 倍，但有一种说法读不对；想用它就在 `.env` 里写 `DESK_LLM_MODEL=gpt-5-nano`。"),
])

patch("docs/round2_changes.md", [
    ("1. `lateness` 用新规则，还是用 `use_slack`（迟交更少、成本低 9%，周转慢到 14 天）。\n"
     "2. 语言层默认模型用 GPT-5 nano 还是 mini（每 30 条约 1 美分对 3.6 美分；mini 在两套消息上行为和决策全对）。\n",
     "1. `lateness` 用新规则，还是用 `use_slack`（迟交更少、成本低 9%，周转慢到 14 天）。2026-10-07：两个都保留，再讨论。\n"
     "2. ~~语言层默认模型~~：2026-10-07 定为 **GPT-5 mini**（每 30 条约 3.6 美分，两套消息上行为和决策全对）。nano 仍可在 `.env` 里选。\n"),
    ("--parser llm --model gpt-5-nano --runs 3", "--parser llm --model gpt-5-mini --runs 3"),
    ("带 `--parser llm` 的命令需要 `.env` 里的 key，会产生费用。`<gold_labels.csv>` 即 `eval/gold_labels.csv`。",
     "带 `--parser llm` 的命令需要 `.env` 里的 key，会产生费用。`<gold_labels.csv>` 即 `eval/gold_labels.csv`。\n\n"
     "第二轮的结果文件、实验脚本、挑战集、汇报稿和失败案例清单都在仓库的 [`round2/`](../round2/README.md) 里。"),
])
print("docs patched")
