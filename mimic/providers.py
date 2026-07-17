import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Protocol

import httpx

from mimic.config import Config
from mimic.types import ProviderKind


class Provider(Protocol):
    name: ProviderKind
    model: str

    def complete(self, system: str, user: str) -> str: ...


class AnthropicProvider:
    name = ProviderKind.ANTHROPIC

    def __init__(self, model: str):
        try:
            from anthropic import Anthropic
        except ImportError as e:
            raise ImportError(
                "the anthropic package is required. install: pip install mimic-cli[anthropic]"
            ) from e
        key = os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise RuntimeError("ANTHROPIC_API_KEY is not set.")
        self._client = Anthropic(api_key=key)
        self.model = model

    def complete(self, system: str, user: str) -> str:
        msg = self._client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user}],
        )
        return "".join(block.text for block in msg.content if getattr(block, "type", "") == "text")


class OpenAIProvider:
    name = ProviderKind.OPENAI

    def __init__(self, model: str):
        try:
            from openai import OpenAI
        except ImportError as e:
            raise ImportError(
                "the openai package is required. install: pip install mimic-cli[openai]"
            ) from e
        key = os.environ.get("OPENAI_API_KEY")
        if not key:
            raise RuntimeError("OPENAI_API_KEY is not set.")
        self._client = OpenAI(api_key=key)
        self.model = model

    def complete(self, system: str, user: str) -> str:
        resp = self._client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return resp.choices[0].message.content or ""


class OllamaProvider:
    name = ProviderKind.OLLAMA

    def __init__(self, model: str, base_url: str):
        self.model = model
        self._base_url = base_url.rstrip("/")

    def complete(self, system: str, user: str) -> str:
        r = httpx.post(
            f"{self._base_url}/api/chat",
            json={
                "model": self.model,
                "stream": False,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            },
            timeout=300,
        )
        r.raise_for_status()
        return r.json().get("message", {}).get("content", "")


class ClaudeCliProvider:
    """Shells out to `claude -p`; uses local Claude Code auth."""

    name = ProviderKind.CLAUDE

    def __init__(self, model: str):
        binary = shutil.which("claude")
        if not binary:
            raise RuntimeError(
                "the `claude` CLI is not on PATH. install Claude Code, or use --provider anthropic."
            )
        self._binary = binary
        self.model = model

    def complete(self, system: str, user: str) -> str:
        cmd = [
            self._binary,
            "-p",
            "--output-format", "text",
            "--system-prompt", system,
            "--model", self.model,
            "--no-session-persistence",
        ]
        result = subprocess.run(
            cmd,
            input=user,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"claude -p failed (exit {result.returncode}): {result.stderr.strip() or result.stdout.strip()}"
            )
        return result.stdout


class CodexCliProvider:
    """Shells out to `codex exec`; uses local Codex auth."""

    name = ProviderKind.CODEX

    def __init__(self, model: str):
        binary = shutil.which("codex")
        if not binary:
            raise RuntimeError(
                "the `codex` CLI is not on PATH. install Codex, or use --provider openai."
            )
        self._binary = binary
        self.model = model

    def complete(self, system: str, user: str) -> str:
        prompt = f"{system}\n\n---\n\n{user}"
        with tempfile.NamedTemporaryFile(mode="w+", suffix=".txt", delete=False) as tmp:
            out_path = Path(tmp.name)
        try:
            cmd = [
                self._binary,
                "exec",
                "--model", self.model,
                "--skip-git-repo-check",
                "--sandbox", "read-only",
                "--ephemeral",
                "--color", "never",
                "--output-last-message", str(out_path),
                "-",
            ]
            result = subprocess.run(
                cmd,
                input=prompt,
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode != 0:
                raise RuntimeError(
                    f"codex exec failed (exit {result.returncode}): {result.stderr.strip() or result.stdout.strip()}"
                )
            return out_path.read_text(encoding="utf-8")
        finally:
            out_path.unlink(missing_ok=True)


def build(config: Config) -> Provider:
    match config.provider:
        case ProviderKind.ANTHROPIC:
            return AnthropicProvider(config.model)
        case ProviderKind.OPENAI:
            return OpenAIProvider(config.model)
        case ProviderKind.OLLAMA:
            return OllamaProvider(config.model, config.ollama_base_url)
        case ProviderKind.CLAUDE:
            return ClaudeCliProvider(config.model)
        case ProviderKind.CODEX:
            return CodexCliProvider(config.model)
        case _:
            raise NotImplementedError(f"unknown provider: {config.provider}")
