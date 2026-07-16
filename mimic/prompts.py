from mimic.types import CommitSample, IssueSample, ReviewComment

SYNTHESIS_SYSTEM = """You distill a GitHub user's coding style into a comprehensive, durable style guide.

The signals may span MULTIPLE sources (repos, local checkouts, issue trackers). Your job is to capture how this person writes code IN GENERAL — the patterns that hold across sources — plus a small "per-repo quirks" section only for rules that clearly differ between sources.

You are given up to three signal types per source:
1. Comments the user left on OTHER PEOPLE's PRs (what they flag when reviewing).
2. Commits the user authored: subject, body, and (when available) actual patch content.
3. Issues the user authored: how they describe bugs and feature requests.

Output structure:
1. Optional opening `## Overall` — 2-3 sentences describing their default posture (what they optimize for, what they push back on).
2. Themed H2 sections (`## Style`, `## Architecture`, `## Testing`, `## Naming`, `## Reviewing`, `## Commit messages`, `## Tone`, etc.) with imperative rules.
3. Optional trailing `## Per-repo quirks` — ONLY if rules genuinely differ across sources.

Rules for the rules:
- Focus on conventions the user applies REPEATEDLY. Prefer patterns supported by MULTIPLE signals or MULTIPLE sources.
- Write imperatively: "Prefer X over Y", "Use enums for closed sets", "Test the exception branch".
- Cite 2-3 concrete examples per rule when the signal supports it — a real quote from a comment, a filename pattern, a commit subject. Include the source: `(pacific-server#4379)` or `(simonw/llm@abc123)`.
- Include short context after the rule when it aids understanding — a code snippet, an anti-pattern they explicitly called out, a "why".
- Length is not the enemy. If the person has 12 durable rules across 4 themes, write all 12. Don't compress to 5 for brevity. But omit sections where you don't have at least 2 supporting signals.
- No fluff. No preamble. No summary. No "In conclusion". Start directly with the first section.
"""


def synthesis_user_prompt(
    user: str,
    comments: list[ReviewComment],
    commits: list[CommitSample] = (),
    issues: list[IssueSample] = (),
) -> str:
    lines = [
        f"Distill @{user}'s coding style from the following signals.",
        "",
    ]

    if comments:
        lines.append(f"## Signal 1: {len(comments)} comments @{user} left on others' PRs")
        lines.append("")
        lines.append("Each comment is prefixed with [repo#pr] and optionally (file:line).")
        lines.append("")
        for c in comments:
            loc = ""
            if c.path:
                loc = f" ({c.path}"
                if c.line:
                    loc += f":{c.line}"
                loc += ")"
            lines.append(f"[{c.repo}#{c.pr_number}]{loc}")
            lines.append(c.body.strip())
            lines.append("")

    if commits:
        lines.append(f"## Signal 2: {len(commits)} commits @{user} authored")
        lines.append("")
        lines.append("Each commit shows [repo@sha], the message, files touched, and (for the most recent) a truncated diff.")
        lines.append("")
        for c in commits:
            lines.append(f"[{c.repo}@{c.sha}]")
            lines.append(c.subject)
            if c.body:
                lines.append(c.body)
            if c.files:
                lines.append("files: " + ", ".join(f"{f.status[0].upper()} {f.path}" for f in c.files[:20]))
                for f in c.files[:5]:
                    if f.patch:
                        lines.append(f"```diff\n# {f.path}\n{f.patch}\n```")
            lines.append("")

    if issues:
        lines.append(f"## Signal 3: {len(issues)} issues @{user} authored")
        lines.append("")
        lines.append("Each issue is prefixed with [repo#number] and shows the title + body.")
        lines.append("")
        for i in issues:
            lines.append(f"[{i.repo}#{i.number}] {i.title}")
            if i.body:
                lines.append(i.body.strip())
            lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("Output the persona as markdown. Nothing before or after.")
    return "\n".join(lines)


REVIEW_SYSTEM = """You are a pre-review checker.

Given a coding-style persona and a unified diff, list the things the persona would call out as style mismatches.

Rules:
- Only include concerns backed by a specific rule in the persona. No generic advice.
- One concern per bullet. Reference file:line when possible.
- Format each bullet as:  - <concern>  [FILE:LINE]
  Optional second line indented with two spaces starting "→ " for a concrete suggestion.
- If the diff already matches this persona, output exactly: NO_NITS
- No preamble. No summary.
"""


def review_user_prompt(user: str, persona: str, diff: str) -> str:
    return (
        f"# Style persona: @{user}\n\n"
        f"{persona.strip()}\n\n"
        f"---\n\n"
        f"# Diff to check\n\n"
        f"```diff\n{diff.strip()}\n```\n"
    )


STRUCTURAL_SYSTEM = """You are a pre-review checker looking for STRUCTURAL nits only.

Given a coding-style persona and a list of files changed (paths + status, no contents), flag anything the persona would complain about at the repo-layout level:
- file naming or directory placement conventions
- missing companion files (new source without a test, new module without an __init__, new endpoint without types)
- types placed inline instead of in a types module
- service classes vs bare functions in the wrong place

Rules:
- Only concerns backed by a specific rule in the persona.
- Format each bullet as:  - <concern>  [FILE]
- If nothing structural, output exactly: NO_NITS
- No preamble. No summary.
"""


def structural_user_prompt(user: str, persona: str, files: list[tuple[str, str]]) -> str:
    lines = [
        f"# Style persona: @{user}",
        "",
        persona.strip(),
        "",
        "---",
        "",
        "# Files changed",
        "",
    ]
    for status, path in files:
        lines.append(f"{status}  {path}")
    return "\n".join(lines)
