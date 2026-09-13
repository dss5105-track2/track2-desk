# 标注指南 v0（张锦若 · 周三冻结）

## 流程

1. **独立分类（全员，周二晚前）。** 每人只看 `data/dispatch_requests.txt`、`data/orders.csv`、`data/workshops.csv` 和 `eval/protocol.md`，把 30 条分进官方四类，并写内部子类。**不看任何人的结果，也不要打开 `eval/draft/`。** 交给张锦若。
2. **统计分歧（张锦若，周三会前）。** 每条算六人一致率；一致率低于 5/6 的列入周三讨论。
3. **修订指南（周三会上）。** 讨论结论写进本文件"裁定记录"，然后冻结。
4. **双人正式标注（张锦若、李岩，周四）。** 按冻结指南各自填写 `gold_labels.csv` 的 A 列、B 列，晚上比对，记录 Cohen's kappa。
5. **生成事实部分（吴杰，周四）。** 行为标签定稿后，运行 `python eval/compute_gold_facts.py`，由内核按协议重放，生成每条的候选估算与推荐车间。**标准答案里的数字只能来自这个脚本。**

## 判定顺序

对每条消息依次问：

1. 它是不是在问数据里根本没有的东西？（历史派单、给客户的报价、不存在的订单号、工人、收入）→ `decline-to-answer`
2. 它是不是在问进度而不是派单？ORD-999 这种不存在的订单 → `decline-to-answer`；存在的订单问进度 → 超出本系统范围，也归 `decline-to-answer` 并说明
3. 能不能唯一确定是哪张订单？不能 → `clarify / ambiguous_reference`
4. 订单状态有没有冲突？PACKING、COMPLETE、本会话已派 → `clarify / state_conflict`
5. 派单必需的件数与日期是否齐全（聊天里或订单表里能唯一确定）？不齐 → `clarify / missing_fields`
6. 请求有没有指定一家不合格的车间？有 → `refuse / ineligible_suggestion`
7. 以上都不是：有没有按时方案？有 → `extract / allocate`；没有 → `extract / no_on_time_option`

## 正例与反例

| 类别 | 正例 | 正例 | 反例（看起来像但不是） |
|---|---|---|---|
| decline | R02 问去年十月用了哪家，数据从 2026-01 开始 | R13 问给 TrendCart 的报价，`cost_per_piece` 是车间收我们的价 | R18 看起来是进度查询，但关键是 ORD-999 不存在 |
| clarify / ambiguous | R03 "the TrendCart order"，TrendCart 有 6 单在途 | R29 "the vests"，背心在途 6 单 | R21 说了 "Harbor Knits" 但也给了订单号，不歧义 |
| clarify / state_conflict | R16 ORD-114 在 PACKING | R26 ORD-107 在 PACKING | R20 与 R14 同单，但 R14 未写账本，不算冲突 |
| clarify / missing | R05 新交期"通话后再确认" | R10 "details to follow" | R07 说 "make Mar 31"，日期虽已过但是给了 |
| refuse | R08 FreshStart 上限 300，请求 400 | R11 OldMill 已停牌 | R12 排除 QuickStitch 是用户约束，不是拒绝 |
| extract / allocate | R09 有多家按时，要最快 | R25 排除 BudgetWorks 后仍有按时方案 | R27 要最低缺陷率，但截止日已过，是 no_on_time |
| extract / no_on_time | R17 截止日 3 月 17 日已过 | R06 余量 4 天，最快也要 8 天多 | R23 要拆单，拆单也救不回，仍是 no_on_time |

## 常见错误

- **把排除约束当成拒绝。** "keep it away from BudgetWorks" 是用户约束，系统照做即可，不是 refuse。
- **聊天日期与订单表不一致时自行选一个。** 两者都记下，由状态检查报出。
- **看到 "urgent" 就当成 fastest。** R09 明确说 "fastest turnaround" 才算。
- **忽略跨消息约束。** R12 的 QuickStitch 禁令之后，R17、R21、R25、R30 的候选都要排除 W1。

## 裁定记录

（周三会上填写：条目、分歧、结论、理由）
