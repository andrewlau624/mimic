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
$ mimic learn charliermarsh --repo astral-sh/ruff --repo astral-sh/uv --since 2025-01-01
scanning astral-sh/ruff — up to 200 PRs...
  saved 214 review comments + 38 commits.
scanning astral-sh/uv — up to 200 PRs...
  saved 126 review comments + 17 commits.
combined across 2 sources: 340 review comments + 55 commits.
synthesizing...
wrote /Users/you/.mimic/personas/charliermarsh/persona.md

$ mimic review charliermarsh
likely nits from @charliermarsh (4):
- new dependency added without an entry in the "why we need it" note — prefer stdlib or an existing dep (pyproject.toml:34)
  → drop the `pendulum` dep; the two datetime ops here work with stdlib `datetime` + `zoneinfo`
- `Any` on a public function return type; widen only when the shape is genuinely open (src/cli/resolver.py:88)
  → return `ResolvedTarget | None` — the only two shapes callers actually get
- test doesn't cover the error branch of `parse_manifest` (tests/test_manifest.py)
  → add a `test_parse_manifest_raises_on_missing_field` fixture with a minimal invalid manifest
- long-form `--verbose` without a short `-v` alias; every other flag has both (src/cli/args.py:112)
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
