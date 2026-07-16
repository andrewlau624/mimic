---
description: Scrape a GitHub user's PR comments + commits and cache a style persona.
argument-hint: <github-user> [--repo owner/name] [--since YYYY-MM-DD] [--only pr|commits|all]
---

You're helping the user learn a GitHub user's coding style. Since you (Claude) are already the LLM, do the synthesis yourself instead of making mimic call another API.

Two-step host-mode flow:

1. Scrape and print the synthesis prompt:
   ```
   mimic learn $ARGUMENTS --dry-run
   ```
   This scrapes PR comments + commit history (with truncated diffs on the top-10 commits) and prints the full synthesis prompt to stdout. No LLM call.

2. Read the prompt, generate the persona as pure markdown following the instructions in the prompt, then save it:
   ```
   mimic learn <user> --body-from -
   ```
   Pipe your generated persona into that command (via heredoc or shell redirection).

If `mimic` is not on PATH, tell the user to install it: `pip install mimic-cli`.
If `gh` is not installed or not authenticated, point them at `gh auth login`.

When it finishes, echo the path it wrote and remind the user they can hand-edit the persona at `~/.mimic/personas/<user>.md`.
