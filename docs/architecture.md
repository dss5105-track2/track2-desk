# 架构 v0（许佩瑶 · 吴杰）

GitHub 会直接渲染下面的 Mermaid 图。Sprint 1 的幻灯片版由许佩瑶据此重画。

```mermaid
flowchart LR
    subgraph IN[输入]
        CHAT[群聊消息<br/>dispatch_requests.txt]
    end

    subgraph L2[Layer 2 · 语言层 · LLM 只做理解与叙述]
        PARSE[解析<br/>LLM 或规则回退]
        CHECK[状态交叉检查]
        ROUTE{行为路由}
        EXPLAIN[按工具输出生成解释]
        VERIFY[数字回溯核查器]
    end

    subgraph L1[Layer 1 · 确定性内核 · 零 LLM]
        REG[车间登记册<br/>check_eligibility]
        ORD[订单表<br/>resolve / state_checks]
        EST[交期估算器]
        RANK[可配置目标分配器]
        LEDGER[(队列账本<br/>+ 审计记录)]
    end

    subgraph L3[Layer 3 · 调度员界面]
        INBOX[收件箱视图]
        CARD[单条请求视图<br/>候选 · 估算 · 推荐 · 理由]
        CONFIRM[确认 / 改派 / 追问]
        AUDIT[审计记录视图]
    end

    SIM[[simulate.py<br/>官方模拟器]]

    CHAT --> PARSE --> CHECK
    CHECK <--> ORD
    CHECK --> ROUTE
    ROUTE -- clarify / refuse / decline --> EXPLAIN
    ROUTE -- extract --> RANK
    RANK <--> REG
    RANK <--> EST
    EST <--> LEDGER
    RANK --> EXPLAIN --> VERIFY --> CARD
    INBOX --> CARD --> CONFIRM
    CONFIRM -- 人确认后 --> LEDGER
    LEDGER --> AUDIT
    SIM -. allocator 接口 .-> RANK
```

## 接口冻结（周五）

内核对外只暴露四个入口，语言层与界面只调这四个：

| 入口 | 位置 | 签名 |
|---|---|---|
| eligible | `kernel/register.py` | `eligible_workshops(workshops, category, pieces, exclude=()) -> list[Workshop]` |
| estimate | `kernel/estimator.py` | `estimate(w, pieces, queue_days, sent_date, due_date, include_rework=True) -> Estimate` |
| rank | `kernel/allocator.py` | `Allocator(objective).rank(batch, workshops, queues, exclude=(), preference=None) -> list[dict]` |
| commit | `kernel/ledger.py` | `Ledger.commit(request_id=, order_id=, workshop_id=, ..., confirmed_by=) -> dict` |

模拟器只看到 `Allocator.__call__(batch, workshops, queues) -> workshop_id`。语言层在模拟器实验中完全不参与。
