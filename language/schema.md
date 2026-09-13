# Structured request schema v0（李岩 · 待周三冻结）

每条群聊消息被解析成一个 JSON 对象。LLM 解析器和规则回退解析器（`llm/llm_client.py`）输出**同一个** schema，语言层后续步骤只认这个结构。

## 字段

| 字段 | 类型 | 必填 | 含义 | 来源 |
|---|---|---|---|---|
| `request_id` | str | 是 | `R01`…；留出集用 `H01`… | 行首 |
| `timestamp` | str `HH:MM` | 是 | 消息时间，协议按它排序 | 行首 |
| `requester` | str | 是 | 发消息的人，约束的"下达人" | 行首 |
| `raw_text` | str | 是 | 原文，审计用 | 行首之后 |
| `question_type` | enum | 是 | `allocation` 派单 / `status` 进度查询 / `information` 信息查询 | 解析 |
| `order_id` | str \| null | 否 | `ORD-xxx`；聊天未给出则为 null，**不猜** | 解析 |
| `order_ref_hint` | str \| null | 否 | 未给订单号时的指代原文，如 "the TrendCart order"、"that big reorder" | 解析 |
| `customer` | str \| null | 否 | 必须是 orders.csv 中 8 个客户之一 | 解析 |
| `product` | str \| null | 否 | orders.csv 的 7 种产品之一 | 解析 |
| `category` | enum \| null | 否 | `TOPS` / `ACCESSORIES`；由 product 推出 | 推导 |
| `pieces` | int \| null | 否 | **聊天里说的**件数；与 orders.csv 不一致时两者都保留，由状态检查报出 | 解析 |
| `due_date` | ISO date \| null | 否 | **聊天里说的**日期（"back by Mar 17"、"ship date Apr 05"、"Deadline Apr 05"） | 解析 |
| `forced_workshop` | str \| null | 否 | 请求指定的车间 id（"Send ... to FreshStart"） | 解析 |
| `excluded_workshops` | list[str] | 是 | 请求排除的车间 id | 解析 |
| `constraint_scope` | enum | 是 | `request` 仅本条 / `session` 本会话持续（"nothing new to QuickStitch **this week**"） | 解析 |
| `preference` | enum | 是 | `none` / `fastest` / `cheapest_on_time` / `lowest_defect` / `split` | 解析 |
| `references_prior` | str \| null | 否 | 引用的前序请求 id（R15 → R10） | 跨消息记忆 |
| `missing_fields` | list[str] | 是 | 派单所缺字段，驱动追问 | 规则 |
| `parser` | str | 是 | `rules` 或 `llm:<model>` | 系统 |
| `notes` | list[str] | 是 | 解析时的提示，如 "same order as R14"、"fallback: RuntimeError" | 系统 |

## 规则

1. **只从原文提取，不从 orders.csv 反填。** 聊天没说件数，`pieces` 就是 null。与订单表的比对是下一步状态检查的事，不是解析的事。这样"解析是否正确"和"查表是否正确"能分开评估。
2. **日期一律按 2026 年解析。** "Mar 31" → `2026-03-31`。
3. **车间名映射到 id。** QuickStitch W1、SteadyHands W2、BudgetWorks W3、Little Loom W4、GiantWeave W5、Nimble Needle W6、OldMill W7、FreshStart W8。
4. **排除优先于指定。** 同一句里既提到又说"away from / nothing new to / avoid"的，归入 `excluded_workshops`。
5. **`constraint_scope = session` 的约束对之后所有请求生效**，并记录下达人和来源请求。当前 30 条里唯一的例子是 R12 Boss 的 "nothing new to QuickStitch this week"。
6. **`question_type` 不是派单时**，`missing_fields` 为空，由行为路由直接走 decline 或 status。

## 例子

R12 原文：`ORD-053 — 800 polo shirts for UrbanThread, due Apr 10. Boss says nothing new to QuickStitch this week, they're swamped.`

```json
{
  "request_id": "R12", "timestamp": "08:48", "requester": "Ravi",
  "question_type": "allocation",
  "order_id": "ORD-053", "order_ref_hint": null,
  "customer": "UrbanThread", "product": "Polo shirt", "category": "TOPS",
  "pieces": 800, "due_date": "2026-04-10",
  "forced_workshop": null, "excluded_workshops": ["W1"], "constraint_scope": "session",
  "preference": "none", "references_prior": null, "missing_fields": [],
  "parser": "manual", "notes": ["exclusion imposed by Boss, relayed by Ravi"]
}
```

完整 30 条手工解析见 `requests_gold.json`。
