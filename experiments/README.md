# Experiments

The evidence behind the results in the main README. Most write-ups here are working documents in Chinese; tables and scripts are self-explanatory.

| Folder | What it holds | Reproduce |
|---|---|---|
| `scripts/` | Allocator experiments and validation | `python experiments/scripts/exp_round2.py`, `exp_sunday.py`, `validate_allocators.py` |
| `allocator_results/` | Official 10-seed results, fresh order books, promised dates | `exp_round2.py`, `validate_allocators.py` |
| `simulator_assumptions/` | The simulator re-run with Sundays off; closures spotted from the queue | `exp_sunday.py`, `exp_closure.py` |
| `labels/` | Labelling rules, team votes and agreement, frozen labels for the official 30 | `labels/make_labels.py` |
| `language_eval/` | Language scores by run: `baseline`, `improved_prompt`, `grounding_2_1`, `grounding_2_2`, `ablation` | `eval/run_language_eval.py` |
| `language_eval/challenge_set/` | 38 AI-written messages with labels. Used in development, so not a clean test | `make_challenge.py` |
| `failure_cases.md` | Failures found during development | - |

Result files record the commit they were produced at. The held-out test is in [`eval/heldout/`](../eval/heldout/README.md).
