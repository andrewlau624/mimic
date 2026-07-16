---
description: Scrape a GitHub user's PR comments into a cached reviewer persona.
argument-hint: <github-user> [--repo owner/name] [--since YYYY-MM-DD]
---

Run the mimic CLI to learn a reviewer's style:

```
mimic learn $ARGUMENTS
```

If `mimic` is not on PATH, tell the user to install it: `pip install mimic-cli`.
If `gh` is not installed or not authenticated, point them at `gh auth login`.

When it finishes, echo the path it wrote and remind the user they can hand-edit the persona at `~/.mimic/personas/<user>.md`.
