# Architecture

Original design by Xu Peiyao and Wu Jie.

```mermaid
flowchart LR
    subgraph IN[Input]
        CHAT[Chat message]
    end

    subgraph L2[Language layer: the model only reads and narrates]
        PARSE[Parse<br/>GPT-5 mini or rules]
        GROUND[Check values<br/>against the text]
        CHECK[Order state checks]
        ROUTE{Route the reply}
        EXPLAIN[Explain from<br/>tool outputs]
        VERIFY[Number check]
    end

    subgraph L1[Kernel: deterministic, no LLM]
        REG[Workshop register]
        ORD[Order book]
        EST[Date estimator]
        RANK[Allocator<br/>objective is a setting]
        LEDGER[(Queue ledger<br/>and audit record)]
    end

    subgraph L3[Dispatcher interface]
        INBOX[Inbox by next step]
        CARD[Decision card]
        CONFIRM[Confirm, change, ask]
        AUDIT[Audit log]
    end

    SIM[[Shared simulator]]

    CHAT --> PARSE --> GROUND --> CHECK
    CHECK <--> ORD
    CHECK --> ROUTE
    ROUTE -- ask, refuse, cannot answer --> EXPLAIN
    ROUTE -- dispatch --> RANK
    RANK <--> REG
    RANK <--> EST
    EST <--> LEDGER
    RANK --> EXPLAIN --> VERIFY --> CARD
    INBOX --> CARD --> CONFIRM
    CONFIRM -- after a person confirms --> LEDGER
    LEDGER --> AUDIT
    SIM -. allocator interface .-> RANK
```

## Kernel entry points

The language layer and the interface call the kernel through these four:

| Entry | Location | Signature |
|---|---|---|
| eligible | `kernel/register.py` | `eligible_workshops(workshops, category, pieces, exclude=()) -> list[Workshop]` |
| estimate | `kernel/estimator.py` | `estimate(w, pieces, queue_days, sent_date, due_date, include_rework=True) -> Estimate` |
| rank | `kernel/allocator.py` | `Allocator(objective).rank(batch, workshops, queues, exclude=(), preference=None) -> list[dict]` |
| commit | `kernel/ledger.py` | `Ledger.commit(request_id=, order_id=, workshop_id=, ..., confirmed_by=) -> dict` |

The simulator sees only `Allocator.__call__(batch, workshops, queues) -> workshop_id`. The language layer takes no part in simulator runs.
