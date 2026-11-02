# Contributing

## Branches

- `main` takes changes through pull requests.
- Name branches for the work, for example `closure-detection`.

## Commits

- One commit does one thing; keep the first line under 60 characters.
- Commit under your own account, so the history shows who did what.

## Never

- Change `data/` or `harness/simulate.py`. Extended scenarios go in `scenarios/`.
- Commit an API key. Keys go in `.env`, which is git-ignored.
- Quote a simulator number without its command, seeds and commit.
- Edit the records in `eval/heldout/first_run/`, `first_run.md` or the frozen answers. Later runs get their own record.
