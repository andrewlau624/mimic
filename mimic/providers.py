import os
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
            system=system,
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


def build(config: Config) -> Provider:
    match config.provider:
        case ProviderKind.ANTHROPIC:
            return AnthropicProvider(config.model)
        case ProviderKind.OPENAI:
            return OpenAIProvider(config.model)
        case ProviderKind.OLLAMA:
            return OllamaProvider(config.model, config.ollama_base_url)
        case _:
            raise NotImplementedError(f"unknown provider: {config.provider}")
