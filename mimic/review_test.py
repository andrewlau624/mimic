from mimic.review import _parse


def test_no_nits_sentinel_yields_empty():
    c = _parse("andrew", "NO_NITS")
    assert c.items == []


def test_parses_bullet_with_file_line():
    raw = "- Missing test for exception branch [server/spend.py:88]"
    c = _parse("andrew", raw)
    assert len(c.items) == 1
    item = c.items[0]
    assert item.file == "server/spend.py"
    assert item.line == 88
    assert "Missing test" in item.concern


def test_parses_bullet_with_suggestion_second_line():
    raw = "- Raw dict crossing queue boundary [q.py:12]\n  → use Pydantic model"
    c = _parse("andrew", raw)
    assert len(c.items) == 1
    assert c.items[0].suggestion == "use Pydantic model"


def test_multiple_items_render_cleanly():
    raw = "- A [f.py:1]\n- B [g.py:2]\n  → do B'\n- C"
    c = _parse("andrew", raw)
    assert [i.concern for i in c.items] == ["A", "B", "C"]
    assert c.items[1].suggestion == "do B'"
    assert c.items[2].file is None
