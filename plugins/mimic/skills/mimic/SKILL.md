---
name: mimic
description: Use before opening a pull request when the user wants to preempt a specific REVIEWER's nits — a teammate who reviews their PRs. Mimic learns the reviewer's style from every comment they've left on PRs across one or more repos, plus commits they've authored (how they write code themselves), then checks the current diff against that persona. Not for arbitrary GitHub users — the signal is specifically PR review comments, so it only works well for people who actively review code. Requires the `mimic` CLI on PATH (`pip install mimic-cli`). If no persona is cached, run `mimic learn <user> --repo owner/name` first (pass --repo multiple times for cross-repo reviewers); then run `mimic review <user>` against the current diff and surface the checklist to the user.
---

# mimic

You are helping the user shape a diff to preempt a code reviewer's nits before opening a PR. The signal is PR review comments the reviewer has left on other people's code, optionally supplemented by their own commits (how they write code themselves).

## When to invoke

- User says something like "mimic mattpocock", "check this against @matt-at-pacific", "would jonathan flag this", "preempt jonhilgart22".
- Just before running `gh pr create`, if the user has previously used mimic in this repo.

## What to run

1. Confirm the persona exists: `mimic list`.
2. If missing, learn it in host mode (no API key needed, you are the LLM):
   1. `mimic learn <user> --repo owner/name [--repo owner/name2 ...] [--since YYYY-MM-DD] --dry-run`
      - Pass `--repo` multiple times if the reviewer works across several repos in the org — cross-repo signals reinforce shared conventions.
      - `--limit N` caps PRs scanned per repo (default 200 — bump higher for prolific reviewers).
      - `--local /path/to/repo` (once per `--repo`, same order) pulls commit patches from a local checkout.
   2. Read the printed synthesis prompt, generate the persona as markdown following its rules.
   3. Save it: `mimic learn <user> --body-from -` (pipe your persona in via heredoc).
3. Get the checklist against the current branch:
   `mimic review <user> --base <base-branch>`
   (Default base is `main`. If the repo uses `master` or `develop`, pass `--base` explicitly.)

## What to do with the output

- The checklist prints one bullet per style-mismatch, with `file:line` when available.
- Walk each bullet. Read the referenced code, decide whether the rule actually applies to this diff, and apply the fix if it does. Skip rules that don't apply — the persona is a guide, not law.
- Do not silently rewrite the whole diff. The user wants a targeted pass, not a redo.

## Scope note

Mimic is REVIEWER-scoped: it learns from what someone flags when reviewing others' code. It does NOT try to be a general "how this person writes" tool. If the target has no public PR review activity, mimic has nothing to learn from. Pick someone who reviews.

## Providers

Default provider is Anthropic (`claude-sonnet-4-6`). Override per-call with `--provider openai|ollama` or globally with `MIMIC_PROVIDER`. The user's chosen provider needs credentials in the environment (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, or a running Ollama daemon).

## Failure modes

- `gh` not installed → tell the user to install it and run `gh auth login`.
- `--repo` missing → mimic errors: "--repo owner/name is required".
- No signals found → the reviewer might have no comments in the repo/window. Widen `--since` or add another `--repo`.
- `NO_NITS` output → the diff already matches that persona's style. Say so and move on.
