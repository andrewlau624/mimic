---
description: Scrape a code reviewer's PR comments + commits across one or more repos and cache a style persona.
argument-hint: <github-user> --repo owner/name [--repo owner/name2 ...] [--since YYYY-MM-DD]
---

You're helping the user learn a code reviewer's style. Since you (Claude) are already the LLM, do the synthesis yourself instead of making mimic call another API.

Two-step host-mode flow:

1. Scrape and print the synthesis prompt:
   ```
   mimic learn $ARGUMENTS --dry-run
   ```
   This lists every PR in each `--repo` (bounded by `--since` and `--limit`), filters review comments and reviews to those by the target user, and prints the full synthesis prompt to stdout. No LLM call.

   For cross-repo reviewers, pass `--repo` multiple times: `--repo acme/api --repo acme/web --repo acme/infra`. Each repo becomes a separate source in the persona.

2. Read the prompt, generate the persona as pure markdown following the instructions in the prompt, then save it:
   ```
   mimic learn <user> --body-from -
   ```
   Pipe your generated persona into that command (via heredoc or shell redirection).

If `mimic` is not on PATH, tell the user to install it: `pip install mimic-cli`.
If `gh` is not installed or not authenticated, point them at `gh auth login`.

When it finishes, echo the path it wrote and remind the user they can hand-edit the persona at `~/.mimic/personas/<user>/persona.md`.

## Scope note

Mimic is REVIEWER-scoped: it learns from what someone flags when reviewing others' code. It does NOT try to profile arbitrary GitHub users. If the target has no public PR review activity in the scoped repo, mimic has nothing to learn from — pick someone who reviews.
