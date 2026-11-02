# Tool specification

Specified before the code was written. The language layer gets numbers only through these tools. Tool names are as they appear in the recorded tool calls, or the logical name of the function listed.

| Tool | Input | Output | Why it exists | What it does not do | Failure mode | Implementation |
|---|---|---|---|---|---|---|
| `resolve_order_reference` | `order_id`, customer, product, or a phrase such as "the TrendCart order" | Candidate orders with status, stage, due date | Turns a loose reference into a specific order | Does not choose: more than one candidate goes back as a question | Misses customer spelling variants | `kernel/orders.py: find_orders()` |
| `state_checks` | Order, today, ledger | Conflicts: not found, complete, packing, overdue, due today, already dispatched this session | Catches an order that should not go out | Does not decide the reply, only reports facts | Chat and order book disagreeing on pieces or date is a note, not a stop | `kernel/orders.py: state_checks()` |
| `check_eligibility` | Workshop, category, pieces | Yes or no, with the reason: status, makes or batch limit | "Can they make it?" and "Are they allowed to?" | Does not look at the queue | Assumes the register is current | `kernel/register.py` |
| `eligibility_table` | Category, pieces, exclusions | All eight workshops with yes or no and the reason | Shows the dispatcher who was ruled out and why | Does not rank | An exclusion and an ineligibility can read alike | `kernel/register.py` |
| `get_queue` | Date | Days of queue left per workshop, from the ledger | "Can they take it now?" | Does not predict orders yet to arrive | Does not notice a workshop that has stopped | `kernel/ledger.py: Ledger.queues()` |
| `estimate_delivery` | Workshop, pieces, queue, send date, due date | Queue, work, expected rework and transport; two return dates; on time or not; days late; cost | Decisions and explanations rest on these numbers | Promises nothing and does not touch the ledger | Rework is an expected value; assumes a seven-day week | `kernel/estimator.py: estimate()` |
| `rank_candidates` | Batch, objective, exclusions, one-off preference | Ranked candidates with their estimates | Makes the objective a setting | Does not explain | Empty when nobody is eligible; the caller must handle it | `kernel/allocator.py: Allocator.rank()` |
| `split_estimate` | Category, pieces, queues, date | The best two-shop split and the days it gains | Answers "would splitting be faster?" | Does not write to the ledger; the official simulator has no splits | Considers only the two fastest shops; ignores defects | `kernel/estimator.py: split_estimate()` |
| `workshop_batches` | Workshop | Batches dispatched there | Shows what a stoppage affects | Does not move anything | Knows only batches confirmed at this desk | `desk/pipeline.py: Desk._batches_at()` |
| `commit_allocation` | Request, order, workshop, reason, candidates, objective, requester, confirmer | Audit record with estimate and queues before and after | The record the group chat never kept | Never runs without a person confirming | Raises on a repeat dispatch or an ineligible shop | `kernel/ledger.py: Ledger.commit()` |
| `reassign` | Audit id, new workshop, confirmer, reason | New audit record; the old one is marked reassigned | Corrects a wrong dispatch | Never deletes the old record | Replay fails if an earlier record is no longer eligible | `kernel/ledger.py: Ledger.reassign()` |

## Hard rules

- The model does no arithmetic. Queues, estimates, ranking and cost come from these tools.
- Every number in an explanation must be found in this turn's tool calls; `number_check()` in `desk/pipeline.py` verifies it.
- Only `commit_allocation` and `reassign` have side effects, and both need a person's confirmation.
