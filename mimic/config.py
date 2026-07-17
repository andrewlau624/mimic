import os
from pathlib import Path

from pydantic import BaseModel

from mimic.types import ProviderKind

DEFAULT_HOME = Path.home() / ".mimic"
DEFAULT_MODEL_BY_PROVIDER = {
    ProviderKind.ANTHROPIC: "claude-sonnet-4-6",
    ProviderKind.OPENAI: "gpt-4o",
    ProviderKind.OLLAMA: "llama3.1",
    ProviderKind.CLAUDE: "sonnet",
    ProviderKind.CODEX: "gpt-5-codex",
}


class Config(BaseModel):
    home: Path
    provider: ProviderKind
    model: str
    ollama_base_url: str = "http://localhost:11434"

    @property
    def personas_dir(self) -> Path:
        return self.home / "personas"


def load() -> Config:
    home = Path(os.environ.get("MIMIC_HOME", DEFAULT_HOME)).expanduser()
    provider_raw = os.environ.get("MIMIC_PROVIDER", ProviderKind.ANTHROPIC.value).lower()
    try:
        provider = ProviderKind(provider_raw)
    except ValueError as e:
        raise ValueError(
            f"unknown MIMIC_PROVIDER '{provider_raw}'. "
            f"expected one of: {', '.join(p.value for p in ProviderKind)}"
        ) from e
    model = os.environ.get("MIMIC_MODEL") or DEFAULT_MODEL_BY_PROVIDER[provider]
    ollama = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
    return Config(home=home, provider=provider, model=model, ollama_base_url=ollama)
