# 工具规格表 v0（全组 · 周五评审）

先写规格，再写代码。每个工具写明输入、输出、存在的理由、不做什么、失败模式，以及实现位置。语言层（LLM）只能通过这些工具拿数字。

| 工具 | 输入 | 输出 | 存在的理由 | 不做什么 | 失败模式 | 实现 |
|---|---|---|---|---|---|---|
| `resolve_order_reference` | 结构化请求中的 `order_id` / `customer` / `product` / `order_ref_hint` | 候选订单列表，每单附状态、工序、交期、匹配依据 | 把 "the TrendCart order" 变成具体订单 | 不替人选；多于一个候选就返回给 clarify | 匹配到已完成或 PACKING 订单而不报；客户名拼写变体匹配不到 | `kernel/orders.py: find_orders()` |
| `state_checks` | 订单、今天、账本 | 冲突列表：不存在 / COMPLETE / PACKING / 已过期 / 今天到期 / 本会话已派 | 协议第 3 条 | 不决定行为，只报事实 | 聊天件数或日期与订单表不一致时漏报 | `kernel/orders.py: state_checks()` |
| `check_eligibility` | 车间、品类、件数 | `(可否, 原因)`，原因为 status / makes / max_batch 之一 | 三个问题里的"能做吗""允许吗" | 不看队列 | 件数取聊天值还是订单表值没定义 | `kernel/register.py` |
| `eligibility_table` | 品类、件数、排除名单 | 八家车间每家的可否与原因 | 界面候选表要显示被排除的车间和原因 | 不排序 | 排除原因与不合格原因混在一起 | `kernel/register.py` |
| `get_queue` | 日期 | 每家车间剩余队列天数（来自账本） | "现在接得下吗" | 不预测未到的订单 | 账本没随确认更新 | `kernel/ledger.py: Ledger.queues()` |
| `estimate_delivery` | 车间、件数、队列、发出日、交期 | 队列 / 加工 / 返工期望 / 运输分量，预计完成天数与日期，是否按时，晚几天，成本 | 用数字而不是名声做决定；解释里的数字从这里来 | 不承诺、不改账本 | 返工只能给期望值；完成日期按 Python `round()` 与模拟器一致，0.5 天处可能与直觉相反 | `kernel/estimator.py: estimate()` |
| `rank_candidates` | 请求、目标权重、排除名单、单条偏好 | 排序后的候选，每个附估算和得分分解 | 让目标成为配置 | 不解释 | 没有合格候选时返回空列表，调用方必须处理 | `kernel/allocator.py: Allocator.rank()` |
| `split_estimate` | 品类、件数、队列、日期 | 两家拆单方案及相对单家的收益天数 | 回答 R23 类"拆两家会不会快" | 不写账本；官方模拟器不支持拆单 | 只考虑最快的两家；不计缺陷 | `kernel/estimator.py: split_estimate()` |
| `probe_overload` | 车间、假想批次 | 该车间队列变化；本会话在该车间的已派批次预计完成日变化 | Spec 点名的"把这家压爆会怎样" | 不做分配 | 只看单一车间 | 阶段 1 实现 |
| `commit_allocation` | 请求 id、订单、车间、理由、约束、候选表、目标、请求人、确认人 | 审计记录（含 audit_id、估算、队列前后） | 群聊从未留下的记录 | 未经人确认不得调用 | 重复派单、不合格车间会抛错；最坏情况错派一单，靠 `reassign` 撤销 | `kernel/ledger.py: Ledger.commit()` |
| `reassign` | audit_id、新车间、确认人、理由 | 新审计记录，旧记录标 reassigned | 纠正错派 | 不删除旧记录 | 重放账本时若中间记录已不合格会失败 | `kernel/ledger.py: Ledger.reassign()` |
| `ledger_state` | 无 | 已派批次、各车间队列、会话级约束 | 让后续请求看到前面派单和约束的后果 | 不决策 | 会话丢失后不可恢复（阶段 2 加持久化） | `kernel/ledger.py` |

## 硬红线

- LLM 不做算术。队列、估算、排序、成本全部来自上表工具。
- 解释中的每个数字必须能在本轮工具调用日志里找到。`eval/checker`（阶段 2，张锦若）自动核查。
- 有副作用的只有 `commit_allocation` 与 `reassign`，两者都必须先有人确认。
