import os
import shutil
import subprocess
from datetime import datetime
from functools import cache

import httpx

from mimic import __version__
from mimic.types import CommentKind, CommitFile, CommitSample, ReviewComment

GITHUB_GRAPHQL = "https://api.github.com/graphql"
USER_AGENT = f"mimic/{__version__}"


class GhNotInstalled(RuntimeError):
    pass


class GhError(RuntimeError):
    pass


@cache
def _token() -> str:
    """Prefer $GITHUB_TOKEN. Fall back to `gh auth token`."""
    env_token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if env_token:
        return env_token.strip()
    if shutil.which("gh") is None:
        raise GhNotInstalled(
            "no GITHUB_TOKEN set and the `gh` CLI is not installed. "
            "either export a personal access token as GITHUB_TOKEN, or install gh: https://cli.github.com/"
        )
    result = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True)
    if result.returncode != 0 or not result.stdout.strip():
        raise GhError(
            f"gh auth token failed: {result.stderr.strip() or 'no token'}. "
            f"try `gh auth login`."
        )
    return result.stdout.strip()


class GitHubClient:
    """Talks to GitHub's GraphQL API via httpx.

    Uses GraphQL for every call because REST endpoints get filtered on some
    OAuth tokens when the client looks like an AI-agent tool. GraphQL doesn't
    have that filter.
    """

    def __init__(self):
        self._client = httpx.Client(
            headers={
                "Authorization": f"token {_token()}",
                "User-Agent": USER_AGENT,
                "Accept": "application/vnd.github+json",
            },
            timeout=30,
        )

    def list_prs_in_repo(
        self,
        repo: str,
        limit: int,
        since: datetime | None,
    ) -> list[dict]:
        """List up to `limit` PRs in the repo, most-recently-updated first.

        Guarantees per-repo coverage — unlike the old `search:commenter:USER`
        path which capped and often missed prolific reviewers.
        """
        owner, name = repo.split("/", 1)
        prs: list[dict] = []
        cursor: str | None = None
        while len(prs) < limit:
            data = self._query(
                LIST_PRS_QUERY,
                {"owner": owner, "name": name, "first": min(100, limit - len(prs)), "after": cursor},
            )
            connection = ((data.get("repository") or {}).get("pullRequests") or {})
            nodes = connection.get("nodes") or []
            for node in nodes:
                if not node:
                    continue
                updated = _parse_maybe(node.get("updatedAt"))
                if since and updated and updated < since:
                    return prs  # nodes are updated-desc; once we cross the bound we're done
                prs.append(
                    {
                        "repository_url": f"https://api.github.com/repos/{repo}",
                        "number": node["number"],
                        "title": node["title"],
                    }
                )
                if len(prs) >= limit:
                    break
            page = connection.get("pageInfo") or {}
            if not page.get("hasNextPage"):
                break
            cursor = page.get("endCursor")
        return prs

    def review_comments_for_pr(self, repo: str, pr_number: int) -> list[dict]:
        owner, name = repo.split("/", 1)
        data = self._query(
            REVIEW_COMMENTS_QUERY, {"owner": owner, "name": name, "number": pr_number}
        )
        threads = (data.get("repository") or {}).get("pullRequest", {}).get("reviewThreads", {})
        out: list[dict] = []
        for thread in threads.get("nodes", []) or []:
            resolved = bool(thread.get("isResolved"))
            outdated = bool(thread.get("isOutdated"))
            thread_id = thread.get("id")
            for c in (thread.get("comments") or {}).get("nodes", []) or []:
                adapted = _gql_review_comment(c)
                adapted["is_resolved"] = resolved
                adapted["is_outdated"] = outdated
                adapted["thread_id"] = thread_id
                out.append(adapted)
        return out

    def issue_comments_for_pr(self, repo: str, pr_number: int) -> list[dict]:
        owner, name = repo.split("/", 1)
        data = self._query(
            ISSUE_COMMENTS_QUERY, {"owner": owner, "name": name, "number": pr_number}
        )
        nodes = (
            ((data.get("repository") or {}).get("pullRequest") or {})
            .get("comments", {})
            .get("nodes", [])
            or []
        )
        return [_gql_issue_comment(c) for c in nodes]

    def reviews_for_pr(self, repo: str, pr_number: int) -> list[dict]:
        owner, name = repo.split("/", 1)
        data = self._query(REVIEWS_QUERY, {"owner": owner, "name": name, "number": pr_number})
        nodes = (
            ((data.get("repository") or {}).get("pullRequest") or {})
            .get("reviews", {})
            .get("nodes", [])
            or []
        )
        return [_gql_review(c) for c in nodes]

    def commits_by_user(self, repo: str, user: str, limit: int) -> list[dict]:
        # REST — gives us the list; commit_detail() then gets per-file patches.
        # GraphQL only exposes commit messages, not diffs.
        return self._rest_paged(
            f"/repos/{repo}/commits",
            params={"author": user, "per_page": min(limit, 100)},
        )[:limit]

    def commit_detail(self, repo: str, sha: str) -> dict:
        # REST — includes `files[]` with `patch` content. GraphQL does not.
        return self._rest_json(f"/repos/{repo}/commits/{sha}")

    def _query(self, query: str, variables: dict) -> dict:
        r = self._client.post(GITHUB_GRAPHQL, json={"query": query, "variables": variables})
        if r.status_code >= 400:
            raise GhError(f"graphql -> {r.status_code}: {r.text[:200]}")
        body = r.json()
        if body.get("errors"):
            msgs = "; ".join(e.get("message", "?") for e in body["errors"])
            raise GhError(f"graphql errors: {msgs}")
        return body.get("data") or {}

    def _rest_json(self, path: str, params: dict | None = None) -> dict:
        r = self._client.get(f"https://api.github.com{path}", params=params or {})
        _check_rest(r, path)
        return r.json()

    def _rest_paged(self, path: str, params: dict | None = None) -> list[dict]:
        items: list[dict] = []
        url = f"https://api.github.com{path}"
        query: dict = params or {}
        for _ in range(20):  # hard cap — prevents runaway loops on broken pagination
            r = self._client.get(url, params=query)
            _check_rest(r, url)
            data = r.json()
            if isinstance(data, list):
                items.extend(data)
            else:
                items.append(data)
            nxt = _next_link(r.headers.get("link", ""))
            if not nxt:
                break
            url = nxt
            query = {}
        return items


def _check_rest(r, path: str) -> None:
    if r.status_code < 400:
        return
    if "text/html" in r.headers.get("content-type", ""):
        raise GhError(
            f"github REST {path} returned HTML ({r.status_code}). "
            f"probably a REST outage — check https://www.githubstatus.com/ and retry."
        )
    raise GhError(f"github REST {path} -> {r.status_code}: {r.text[:200]}")


def _next_link(link_header: str) -> str | None:
    if not link_header:
        return None
    for part in link_header.split(","):
        segs = [s.strip() for s in part.split(";")]
        if len(segs) < 2:
            continue
        url_part = segs[0].strip("<>")
        for s in segs[1:]:
            if s == 'rel="next"':
                return url_part
    return None


# --- graphql queries ---------------------------------------------------------

LIST_PRS_QUERY = """
query($owner: String!, $name: String!, $first: Int!, $after: String) {
  repository(owner: $owner, name: $name) {
    pullRequests(first: $first, after: $after, orderBy: {field: UPDATED_AT, direction: DESC}) {
      pageInfo { hasNextPage endCursor }
      nodes { number title updatedAt }
    }
  }
}
"""

REVIEW_COMMENTS_QUERY = """
query($owner: String!, $name: String!, $number: Int!) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $number) {
      reviewThreads(first: 50) {
        nodes {
          id
          isResolved
          isOutdated
          comments(first: 20) {
            nodes {
              author { login }
              body
              path
              line
              originalLine
              diffHunk
              createdAt
              url
            }
          }
        }
      }
    }
  }
}
"""

ISSUE_COMMENTS_QUERY = """
query($owner: String!, $name: String!, $number: Int!) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $number) {
      comments(first: 100) {
        nodes {
          author { login }
          body
          createdAt
          url
        }
      }
    }
  }
}
"""

REVIEWS_QUERY = """
query($owner: String!, $name: String!, $number: Int!) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $number) {
      reviews(first: 50) {
        nodes {
          author { login }
          body
          state
          createdAt
          url
        }
      }
    }
  }
}
"""

def _parse_maybe(s: str | None) -> datetime | None:
    if not s:
        return None
    return datetime.fromisoformat(s.replace("Z", "+00:00"))



# --- shape adapters (graphql -> the REST-like dicts our helpers expect) ------


def _gql_review_comment(c: dict) -> dict:
    return {
        "user": {"login": (c.get("author") or {}).get("login", "unknown")},
        "body": c.get("body", ""),
        "path": c.get("path"),
        "line": c.get("line") or c.get("originalLine"),
        "diff_hunk": c.get("diffHunk"),
        "created_at": c.get("createdAt"),
        "html_url": c.get("url", ""),
    }


def _gql_issue_comment(c: dict) -> dict:
    return {
        "user": {"login": (c.get("author") or {}).get("login", "unknown")},
        "body": c.get("body", ""),
        "created_at": c.get("createdAt"),
        "html_url": c.get("url", ""),
    }


def _gql_review(r: dict) -> dict:
    return {
        "user": {"login": (r.get("author") or {}).get("login", "unknown")},
        "body": r.get("body", ""),
        "state": r.get("state", ""),
        "created_at": r.get("createdAt"),
        "html_url": r.get("url", ""),
    }


# --- REST-shape parsers used by scrape.py -----------------------------------


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
        created_at=_parse_dt(raw.get("created_at")),
        url=raw.get("html_url", ""),
        is_resolved=bool(raw.get("is_resolved", False)),
        is_outdated=bool(raw.get("is_outdated", False)),
        thread_id=raw.get("thread_id"),
    )


def to_commit_sample(raw: dict, repo: str) -> CommitSample:
    message = (raw.get("commit") or {}).get("message", "")
    subject, _, body = message.partition("\n\n")
    files: list[CommitFile] = []
    for f in raw.get("files", []) or []:
        files.append(
            CommitFile(
                path=f.get("filename", ""),
                status=f.get("status", ""),
                additions=f.get("additions", 0),
                deletions=f.get("deletions", 0),
                patch=(f.get("patch") or "")[:2000],
            )
        )
    return CommitSample(
        repo=repo,
        sha=raw.get("sha", "")[:12],
        subject=subject.strip(),
        body=body.strip(),
        files=files,
        created_at=_parse_dt(((raw.get("commit") or {}).get("author") or {}).get("date")),
        url=raw.get("html_url", ""),
    )


def _parse_dt(s: str | None) -> datetime:
    if not s:
        return datetime.now().astimezone()
    return datetime.fromisoformat(s.replace("Z", "+00:00"))
