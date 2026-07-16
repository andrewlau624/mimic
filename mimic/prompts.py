from mimic.types import ReviewComment

SYNTHESIS_SYSTEM = """You distill a reviewer's PR comments into a durable style guide.

Rules:
- Focus on rules the reviewer applies REPEATEDLY across different PRs, not one-off notes.
- Prefer accepted corrections (things the author usually acts on) over debatable opinions.
- Write rules imperatively: "Prefer X over Y", "Use enums for closed sets", "Test the exception branch".
- Group under short H2 headers (e.g. ## Style, ## Testing, ## Naming, ## Architecture).
- No fluff. No preamble. No summary. No "In conclusion". Just the rules.
- If you cannot find a rule with at least 2 supporting comments, omit that section.
"""


def synthesis_user_prompt(user: str, comments: list[ReviewComment]) -> str:
    lines = [
        f"Distill @{user}'s reviewer style from the following {len(comments)} comments.",
        "",
        "Each comment is prefixed with [repo#pr] and optionally (file:line).",
        "Some are inline review comments; others are top-level PR discussion.",
        "",
        "---",
    ]
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
    lines.append("---")
    lines.append("")
    lines.append("Output the persona as markdown. Nothing before or after.")
    return "\n".join(lines)


REVIEW_SYSTEM = """You are a pre-review checker.

Given a reviewer's persona and a unified diff, list the things the reviewer would most likely flag.

Rules:
- Only include concerns backed by a specific rule in the persona. No generic advice.
- One concern per bullet. Reference file:line when possible.
- Format each bullet as:  - <concern>  [FILE:LINE]
  Optional second line indented with two spaces starting "→ " for a concrete suggestion.
- If the diff is clean against this persona, output exactly: NO_NITS
- No preamble. No summary.
"""


def review_user_prompt(user: str, persona: str, diff: str) -> str:
    return (
        f"# Reviewer persona: @{user}\n\n"
        f"{persona.strip()}\n\n"
        f"---\n\n"
        f"# Diff to check\n\n"
        f"```diff\n{diff.strip()}\n```\n"
    )


STRUCTURAL_SYSTEM = """You are a pre-review checker looking for STRUCTURAL nits only.

Given a reviewer's persona and a list of files changed (paths + status, no contents), flag anything the reviewer would complain about at the repo-layout level:
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
        f"# Reviewer persona: @{user}",
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
