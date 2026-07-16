---
description: Check the current git diff against a cached reviewer persona.
argument-hint: <github-user> [--base main]
---

Run the mimic CLI to get the checklist:

```
mimic review $ARGUMENTS
```

Then walk each item in the checklist:

- Read the referenced `file:line`.
- Decide whether the nit actually applies to this diff — don't blindly apply.
- Fix the ones that do. Explain the ones you're skipping.

If the output is `NO_NITS`, say the diff looks clean against that persona and stop.

If the user hasn't cached a persona yet, offer to run `/mimic:learn <user>` first.
