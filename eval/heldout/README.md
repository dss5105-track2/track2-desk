# Held-out inbox

43 chat messages written by team members, with answers frozen before the system first saw them. This is the only clean language test; the official 30 and the 38-message challenge set were used in development.

## How it was built

- **Writing.** Wu Jie, Wu Ruohan, Qu Yanyue and Zhang Jinruo each wrote 11 messages from a scenario skeleton (44 in all). Writers did not touch the prompt, parser or `llm/`. Claude drafted the skeletons.
- **Labelling.** Two members who had not written a message labelled it independently, without AI.
- **Settling.** 32 of 44 agreed at once with the skeleton's intent. The 12 disagreements (27.3%) were settled under the team's written rules; Claude proposed the resolutions and the team accepted them. H24 was judged on its wording, and H43 was dropped because its text did not match its skeleton.
- **Exposure.** Before the first run Claude had seen the messages, through the annotation sheets. The code under test (`3e9f2ee`, 7 October) predates the messages, and nothing changed before the first run.

## Results: right response type

| Run | Status | Rules | GPT-5 mini, 3 runs | Record |
|---|---|---|---|---|
| First | **Clean** | 86.0% (37/43) | **89.1%** (115/129) | [`first_run.md`](first_run.md) |
| Reproduction by Li Yan | Clean, same code | 86.0%, identical line by line | 88.4% (114/129) | [`reproduce_liyan/`](reproduce_liyan/REPRODUCE.md) |
| Second | **Not clean: fixes followed the first run's errors** | 88.4% (38/43) | 92.2% (119/129) | [`second_run.md`](second_run.md) |

The team target was 90%. The first run missed it, and that figure stands.

## Limitation

The frozen answers do not list standing exclusions in force, so the decision check does not test whether they were honoured, and can mark honouring one as wrong (H35, H38). Response type is the main metric.

## Reproduce

From the repository root, on `main`:

```bash
python eval/heldout/reproduce_heldout.py --name yourname
```

This runs the recorded commit in a temporary worktree and compares the result with the record. Add `--llm` to run GPT-5 mini too (about $0.17, needs `.env`).

The run records are in Chinese and kept as written.
