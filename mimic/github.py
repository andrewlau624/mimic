import json
import shutil
import subprocess
from datetime import datetime

from mimic.types import CommentKind, CommitSample, ReviewComment


class GhNotInstalled(RuntimeError):
    pass


class GhError(RuntimeError):
    pass


class GitHubClient:
    """Thin wrapper around the `gh` CLI so we inherit its auth (no token juggling)."""

    def __init__(self, gh_bin: str = "gh"):
        if shutil.which(gh_bin) is None:
            raise GhNotInstalled(
                "the `gh` CLI is required. install: https://cli.github.com/ then `gh auth login`."
            )
        self._gh = gh_bin

    def find_prs_with_user(self, user: str, repo: str | None, limit: int) -> list[dict]:
        """PRs where `user` participated (commented or reviewed). Newest first."""
        q_parts = [f"commenter:{user}", "is:pr"]
        if repo:
            q_parts.append(f"repo:{repo}")
        query = " ".join(q_parts)
        args = [
            "api",
            "-X", "GET",
            "/search/issues",
            "-f", f"q={query}",
            "-f", "sort=updated",
            "-f", "order=desc",
            "-F", f"per_page={min(limit, 100)}",
        ]
        data = self._json(args)
        items = data.get("items", [])[:limit]
        return items

    def review_comments_for_pr(self, repo: str, pr_number: int) -> list[dict]:
        return self._json_paged(f"/repos/{repo}/pulls/{pr_number}/comments")

    def issue_comments_for_pr(self, repo: str, pr_number: int) -> list[dict]:
        return self._json_paged(f"/repos/{repo}/issues/{pr_number}/comments")

    def reviews_for_pr(self, repo: str, pr_number: int) -> list[dict]:
        return self._json_paged(f"/repos/{repo}/pulls/{pr_number}/reviews")

    def commits_by_user(self, repo: str, user: str, limit: int) -> list[dict]:
        per_page = min(limit, 100)
        path = f"/repos/{repo}/commits?author={user}&per_page={per_page}"
        return self._json_paged(path)[:limit]

    def _json(self, args: list[str]) -> dict:
        cmd = [self._gh, *args]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise GhError(f"gh failed ({' '.join(args[:3])}): {result.stderr.strip()}")
        return json.loads(result.stdout or "{}")

    def _json_paged(self, path: str) -> list[dict]:
        args = ["api", "--paginate", path]
        cmd = [self._gh, *args]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise GhError(f"gh failed ({path}): {result.stderr.strip()}")
        out = result.stdout.strip()
        if not out:
            return []
        chunks = [json.loads(line) for line in out.splitlines() if line.strip()]
        flat: list[dict] = []
        for chunk in chunks:
            if isinstance(chunk, list):
                flat.extend(chunk)
            else:
                flat.append(chunk)
        return flat


def to_review_comment(
    kind: CommentKind,
    raw: dict,
    repo: str,
    pr_number: int,
    pr_title: str,
) -> ReviewComment:
    user = (raw.get("user") or {}).get("login", "unknown")
    return ReviewComment(
        kind=kind,
        repo=repo,
        pr_number=pr_number,
        pr_title=pr_title,
        author=user,
        body=raw.get("body") or raw.get("state") or "",
        path=raw.get("path"),
        line=raw.get("line") or raw.get("original_line"),
        diff_hunk=raw.get("diff_hunk"),
        created_at=datetime.fromisoformat(raw["created_at"].replace("Z", "+00:00"))
        if raw.get("created_at")
        else datetime.now().astimezone(),
        url=raw.get("html_url", ""),
    )


def to_commit_sample(raw: dict, repo: str) -> CommitSample:
    message = (raw.get("commit") or {}).get("message", "")
    subject, _, body = message.partition("\n\n")
    date_str = ((raw.get("commit") or {}).get("author") or {}).get("date")
    created_at = (
        datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        if date_str
        else datetime.now().astimezone()
    )
    return CommitSample(
        repo=repo,
        sha=raw.get("sha", "")[:12],
        subject=subject.strip(),
        body=body.strip(),
        created_at=created_at,
        url=raw.get("html_url", ""),
    )
