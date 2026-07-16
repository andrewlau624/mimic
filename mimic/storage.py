import re
from pathlib import Path

from mimic.config import Config


class PersonaStore:
    def __init__(self, config: Config):
        self._dir = config.personas_dir

    def path(self, user: str) -> Path:
        safe = _safe(user)
        return self._dir / f"{safe}.md"

    def exists(self, user: str) -> bool:
        return self.path(user).exists()

    def read(self, user: str) -> str:
        p = self.path(user)
        if not p.exists():
            raise FileNotFoundError(f"no persona cached for @{user}. run: mimic learn {user}")
        return p.read_text(encoding="utf-8")

    def write(self, user: str, contents: str) -> Path:
        p = self.path(user)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(contents, encoding="utf-8")
        return p

    def delete(self, user: str) -> bool:
        p = self.path(user)
        if not p.exists():
            return False
        p.unlink()
        return True

    def list_users(self) -> list[str]:
        if not self._dir.exists():
            return []
        return sorted(p.stem for p in self._dir.glob("*.md"))


def _safe(user: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", user):
        raise ValueError(f"invalid github username: {user!r}")
    return user.lower()
