# Scenario variants (stress tests for the lateness objective)

The official 120 orders have 14–35 days of slack (median 25) while the Factory Primer says
reorders are due in **7–14 days**. On the official data a six-line earliest-finish rule is
already at ~2 % late, so the primary objective cannot separate policies there. Scenarios
below are parameter transforms of the official data. They never replace the official run;
every report shows the official table first and the scenario tables separately.

| name | transform | why |
|---|---|---|
| `due_7_14` | rescale each order's slack into 7–14 days (seeded) | Primer's reorder window |
| `acc_surge` | add N accessory orders resampled from the existing 35 (new ids, dates) | accessories are the bottleneck (370 pcs/day) |
| `shock_W<k>` | force the closed workshop instead of the seed's draw | the official seed always closes W2 |

Config files are JSON (`due_7_14.json`, `acc_surge.json`). `make_scenario.py` writes a new
data directory under `scenarios/out/<name>/data/` and `run_scenario.py` points the untouched
simulator at it via `simulate.DATA`.

```
python scenarios/make_scenario.py scenarios/due_7_14.json
python scenarios/run_scenario.py scenarios/out/due_7_14 --seeds 5105 1 2 3 4 5
python scenarios/run_scenario.py scenarios/out/due_7_14 --shock --force-target W6
```

Nothing here generates dispatch history, customer quotes or worker data: those questions
must stay unanswerable (evaluation category "decline-to-answer").
