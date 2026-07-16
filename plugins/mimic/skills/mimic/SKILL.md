---
name: mimic
description: Use when the user wants their code to match a specific GitHub user's coding style before opening a PR, or when they say "mimic", "match", or "write in the style of" any GitHub username (a teammate, a maintainer they admire, anyone with a public review or commit history). Mimic learns their conventions from their PR review comments (what they flag when reviewing others' code) and their commit history (how they structure and name their own code), then checks the current diff against that combined persona. Requires the `mimic` CLI on PATH (`pip install mimic-cli`). If no persona is cached, run `mimic learn <user>` first; then run `mimic review <user>` against the current diff and surface the checklist to the user.
---

# mimic

You are helping the user shape a diff to match a specific GitHub user's coding style before opening a PR. The style comes from two signals: comments that user has left on other people's PRs (what they flag) and code they've written themselves (how they structure things).

## When to invoke

- User says something like "mimic andrewlau624", "write this like simonw would", "match sindresorhus's style", "check this against andrew's conventions".
- Just before running `gh pr create`, if the user has previously used mimic in this repo.

## What to run

1. Confirm the persona exists: `mimic list`.
2. If missing, learn it in host mode (no API key needed, you are the LLM):
   1. `mimic learn <user> [--repo owner/name] [--since YYYY-MM-DD] --dry-run`
   2. Read the printed synthesis prompt, generate the persona as markdown following its rules.
   3. Save it: `mimic learn <user> --body-from -` (pipe your persona in via heredoc).
3. Get the checklist against the current branch:
   `mimic review <user> --base <base-branch>`
   (Default base is `main`. If the repo uses `master` or `develop`, pass `--base` explicitly.)

## What to do with the output

- The checklist prints one bullet per style-mismatch, with `file:line` when available.
- Walk each bullet. Read the referenced code, decide whether the rule actually applies to this diff, and apply the fix if it does. Skip rules that don't apply — the persona is a guide, not law.
- Do not silently rewrite the whole diff. The user wants a targeted pass, not a redo.

## Providers

Default provider is Anthropic (`claude-sonnet-4-6`). Override per-call with `--provider openai|ollama` or globally with `MIMIC_PROVIDER`. The user's chosen provider needs credentials in the environment (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, or a running Ollama daemon).

## Failure modes

- `gh` not installed → tell the user to install it and run `gh auth login`.
- No signal found → the user might have the wrong login, or the target hasn't reviewed or committed to anything public in the scoped window. Confirm the handle and widen `--since`.
- `NO_NITS` output → the diff already matches that persona's style. Say so and move on.
