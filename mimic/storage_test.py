from pathlib import Path

import pytest

from mimic.config import Config
from mimic.storage import PersonaStore, _safe
from mimic.types import ProviderKind


def _store(tmp_path: Path) -> PersonaStore:
    cfg = Config(home=tmp_path, provider=ProviderKind.ANTHROPIC, model="x")
    return PersonaStore(cfg)


def test_roundtrip(tmp_path: Path):
    s = _store(tmp_path)
    assert not s.exists("andrew")
    s.write("andrew", "# persona\n\n- rule 1\n")
    assert s.exists("andrew")
    assert "rule 1" in s.read("andrew")


def test_delete(tmp_path: Path):
    s = _store(tmp_path)
    s.write("andrew", "x")
    assert s.delete("andrew")
    assert not s.delete("andrew")


def test_list_sorted(tmp_path: Path):
    s = _store(tmp_path)
    for u in ["zoe", "andrew", "mia"]:
        s.write(u, "x")
    assert s.list_users() == ["andrew", "mia", "zoe"]


def test_missing_read_raises_with_hint(tmp_path: Path):
    s = _store(tmp_path)
    with pytest.raises(FileNotFoundError, match="mimic learn andrew"):
        s.read("andrew")


def test_rejects_bad_username():
    with pytest.raises(ValueError):
        _safe("../etc/passwd")
