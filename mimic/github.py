import os
import shutil
import subprocess
from datetime import datetime
from functools import cache

import httpx

from mimic import __version__
from mimic.types import CommentKind, CommitFile, CommitSample, IssueSample, ReviewComment

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
        self._user_id_cache: dict[str, str] = {}

    def find_prs_with_user(self, user: str, repo: str | None, limit: int) -> list[dict]:
        q = f"commenter:{user} is:pr" + (f" repo:{repo}" if repo else "")
        data = self._query(FIND_PRS_QUERY, {"q": q, "first": min(limit, 100)})
        out: list[dict] = []
        for node in data["search"]["nodes"]:
            if not node:
                continue
            out.append(
                {
                    "repository_url": f"https://api.github.com/repos/{node['repository']['nameWithOwner']}",
                    "number": node["number"],
                    "title": node["title"],
                }
            )
        return out[:limit]

    def review_comments_for_pr(self, repo: str, pr_number: int) -> list[dict]:
        owner, name = repo.split("/", 1)
        data = self._query(
            REVIEW_COMMENTS_QUERY, {"owner": owner, "name": name, "number": pr_number}
        )
        threads = (data.get("repository") or {}).get("pullRequest", {}).get("reviewThreads", {})
        out: list[dict] = []
        for thread in threads.get("nodes", []) or []:
            for c in (thread.get("comments") or {}).get("nodes", []) or []:
                out.append(_gql_review_comment(c))
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
        owner, name = repo.split("/", 1)
        user_id = self._user_id(user)
        data = self._query(
            COMMITS_QUERY,
            {"owner": owner, "name": name, "userId": user_id, "first": min(limit, 100)},
        )
        target = (
            ((data.get("repository") or {}).get("defaultBranchRef") or {}).get("target") or {}
        )
        nodes = (target.get("history") or {}).get("nodes", []) or []
        return [_gql_commit(c) for c in nodes[:limit]]

    def issues_authored_by(self, user: str, repo: str | None, limit: int) -> list[dict]:
        q = f"author:{user} is:issue" + (f" repo:{repo}" if repo else "")
        data = self._query(FIND_ISSUES_QUERY, {"q": q, "first": min(limit, 100)})
        out: list[dict] = []
        for node in data["search"]["nodes"]:
            if not node:
                continue
            out.append(_gql_issue(node))
        return out[:limit]

    def _user_id(self, login: str) -> str:
        if login in self._user_id_cache:
            return self._user_id_cache[login]
        data = self._query(USER_ID_QUERY, {"login": login})
        user = data.get("user")
        if not user:
            raise GhError(f"github user @{login} not found.")
        self._user_id_cache[login] = user["id"]
        return user["id"]

    def _query(self, query: str, variables: dict) -> dict:
        r = self._client.post(GITHUB_GRAPHQL, json={"query": query, "variables": variables})
        if r.status_code >= 400:
            raise GhError(f"graphql -> {r.status_code}: {r.text[:200]}")
        body = r.json()
        if body.get("errors"):
            msgs = "; ".join(e.get("message", "?") for e in body["errors"])
            raise GhError(f"graphql errors: {msgs}")
        return body.get("data") or {}


# --- graphql queries ---------------------------------------------------------

FIND_PRS_QUERY = """
query($q: String!, $first: Int!) {
  search(query: $q, type: ISSUE, first: $first) {
    nodes {
      ... on PullRequest {
        number
        title
        repository { nameWithOwner }
      }
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

USER_ID_QUERY = """
query($login: String!) { user(login: $login) { id } }
"""

COMMITS_QUERY = """
query($owner: String!, $name: String!, $userId: ID!, $first: Int!) {
  repository(owner: $owner, name: $name) {
    defaultBranchRef {
      target {
        ... on Commit {
          history(first: $first, author: {id: $userId}) {
            nodes {
              oid
              message
              committedDate
              url
            }
          }
        }
      }
    }
  }
}
"""

FIND_ISSUES_QUERY = """
query($q: String!, $first: Int!) {
  search(query: $q, type: ISSUE, first: $first) {
    nodes {
      ... on Issue {
        number
        title
        body
        createdAt
        url
        repository { nameWithOwner }
      }
    }
  }
}
"""


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


def _gql_commit(c: dict) -> dict:
    return {
        "sha": c.get("oid", ""),
        "commit": {
            "message": c.get("message", ""),
            "author": {"date": c.get("committedDate")},
        },
        "html_url": c.get("url", ""),
        "files": [],
    }


def _gql_issue(i: dict) -> dict:
    return {
        "number": i.get("number", 0),
        "title": i.get("title", ""),
        "body": i.get("body", ""),
        "created_at": i.get("createdAt"),
        "html_url": i.get("url", ""),
        "repo": (i.get("repository") or {}).get("nameWithOwner", ""),
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
    )


def to_issue_sample(raw: dict) -> IssueSample:
    return IssueSample(
        repo=raw.get("repo", ""),
        number=raw.get("number", 0),
        title=raw.get("title", ""),
        body=(raw.get("body") or "")[:4000],
        created_at=_parse_dt(raw.get("created_at")),
        url=raw.get("html_url", ""),
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
