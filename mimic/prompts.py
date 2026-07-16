from mimic.types import CommitSample, ReviewComment

SYNTHESIS_SYSTEM = """You distill a GitHub user's coding style into a durable style guide.

You are given two signals:
1. Comments the user left on OTHER PEOPLE's PRs (what they flag when reviewing).
2. Commit subjects/bodies from the user's OWN commits (how they describe their own work).

Rules:
- Focus on conventions the user applies REPEATEDLY across different PRs or commits.
- Prefer patterns supported by BOTH signals when possible (they flag it in reviews AND they follow it themselves).
- Write rules imperatively: "Prefer X over Y", "Use enums for closed sets", "Test the exception branch".
- Group under short H2 headers (e.g. ## Style, ## Testing, ## Naming, ## Architecture, ## Commit messages).
- No fluff. No preamble. No summary. No "In conclusion". Just the rules.
- If you cannot find a rule with at least 2 supporting signals, omit that section.
"""


def synthesis_user_prompt(
    user: str,
    comments: list[ReviewComment],
    commits: list[CommitSample] = (),
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
