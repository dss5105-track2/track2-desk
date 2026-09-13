# ⚠ 草稿目录：独立分类完成前不要打开

`gold_labels_draft.csv` 是 Claude 按 `eval/protocol.md` 生成的第一版标注与数字，用于对照，**不是标准答案**。

- 全员独立分类（labeling_guide 第 1 步）交齐之前，任何人都不要打开本目录的 CSV，否则分歧统计失效。
- 数字由 PowerShell 按内核公式重放得到（含返工期望、Python round 规则），本机当时无 Python。正式数字必须由 `python eval/compute_gold_facts.py` 生成并与本草稿比对。
- `final` 列由张锦若在双人标注后填写；定稿后另存为 `eval/gold_labels.csv`，本草稿保留不删，作为开发接触的证据。

## 草稿里的分布

| 官方类别 | 条数 | 其中 |
|---|---|---|
| extract | 14 | allocate 3（R09 R12 R25）；no_on_time_option 11 |
| clarify | 9 | ambiguous 4；missing 3；state_conflict 2（R16 R26） |
| refuse | 4 | R08 R11 R14 R24 |
| decline-to-answer | 3 | R02 R13 R18 |

30 条里只有 3 条存在按时方案并应直接派单。

## 需要讨论的争议

| 条目 | 争议 | 影响 |
|---|---|---|
| R12 禁令范围 | Boss 的 "nothing new to QuickStitch this week" 是否对会话生效 | R17 R21 R25 R30 的答案随之变化；R21 在不生效时变为 allocate W1 |
| R20 | 与 R14 同单，算 extract 还是 clarify | 行为类别 |
| R11 | 08:44 在禁令之前，替代推荐 QuickStitch 是否合适 | 替代车间 |
