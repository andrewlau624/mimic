---
name: mimic
description: Use before opening a pull request when the user wants to preempt a reviewer's nits, or when they ask to "mimic", "match", or "check against" any GitHub user's style (a teammate, or a maintainer they admire). Requires the `mimic` CLI on PATH (`pip install mimic-cli`). If no persona is cached, run `mimic learn <user>` first; then run `mimic review <user>` against the current diff and surface the checklist to the user.
---

# mimic

You are helping the user tighten a diff against a specific reviewer's known nits before they open a PR.

## When to invoke

- User says something like "mimic andrewlau624", "check this against andrew's style", "what would andrew flag".
- Just before running `gh pr create`, if the user has previously used mimic in this repo.

## What to run

1. Confirm the persona exists: `mimic list`.
2. If missing, ask the user for a date bound and (optionally) a repo, then:
   `mimic learn <user> [--repo owner/name] [--since YYYY-MM-DD]`
3. Get the checklist against the current branch:
   `mimic review <user> --base <base-branch>`
   (Default base is `main`. If the repo uses `master` or `develop`, pass `--base` explicitly.)

## What to do with the output

- The checklist prints one nit per bullet with `file:line` when available.
- Walk each nit. For each: read the referenced code, decide whether it's a real fit for this diff, and apply the fix if it is. Skip nits that don't apply — the persona is a hint, not law.
- Do not silently rewrite the whole diff. The user wants review, not a redo.

## Providers

Default provider is Anthropic (`claude-sonnet-4-6`). Override per-call with `--provider openai|ollama` or globally with `MIMIC_PROVIDER`. The user's chosen provider must have credentials in the environment (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, or a running Ollama daemon).

## Failure modes

- `gh` not installed → tell the user to install it and run `gh auth login`.
- No comments found → the user might have the wrong login, or the person hasn't reviewed anything public. Confirm the handle.
- `NO_NITS` output → the diff is clean against that persona. Say so and move on.
