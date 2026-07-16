from datetime import UTC, datetime
from pathlib import Path

import pytest

from mimic.config import Config
from mimic.storage import PersonaStore, _safe, _safe_source
from mimic.types import ProviderKind, SignalsBundle


def _store(tmp_path: Path) -> PersonaStore:
    cfg = Config(home=tmp_path, provider=ProviderKind.ANTHROPIC, model="x")
    return PersonaStore(cfg)


def test_persona_roundtrip(tmp_path: Path):
    s = _store(tmp_path)
    assert not s.exists("andrew")
    s.write_persona("andrew", "# persona\n\n- rule 1\n")
    assert s.exists("andrew")
    assert "rule 1" in s.read_persona("andrew")


def test_legacy_flat_md_is_still_readable(tmp_path: Path):
    s = _store(tmp_path)
    legacy = s.legacy_path("andrew")
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_text("# legacy persona\n", encoding="utf-8")
    assert s.exists("andrew")
    assert "legacy" in s.read_persona("andrew")


def test_delete_user_removes_everything(tmp_path: Path):
    s = _store(tmp_path)
    s.write_persona("andrew", "x")
    s.save_source("andrew", "acme/api", "graphql", None, SignalsBundle())
    assert s.delete_user("andrew")
    assert not s.exists("andrew")


def test_list_users_sees_new_and_legacy(tmp_path: Path):
    s = _store(tmp_path)
    s.write_persona("zoe", "x")
    # legacy flat file
    legacy = s.legacy_path("andrew")
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_text("x", encoding="utf-8")
    assert s.list_users() == ["andrew", "zoe"]


def test_missing_read_raises_with_hint(tmp_path: Path):
    s = _store(tmp_path)
    with pytest.raises(FileNotFoundError, match="mimic learn andrew"):
        s.read_persona("andrew")


def test_rejects_bad_username():
    with pytest.raises(ValueError):
        _safe("../etc/passwd")


def test_source_key_sanitization():
    assert _safe_source("pacific-ai-team/pacific-server") == "pacific-ai-team_pacific-server"
    assert _safe_source("local:/Users/x/foo bar") == "local_Users_x_foo_bar"


def test_save_and_load_sources_accumulates(tmp_path: Path):
    s = _store(tmp_path)
    from mimic.types import CommentKind, ReviewComment

    def _c(repo: str, body: str) -> ReviewComment:
        return ReviewComment(
            kind=CommentKind.REVIEW_COMMENT,
            repo=repo,
            pr_number=1,
            pr_title="t",
            author="jh",
            body=body,
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            url="",
        )

    s.save_source("jh", "acme/api", "graphql", None, SignalsBundle(comments=[_c("acme/api", "one")]))
    s.save_source("jh", "acme/web", "graphql", None, SignalsBundle(comments=[_c("acme/web", "two")]))

    combined, sources = s.load_all_sources("jh")
    assert len(combined.comments) == 2
    assert len(sources) == 2
    assert {src.key for src in sources} == {"acme/api", "acme/web"}


def test_delete_source_leaves_others(tmp_path: Path):
    s = _store(tmp_path)
    s.save_source("jh", "acme/api", "graphql", None, SignalsBundle())
    s.save_source("jh", "acme/web", "graphql", None, SignalsBundle())
    assert s.delete_source("jh", "acme/api")
    remaining = {src.key for src in s.list_sources("jh")}
    assert remaining == {"acme/web"}
