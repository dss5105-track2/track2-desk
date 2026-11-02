# Spotting a closure from the queue

`python experiments/scripts/exp_closure.py` writes `closure_detection.csv`. `harness/simulate.py` is unchanged.

**Method.** `kernel/closure.py` keeps the worst case each workshop's queue could reach, with every batch reworked. A queue above that cannot be a defect, so the workshop is flagged and gets no new work until the unexplained part has run out.

**Results.** Use `closure_detection.csv` for the numbers.

- No false alarms: 0 flags in 60 runs without a closure, and results identical to plain `use_slack`.
- Flagged 9 of 10 closures on the reported seeds and 43 of 50 on seeds not used while writing it, always on the workshop that closed.
- A closure is missed when the workshop gets no batch that touches the closure, so the queue shows no trace.
- **It does not reduce lateness:** 1.667% with and without on the reported seeds; 1.533% with, 1.517% without on the others.

**Why no gain.** Once one batch is stuck, the queue already shows the delay, so the estimates steer later batches elsewhere anyway. The simulator also cannot move the stuck batch. So we report the detector and do not make it a default setting.

**Limits.**

- The simulator adds the whole pause to the queue when a batch is dispatched, so a flag can come before the closure starts (day 7 for a closure on day 30). A real queue would show nothing until work stopped.
- The live desk has no feed of real queues, so this detector does not run there. At the desk a person reports the stop, in chat or on the Workshops tab, and the dispatcher confirms it. Confirming stops new work and lists batches that can be moved.
