from datetime import UTC, datetime

from mimic.types import CommentKind, CommitSample, ReviewComment
from mimic.verbose import render


def _c(repo: str, pr: int, body: str, path: str | None = None, line: int | None = None) -> ReviewComment:
    return ReviewComment(
        kind=CommentKind.REVIEW_COMMENT,
        repo=repo,
        pr_number=pr,
        pr_title="t",
        author="matt",
        body=body,
        path=path,
        line=line,
        created_at=datetime(2026, 3, 1, tzinfo=UTC),
        url="",
    )


def _commit(repo: str, subject: str, body: str = "") -> CommitSample:
    return CommitSample(
        repo=repo,
        sha="abc12345",
        subject=subject,
        body=body,
        created_at=datetime(2026, 3, 1, tzinfo=UTC),
        url="",
    )


def test_verbose_groups_comments_by_repo_then_pr():
    out = render(
        "matt",
        [
            _c("acme/api", 10, "one"),
            _c("acme/api", 11, "two", path="src/x.py", line=42),
            _c("acme/web", 5, "three"),
        ],
        [],
    )
    assert "## acme/api — 2 comments" in out
    assert "## acme/web — 1 comments" in out
    assert "### #10" in out
    assert "### #11" in out
    assert "(src/x.py:42)" in out
    # acme/api should come before acme/web (alphabetical)
    assert out.index("acme/api") < out.index("acme/web")


def test_verbose_lists_commits_grouped_by_repo():
    out = render(
        "matt",
        [],
        [
            _commit("acme/api", "fix: something"),
            _commit("acme/api", "feat: another"),
            _commit("acme/web", "chore: bump"),
        ],
    )
    assert "## commits — acme/api (2)" in out
    assert "## commits — acme/web (1)" in out
    assert "fix: something" in out


def test_verbose_empty_input():
    out = render("matt", [], [])
    assert "@matt" in out
    assert "0 review comments + 0 commits" in out
