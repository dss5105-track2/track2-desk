# Spotting a closure from the queue

`python experiments/scripts/exp_closure.py` writes `closure_detection.csv`. `harness/simulate.py` is unchanged.

**Method.** `kernel/closure.py` keeps the worst case each workshop's queue could reach, with every batch reworked. A queue above that cannot be a defect, so the workshop is flagged and gets no new work until the unexplained part has run out.

## Late batches under shock

| Seeds | `use_slack` | With the watch | With perfect knowledge |
|---|---|---|---|
| Reported, 5105-5114 | 1.667% | 1.667% | 1.583% |
| Not used while writing it, 6000-6049 | 1.517% | 1.533% | 1.483% |

"Perfect knowledge" is told the closed workshop and sends it nothing during the closure, so it is the most any detector could gain: under 0.1 points. `use_slack` already holds up under this closure. Once one batch is stuck, the queue shows the delay and later batches go elsewhere, and the simulator cannot move a stuck batch. So the watch is not a default setting.

## The detection rate does not carry over to real use

It flags a closure in 52 of 60 shock runs, always on the right workshop, with no false alarm in 60 runs without a closure. **That rate is flattering, so do not quote it as a real-world capability:**

- 40 of the 52 flags come before the closure starts. The simulator adds the whole pause to the queue when a batch is dispatched, so the queue reveals the future. A real queue would show nothing until work stopped.
- The no-new-work window reaches the closure in only 33 of the 52 cases.
- A closure is missed when the workshop gets no batch that touches it.

## At the live desk

The desk has no feed of real queues, so this detector does not run there. A person reports the stop, in chat or on the Workshops tab, and the dispatcher confirms it.
