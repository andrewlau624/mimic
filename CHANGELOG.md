# Changelog

## 0.1.0

First cut. `learn` scrapes a reviewer's PR comments via `gh` and asks the configured provider to boil them into a persona doc. `review` checks a git diff against that persona and prints a short list of likely nits. Providers: anthropic (default), openai, ollama. Ships as a Claude Code plugin with `/mimic:learn` and `/mimic:review` slash commands.
