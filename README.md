# Mimic

**Write code the way your reviewers want you to.** Point Mimic at any GitHub user. It reads their PR comments, learns the nits they always flag, and checks your diff against their style before you push. Your toughest reviewer, or a maintainer whose taste you want to steal.

## Four verbs

```
mimic learn  <user>   scrape a reviewer's PR comments and cache a persona
mimic review <user>   check the current git diff against that persona
mimic show   <user>   print the cached persona
mimic list            list cached personas
mimic rm     <user>   delete one
```

```
$ mimic learn andrewlau624 --repo pacific-ai-team/pacific-server --since 2026-01-01
scanning up to 50 PRs for @andrewlau624...
kept 137 signal-bearing comments. synthesizing...
wrote /Users/you/.mimic/personas/andrewlau624.md

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
