# Held-out messages: which model reads them best

Run on 15 November 2026, after the Sprint 3 review, to check the model chosen on 7 October with development sets only. Every model listed got one message first, to check it worked with the frozen code; no call in the runs below fell back to the rule parser.

- **Code:** `7918ac3`, the main branch of the first held-out run (system code identical to the freeze, `3e9f2ee`), checked out in a temporary worktree. Nothing in the system was changed for or after this comparison.
- **Messages and answers:** `eval/heldout/requests.txt` and `gold_labels.csv`, frozen before the first run.
- **Settings:** prompt v2, code check 2.2, objective `use_slack`, three runs per model (129 replies). No call fell back to the rule parser.
- **Command** (from the worktree root, `--env` pointing at a `.env` with `OPENAI_API_KEY`):

```bash
python eval/run_language_eval.py --inbox eval/heldout/requests.txt --labels eval/heldout/gold_labels.csv --parses "" --tag heldout43 --objective use_slack --parser llm --model gpt-5-nano --runs 3 --env ../track2-desk/.env --out <folder>
```

The GPT-5 mini row is the first run itself (`../first_run/`).

| Model | Right reply type | Refuse | Clarify | Same subtype in all 3 runs | Decision sound | Cost per message |
|---|---|---|---|---|---|---|
| GPT-5 nano | 87.6% (113/129) | 12/18 | 36/42 | 81.4% | 83.3% | US$0.0003 |
| **GPT-5 mini (used)** | **89.1% (115/129)** | 12/18 | 37/42 | 88.4% | 80.8% | US$0.0013 |
| GPT-5 | 79.1% (102/129) | 12/18 | 27/42 | 100% | 76.9% | US$0.0085 |
| GPT-5.4 nano | 86.8% (112/129) | 12/18 | 34/42 | 95.3% | 80.8% | US$0.0007 |
| GPT-5.4 mini | 87.6% (113/129) | 12/18 | 35/42 | 97.7% | 79.5% | US$0.0027 |
| GPT-5.6 luna | 89.1% (115/129) | 12/18 | 37/42 | 95.3% | 80.8% | US$0.0007 |

**Costs.** The frozen code prices every model it does not know as GPT-5 mini, so `spent_usd` in the three newer JSON files is wrong. The cost column uses the token counts from those runs and the standard prices on developers.openai.com/api/docs/pricing on 15 November 2026 (USD per million input / output tokens): GPT-5.4 mini 0.75 / 4.50, GPT-5.4 nano 0.20 / 1.25, GPT-5.6 luna 0.20 / 1.20. GPT-5.6 sol (4.00 / 20.00) and terra (2.00 / 12.00) were tried on one message each but not run: at 8–16 times the price of GPT-5 mini they would not be used for this task.

**Reading it.** GPT-5 mini and GPT-5.6 luna share the best score, 115 of 129; luna is more consistent between runs and costs half as much, but it was tried only after the held-out set had been seen, so choosing it now would be choosing on the test. GPT-5.4 mini and nano are more consistent than GPT-5 mini but slightly less accurate. Among the first three, GPT-5 nano is two replies behind at a quarter of the cost but less consistent between runs. GPT-5 gives the same answer every time but declines, in all three runs, seven messages that report a state ("sent it out", "still waiting for the quantity of vests") where the labels ask for a question. Our prompt and checks were written with nano and mini, so this measures GPT-5 with our prompt, not GPT-5 in general. Forty-three messages are too few for the nano–mini gap to be more than a hint.
