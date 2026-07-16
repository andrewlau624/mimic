import json
import re
from datetime import datetime
from pathlib import Path

from mimic.config import Config
from mimic.types import CommitSample, IssueSample, ReviewComment, SignalsBundle, Source


class PersonaStore:
    """Per-user persona directory: persona.md + raw/*.json + sources.json."""

    def __init__(self, config: Config):
        self._root = config.personas_dir

    def user_dir(self, user: str) -> Path:
        return self._root / _safe(user)

    def persona_path(self, user: str) -> Path:
        return self.user_dir(user) / "persona.md"

    def legacy_path(self, user: str) -> Path:
        return self._root / f"{_safe(user)}.md"

    def raw_dir(self, user: str) -> Path:
        return self.user_dir(user) / "raw"

    def sources_meta_path(self, user: str) -> Path:
        return self.user_dir(user) / "sources.json"

    def exists(self, user: str) -> bool:
        return self.persona_path(user).exists() or self.legacy_path(user).exists()

    def read_persona(self, user: str) -> str:
        p = self.persona_path(user)
        if p.exists():
            return p.read_text(encoding="utf-8")
        legacy = self.legacy_path(user)
        if legacy.exists():
            return legacy.read_text(encoding="utf-8")
        raise FileNotFoundError(f"no persona cached for @{user}. run: mimic learn {user}")

    def write_persona(self, user: str, contents: str) -> Path:
        p = self.persona_path(user)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(contents, encoding="utf-8")
        return p

    def delete_user(self, user: str) -> bool:
        deleted = False
        for p in [self.persona_path(user), self.legacy_path(user)]:
            if p.exists():
                p.unlink()
                deleted = True
        raw = self.raw_dir(user)
        if raw.exists():
            for f in raw.iterdir():
                f.unlink()
            raw.rmdir()
        meta = self.sources_meta_path(user)
        if meta.exists():
            meta.unlink()
        udir = self.user_dir(user)
        if udir.exists() and not any(udir.iterdir()):
            udir.rmdir()
        return deleted

    def list_users(self) -> list[str]:
        if not self._root.exists():
            return []
        users = set()
        for p in self._root.iterdir():
            if p.is_dir() and (p / "persona.md").exists():
                users.add(p.name)
            elif p.is_file() and p.suffix == ".md":
                users.add(p.stem)
        return sorted(users)

    # --- sources -------------------------------------------------------------

    def save_source(
        self,
        user: str,
        source_key: str,
        source_kind: str,
        since: datetime | None,
        bundle: SignalsBundle,
    ) -> Path:
        p = self.raw_dir(user) / f"{_safe_source(source_key)}.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "source_key": source_key,
            "source_kind": source_kind,
            "scraped_at": datetime.now().astimezone().isoformat(),
            "since": since.isoformat() if since else None,
            "comments": [c.model_dump(mode="json") for c in bundle.comments],
            "commits": [c.model_dump(mode="json") for c in bundle.commits],
            "issues": [i.model_dump(mode="json") for i in bundle.issues],
        }
        p.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        self._refresh_meta(user)
        return p

    def load_all_sources(self, user: str) -> tuple[SignalsBundle, list[Source]]:
        combined = SignalsBundle()
        sources: list[Source] = []
        raw = self.raw_dir(user)
        if not raw.exists():
            return combined, sources
        for f in sorted(raw.glob("*.json")):
            data = json.loads(f.read_text(encoding="utf-8"))
            for c in data.get("comments", []):
                combined.comments.append(ReviewComment.model_validate(c))
            for c in data.get("commits", []):
                combined.commits.append(CommitSample.model_validate(c))
            for i in data.get("issues", []):
                combined.issues.append(IssueSample.model_validate(i))
            sources.append(
                Source(
                    key=data["source_key"],
                    kind=data["source_kind"],
                    scraped_at=datetime.fromisoformat(data["scraped_at"]),
                    since=datetime.fromisoformat(data["since"]) if data.get("since") else None,
                    comment_count=len(data.get("comments", [])),
                    commit_count=len(data.get("commits", [])),
                    issue_count=len(data.get("issues", [])),
                )
            )
        return combined, sources

    def list_sources(self, user: str) -> list[Source]:
        _, sources = self.load_all_sources(user)
        return sources

    def delete_source(self, user: str, source_key: str) -> bool:
        p = self.raw_dir(user) / f"{_safe_source(source_key)}.json"
        if not p.exists():
            return False
        p.unlink()
        self._refresh_meta(user)
        return True

    def _refresh_meta(self, user: str) -> None:
        sources = self.list_sources(user)
        meta = {"sources": [s.model_dump(mode="json") for s in sources]}
        self.sources_meta_path(user).write_text(json.dumps(meta, indent=2), encoding="utf-8")


def _safe(user: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", user):
        raise ValueError(f"invalid github username: {user!r}")
    return user.lower()


def _safe_source(key: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", key).strip("_") or "unknown"
