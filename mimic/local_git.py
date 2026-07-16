"""Read a user's commits + patches from a local git checkout.

Avoids GraphQL's inability to expose per-file patches, and skips API rate limits
entirely. Useful when the target user commits to a repo you have checked out.
"""
import re
import subprocess
from datetime import datetime
from pathlib import Path

from mimic.types import CommitFile, CommitSample

MAX_PATCH_CHARS = 2000
MAX_PATCH_LINES = 400
_DIFF_RE = re.compile(r"^diff --git a/(\S+) b/(\S+)$")


class LocalGitError(RuntimeError):
    pass


class LocalGit:
    def __init__(self, repo_path: str, repo_name: str = ""):
        self._path = Path(repo_path).expanduser().resolve()
        if not (self._path / ".git").exists() and not (self._path / "HEAD").exists():
            raise LocalGitError(f"{self._path} is not a git repository.")
        self._repo_name = repo_name or self._path.name

    def commits_by(
        self,
        user: str,
        limit: int,
        since: datetime | None,
    ) -> list[CommitSample]:
        args = [
            "git", "-C", str(self._path), "log",
            f"--author={user}",
            f"-n{limit}",
            "--pretty=format:%H%x1f%aI%x1f%s%x1f%b%x1e",
        ]
        if since:
            args.extend(["--since", since.strftime("%Y-%m-%d")])
        result = subprocess.run(args, capture_output=True, text=True)
        if result.returncode != 0:
            raise LocalGitError(f"git log failed: {result.stderr.strip()}")

        out: list[CommitSample] = []
        for entry in result.stdout.split("\x1e"):
            entry = entry.strip("\n")
            if not entry:
                continue
            parts = entry.split("\x1f")
            if len(parts) < 4:
                continue
            sha, date_str, subject, body = parts[0], parts[1], parts[2], "\x1f".join(parts[3:])
            out.append(
                CommitSample(
                    repo=self._repo_name,
                    sha=sha[:12],
                    subject=subject.strip(),
                    body=body.strip(),
                    created_at=datetime.fromisoformat(date_str),
                    url="",
                )
            )
        return out

    def files_for(self, sha: str) -> list[CommitFile]:
        args = [
            "git", "-C", str(self._path), "show", sha,
            "--format=",
            "--unified=3",
        ]
        result = subprocess.run(args, capture_output=True, text=True)
        if result.returncode != 0:
            return []

        files: list[CommitFile] = []
        current: dict | None = None
        for i, line in enumerate(result.stdout.splitlines()):
            if i > MAX_PATCH_LINES * 20:
                break
            m = _DIFF_RE.match(line)
            if m:
                if current:
                    files.append(_finalize(current))
                current = {"path": m.group(2), "patch": line + "\n", "additions": 0, "deletions": 0}
                continue
            if current is None:
                continue
            current["patch"] += line + "\n"
            if line.startswith("+") and not line.startswith("+++"):
                current["additions"] += 1
            elif line.startswith("-") and not line.startswith("---"):
                current["deletions"] += 1
        if current:
            files.append(_finalize(current))
        return files


def _finalize(d: dict) -> CommitFile:
    return CommitFile(
        path=d["path"],
        status="modified",
        additions=d["additions"],
        deletions=d["deletions"],
        patch=d["patch"][:MAX_PATCH_CHARS],
    )
