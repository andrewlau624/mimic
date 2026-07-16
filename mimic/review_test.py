from mimic.review import _dedupe, _parse, split_diff_by_file
from mimic.types import ChecklistItem


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


def test_split_diff_by_file_basic():
    diff = (
        "diff --git a/foo.py b/foo.py\n"
        "--- a/foo.py\n+++ b/foo.py\n@@ -1 +1 @@\n-old\n+new\n"
        "diff --git a/bar.py b/bar.py\n"
        "new file mode 100644\n--- /dev/null\n+++ b/bar.py\n@@ +1 @@\n+hello\n"
    )
    files = split_diff_by_file(diff)
    assert [(s, p) for s, p, _ in files] == [("M", "foo.py"), ("A", "bar.py")]
    assert all(chunk.startswith("diff --git ") for _, _, chunk in files)


def test_split_diff_empty():
    assert split_diff_by_file("") == []
    assert split_diff_by_file("   \n") == []


def test_dedupe_collapses_similar_concerns():
    items = [
        ChecklistItem(concern="Missing test for exception branch", file="a.py", line=1),
        ChecklistItem(concern="Missing test for exception branch", file="b.py", line=2),
        ChecklistItem(concern="Raw dict crossing queue boundary", file="c.py", line=3),
    ]
    out = _dedupe(items)
    assert [i.file for i in out] == ["a.py", "c.py"]
