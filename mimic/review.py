import re
import subprocess

from mimic.prompts import REVIEW_SYSTEM, review_user_prompt
from mimic.providers import Provider
from mimic.types import Checklist, ChecklistItem

LINE_RE = re.compile(r"^\s*-\s+(.*?)(?:\s+\[([^\]]+)\])?\s*$")
SUGGESTION_RE = re.compile(r"^\s{2,}→\s*(.+)$")


class ReviewService:
    def __init__(self, provider: Provider):
        self._provider = provider

    def check(self, user: str, persona: str, diff: str) -> Checklist:
        if not diff.strip():
            return Checklist(user=user, items=[])
        raw = self._provider.complete(REVIEW_SYSTEM, review_user_prompt(user, persona, diff))
        return _parse(user, raw)


def diff_against(base: str) -> str:
    result = subprocess.run(
        ["git", "diff", f"{base}...HEAD"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git diff failed: {result.stderr.strip()}")
    return result.stdout


def _parse(user: str, raw: str) -> Checklist:
    text = raw.strip()
    if text == "NO_NITS" or not text:
        return Checklist(user=user, items=[])
    items: list[ChecklistItem] = []
    pending: ChecklistItem | None = None
    for line in text.splitlines():
        m = LINE_RE.match(line)
        if m:
            if pending:
                items.append(pending)
            concern = m.group(1).strip()
            loc = m.group(2)
            file, line_no = _split_loc(loc) if loc else (None, None)
            pending = ChecklistItem(file=file, line=line_no, concern=concern)
            continue
        s = SUGGESTION_RE.match(line)
        if s and pending is not None:
            pending.suggestion = s.group(1).strip()
    if pending:
        items.append(pending)
    return Checklist(user=user, items=items)


def _split_loc(loc: str) -> tuple[str | None, int | None]:
    if ":" in loc:
        file, line = loc.rsplit(":", 1)
        try:
            return file.strip(), int(line)
        except ValueError:
            return loc.strip(), None
    return loc.strip(), None
