# Mimic

**Write code the way your reviewers want you to.** Point Mimic at a reviewer on your team. It reads every comment they've left on PRs across one or more repos (and, optionally, commits they've authored — how they write code themselves), distills that into a style persona, then checks your diff against it before you push.

Reviewer-scoped: mimic only works well on people who actively review PRs. That teammate who nitpicks every diff, that maintainer whose taste you want to steal.

## Four verbs

```
mimic learn  <user>   scrape a reviewer's PR comments and cache a persona
mimic review <user>   check the current git diff against that persona
mimic show   <user>   print the cached persona
mimic list            list cached personas
mimic rm     <user>   delete one
```

```
$ mimic learn andrewlau624 --repo pacific-ai-team/pacific-server --repo pacific-ai-team/pacific-gateway --since 2026-01-01
scanning pacific-ai-team/pacific-server — up to 200 PRs...
  saved 137 review comments + 42 commits.
scanning pacific-ai-team/pacific-gateway — up to 200 PRs...
  saved 68 review comments + 12 commits.
combined across 2 sources: 205 review comments + 54 commits.
synthesizing...
wrote /Users/you/.mimic/personas/andrewlau624/persona.md

$ mimic review andrewlau624
likely nits from @andrewlau624 (3):
- module-level function doing business logic; refactor into a *Service class (src/spend.py:42)
  → wrap `compute_spend_summary` in a `SpendService` and inject the repo
- raw dict crossing the queue boundary; use a pydantic model (src/spend.py:88)
- missing test for the exception branch in `refresh_spend` (src/spend_test.py:0)
```

## Install

```
pip install mimic-cli[anthropic]
```

Needs `gh` on PATH. Swap `[anthropic]` for `[openai]`, or install with no extras and use a local Ollama.

## Providers

| provider  | env var             | default model         |
| --------- | ------------------- | --------------------- |
| anthropic | `ANTHROPIC_API_KEY` | `claude-sonnet-4-6`   |
| openai    | `OPENAI_API_KEY`    | `gpt-4o`              |
| ollama    | –                   | `llama3.1`            |

Set `MIMIC_PROVIDER` or pass `--provider`. Personas live at `~/.mimic/personas/<user>.md` as plain markdown you can hand-edit.

## Claude Code plugin

```
/plugin marketplace add andrewlau624/mimic
/plugin install mimic
```

Adds `/mimic:learn` and `/mimic:review`.

## License

MIT.
