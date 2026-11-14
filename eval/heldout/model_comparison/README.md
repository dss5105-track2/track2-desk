# Held-out messages: which model reads them best

Run on 15 November 2026, after the Sprint 3 review, to check the model chosen on 7 October with development sets only.

- **Code:** `7918ac3`, the main branch of the first held-out run (system code identical to the freeze, `3e9f2ee`), checked out in a temporary worktree. Nothing in the system was changed for or after this comparison.
- **Messages and answers:** `eval/heldout/requests.txt` and `gold_labels.csv`, frozen before the first run.
- **Settings:** prompt v2, code check 2.2, objective `use_slack`, three runs per model (129 replies). No call fell back to the rule parser.
- **Command** (from the worktree root, `--env` pointing at a `.env` with `OPENAI_API_KEY`):

```bash
python eval/run_language_eval.py --inbox eval/heldout/requests.txt --labels eval/heldout/gold_labels.csv --parses "" --tag heldout43 --objective use_slack --parser llm --model gpt-5-nano --runs 3 --env ../track2-desk/.env --out <folder>
```

The GPT-5 mini row is the first run itself (`../first_run/`).

| Model | Right reply type | Refuse | Clarify | Same subtype in all 3 runs | Decision sound | Cost, 129 replies |
|---|---|---|---|---|---|---|
| GPT-5 nano | 87.6% (113/129) | 12/18 | 36/42 | 81.4% | 83.3% | US$0.041 |
| **GPT-5 mini (used)** | **89.1% (115/129)** | 12/18 | 37/42 | 88.4% | 80.8% | US$0.172 |
| GPT-5 | 79.1% (102/129) | 12/18 | 27/42 | 100% | 76.9% | US$1.100 |

**Reading it.** GPT-5 mini is the most accurate of the three; GPT-5 nano is two replies behind at a quarter of the cost but less consistent between runs. GPT-5 gives the same answer every time but declines, in all three runs, seven messages that report a state ("sent it out", "still waiting for the quantity of vests") where the labels ask for a question. Our prompt and checks were written with nano and mini, so this measures GPT-5 with our prompt, not GPT-5 in general. Forty-three messages are too few for the nano–mini gap to be more than a hint.
