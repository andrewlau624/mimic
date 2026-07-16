from datetime import UTC, datetime

from mimic.scrape import _filter_signal
from mimic.types import CommentKind, ReviewComment


def _c(body: str, when: datetime | None = None) -> ReviewComment:
    return ReviewComment(
        kind=CommentKind.REVIEW_COMMENT,
        repo="o/r",
        pr_number=1,
        pr_title="t",
        author="andrew",
        body=body,
        created_at=when or datetime(2026, 1, 1, tzinfo=UTC),
        url="",
    )


def test_drops_lgtm_and_thanks():
    kept = _filter_signal(
        [
            _c("lgtm"),
            _c("Thanks!"),
            _c("👍"),
            _c("Prefer a Pydantic model here instead of a raw dict"),
        ],
        since=None,
    )
    bodies = [c.body for c in kept]
    assert bodies == ["Prefer a Pydantic model here instead of a raw dict"]


def test_drops_short_comments():
    kept = _filter_signal([_c("nit: typo"), _c("Prefer explicit enums over magic strings here.")], since=None)
    assert len(kept) == 1


def test_respects_since_bound():
    old = _c("Prefer explicit enums over magic strings here.", when=datetime(2025, 1, 1, tzinfo=UTC))
    new = _c("Prefer explicit enums over magic strings here.", when=datetime(2026, 6, 1, tzinfo=UTC))
    kept = _filter_signal([old, new], since=datetime(2026, 1, 1, tzinfo=UTC))
    assert len(kept) == 1
    assert kept[0].created_at.year == 2026
