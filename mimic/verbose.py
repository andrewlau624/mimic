"""Deterministic dump of every scraped signal, grouped by repo + PR.

Reference material — no LLM call, no dedup, no synthesis. If you want to
see the raw source behind persona.md, this is it.
"""
from collections import defaultdict
from datetime import datetime

from mimic.types import CommitSample, ReviewComment


def render(user: str, comments: list[ReviewComment], commits: list[CommitSample]) -> str:
    repos = sorted({c.repo for c in comments} | {c.repo for c in commits})
    lines = [
        f"# @{user} — all scraped signals",
        "",
        f"_generated {datetime.now().astimezone().strftime('%Y-%m-%d')} from "
        f"{len(comments)} review comments + {len(commits)} commits across {len(repos)} repos_",
        "",
    ]

    by_repo: dict[str, list[ReviewComment]] = defaultdict(list)
    for c in comments:
        by_repo[c.repo].append(c)

    for repo in sorted(by_repo):
        rc = by_repo[repo]
        lines.append(f"## {repo} — {len(rc)} comments")
        lines.append("")
        by_pr: dict[int, list[ReviewComment]] = defaultdict(list)
        for c in rc:
            by_pr[c.pr_number].append(c)
        for pr in sorted(by_pr):
            lines.append(f"### #{pr}")
            for c in by_pr[pr]:
                loc = ""
                if c.path:
                    loc = f"({c.path}"
                    if c.line:
                        loc += f":{c.line}"
                    loc += ") "
                body = " ".join(c.body.strip().split())
                lines.append(f"- {loc}{body}")
            lines.append("")

    by_repo_commits: dict[str, list[CommitSample]] = defaultdict(list)
    for c in commits:
        by_repo_commits[c.repo].append(c)

    for repo in sorted(by_repo_commits):
        cs = by_repo_commits[repo]
        lines.append(f"## commits — {repo} ({len(cs)})")
        lines.append("")
        for c in cs:
            lines.append(f"- `{c.sha}` [{c.created_at.strftime('%Y-%m-%d')}] {c.subject}")
            if c.body:
                first = c.body.split("\n\n", 1)[0][:300]
                lines.append(f"  {first}")
        lines.append("")

    return "\n".join(lines)
