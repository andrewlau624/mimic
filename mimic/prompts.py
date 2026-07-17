from datetime import UTC, datetime

from mimic.types import CommitSample, ReviewComment

SYNTHESIS_SYSTEM = """You distill a code REVIEWER's style into a durable, cite-heavy style guide.

The signals span PR review comments (the primary signal — what they flag when reviewing others' code) and, when available, commits they authored (secondary — how they write their own code). Signals may span MULTIPLE source repos; when they do, prefer patterns that repeat across repos.

Output structure:
1. Optional opening `## Overall` — 2-3 sentences describing their default review posture (what they push back on, what they optimize for).
2. Themed H2 sections describing WHAT they flag (`## Architecture`, `## Naming`, `## Testing`, `## Style`, `## Types`, `## Commit messages`). Do NOT include a `## Tone` section — how they phrase reviews is out of scope; only what they flag matters.
3. Optional trailing `## Per-repo quirks` — ONLY if rules genuinely differ across sources.

Weight signal strength (each comment is tagged in brackets):
- `[resolved]` — the review thread was resolved. The author accepted the nit and shipped it. STRONGER signal than unresolved.
- `[recent]` — comment is less than 90 days old. Reflects current priorities. Weight higher.
- `[older]` — comment is more than 2 years old. May reflect outdated positions. Include only if reinforced by recent signals.

Grouping and deduplication:
- Many comments say the same thing in different words. GROUP similar comments into one rule.
- One rule can be backed by 10+ similar comments. Cite 2-3 representative quotes, not all 10.
- REQUIRE at least 2 supporting comments from DIFFERENT PRs. Two comments on the same PR count as ONE signal — a rant on a single PR is not a durable pattern.
- Prefer citing quotes that come from DIFFERENT PRs (shows the pattern isn't tied to one PR's context).
- If a rule holds across multiple repos, cite one example from each repo when possible.

Rules for the rules:
- Focus on conventions the reviewer applies REPEATEDLY. Prefer patterns supported by MULTIPLE comments across MULTIPLE PRs, weighted by `[resolved]` and `[recent]` tags.
- Write imperatively: "Prefer X over Y", "Use enums for closed sets", "Test the exception branch".
- Cite 2-3 concrete examples per rule — a real quote from a comment, a filename, a commit subject. Include the source: `(pacific-server#4379)` or `(acme/api@abc123)`.
- Include short context after the rule when it aids understanding — a code snippet, an anti-pattern they explicitly called out, a "why".
- Length is not the enemy. If the reviewer has 12 durable rules across 4 themes, write all 12. Don't compress.
- No fluff. No preamble. No summary. Start directly with the first section.
"""


def _tags(c: ReviewComment) -> str:
    tags = []
    if c.is_resolved:
        tags.append("resolved")
    now = datetime.now(tz=UTC)
    days = (now - c.created_at).days
    if days < 90:
        tags.append("recent")
    elif days > 730:
        tags.append("older")
    return f" [{', '.join(tags)}]" if tags else ""


def synthesis_user_prompt(
    user: str,
    comments: list[ReviewComment],
    commits: list[CommitSample] = (),
) -> str:
    lines = [
        f"Distill @{user}'s review style from the following signals.",
        "",
    ]

    if comments:
        lines.append(f"## Signal 1: {len(comments)} review comments @{user} left on others' PRs")
        lines.append("")
        lines.append("Each comment is prefixed with [repo#pr] and optionally (file:line). Metadata tags in brackets indicate signal strength: [resolved] = author accepted; [recent] = <90d; [older] = >2y.")
        lines.append("")
        for c in comments:
            loc = ""
            if c.path:
                loc = f" ({c.path}"
                if c.line:
                    loc += f":{c.line}"
                loc += ")"
            lines.append(f"[{c.repo}#{c.pr_number}]{loc}{_tags(c)}")
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
