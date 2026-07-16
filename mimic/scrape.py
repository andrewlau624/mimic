import re
from datetime import datetime

from mimic.github import GitHubClient, to_commit_sample, to_issue_sample, to_review_comment
from mimic.local_git import LocalGit
from mimic.types import CommentKind, CommitSample, IssueSample, ReviewComment

NOISE_PATTERNS = [
    re.compile(r"^\s*(lgtm|ship\s?it|👍|:\+1:|:shipit:)\s*[.!]?\s*$", re.IGNORECASE),
    re.compile(r"^\s*(thanks|thank you|nice|great|cool)\b.{0,30}$", re.IGNORECASE),
    re.compile(r"^\s*/?(rebase|merge|approve|assign)\b", re.IGNORECASE),
]

MIN_BODY_LEN = 20
DEFAULT_COMMIT_LIMIT = 30
DEFAULT_LOCAL_ENRICH = 10


class ScrapeService:
    def __init__(self, gh: GitHubClient):
        self._gh = gh

    def collect_comments(
        self,
        user: str,
        repo: str | None,
        limit: int,
        since: datetime | None,
    ) -> list[ReviewComment]:
        prs = self._gh.find_prs_with_user(user, repo, limit)
        comments: list[ReviewComment] = []

        for pr in prs:
            pr_repo = _repo_from_url(pr.get("repository_url", ""))
            pr_number = pr.get("number")
            pr_title = pr.get("title", "")
            if not pr_repo or not pr_number:
                continue

            for raw in self._gh.review_comments_for_pr(pr_repo, pr_number):
                if _by(raw, user):
                    comments.append(
                        to_review_comment(CommentKind.REVIEW_COMMENT, raw, pr_repo, pr_number, pr_title)
                    )

            for raw in self._gh.reviews_for_pr(pr_repo, pr_number):
                if _by(raw, user) and (raw.get("body") or "").strip():
                    comments.append(
                        to_review_comment(CommentKind.REVIEW_BODY, raw, pr_repo, pr_number, pr_title)
                    )

            for raw in self._gh.issue_comments_for_pr(pr_repo, pr_number):
                if _by(raw, user):
                    comments.append(
                        to_review_comment(CommentKind.ISSUE_COMMENT, raw, pr_repo, pr_number, pr_title)
                    )

        return _filter_signal(comments, since)

    def collect_commits(
        self,
        user: str,
        repo: str | None,
        limit: int,
        since: datetime | None,
        local_path: str | None = None,
    ) -> list[CommitSample]:
        if local_path:
            local = LocalGit(local_path, repo_name=repo or "")
            out = local.commits_by(user, limit, since)
            for sample in out[:DEFAULT_LOCAL_ENRICH]:
                sample.files = local.files_for(sample.sha)
            return out

        if not repo:
            return []
        raws = self._gh.commits_by_user(repo, user, limit)
        out = [to_commit_sample(r, repo) for r in raws]
        if since:
            out = [c for c in out if c.created_at >= since]
        out.sort(key=lambda c: c.created_at, reverse=True)
        return out

    def collect_issues(
        self,
        user: str,
        repo: str | None,
        limit: int,
        since: datetime | None,
    ) -> list[IssueSample]:
        raws = self._gh.issues_authored_by(user, repo, limit)
        out = [to_issue_sample(r) for r in raws]
        if since:
            out = [i for i in out if i.created_at >= since]
        out.sort(key=lambda i: i.created_at, reverse=True)
        return out


def _by(raw: dict, user: str) -> bool:
    login = ((raw.get("user") or {}).get("login") or "").lower()
    return login == user.lower()


def _repo_from_url(url: str) -> str:
    prefix = "https://api.github.com/repos/"
    return url[len(prefix):] if url.startswith(prefix) else ""


def _filter_signal(comments: list[ReviewComment], since: datetime | None) -> list[ReviewComment]:
    out: list[ReviewComment] = []
    for c in comments:
        if since and c.created_at < since:
            continue
        body = c.body.strip()
        if len(body) < MIN_BODY_LEN:
            continue
        if any(p.search(body) for p in NOISE_PATTERNS):
            continue
        out.append(c)
    out.sort(key=lambda c: c.created_at, reverse=True)
    return out
