import re
import subprocess

from mimic.prompts import (
    REVIEW_SYSTEM,
    STRUCTURAL_SYSTEM,
    review_user_prompt,
    structural_user_prompt,
)
from mimic.providers import Provider
from mimic.types import Checklist, ChecklistItem, ChunkMode

LINE_RE = re.compile(r"^\s*-\s+(.*?)(?:\s+\[([^\]]+)\])?\s*$")
SUGGESTION_RE = re.compile(r"^\s{2,}→\s*(.+)$")
DIFF_SPLIT_RE = re.compile(r"^diff --git ", re.MULTILINE)
FILE_PATH_RE = re.compile(r"^a/(\S+) b/(\S+)")

DEFAULT_CHUNK_THRESHOLD_TOKENS = 30_000


class ReviewService:
    def __init__(self, provider: Provider):
        self._provider = provider

    def check(
        self,
        user: str,
        persona: str,
        diff: str,
        mode: ChunkMode = ChunkMode.AUTO,
        threshold: int = DEFAULT_CHUNK_THRESHOLD_TOKENS,
    ) -> Checklist:
        if not diff.strip():
            return Checklist(user=user, items=[])

        files = split_diff_by_file(diff)
        effective = _resolve_mode(mode, files, persona, diff, threshold)

        if effective == ChunkMode.WHOLE or len(files) <= 1:
            raw = self._provider.complete(REVIEW_SYSTEM, review_user_prompt(user, persona, diff))
            return _parse(user, raw)

        items: list[ChecklistItem] = []
        for _status, _path, chunk in files:
            raw = self._provider.complete(REVIEW_SYSTEM, review_user_prompt(user, persona, chunk))
            items.extend(_parse(user, raw).items)

        struct_raw = self._provider.complete(
            STRUCTURAL_SYSTEM,
            structural_user_prompt(user, persona, [(s, p) for s, p, _ in files]),
        )
        items.extend(_parse(user, struct_raw).items)

        return Checklist(user=user, items=_dedupe(items))


def diff_against(base: str) -> str:
    result = subprocess.run(
        ["git", "diff", f"{base}...HEAD"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git diff failed: {result.stderr.strip()}")
    return result.stdout


def split_diff_by_file(diff: str) -> list[tuple[str, str, str]]:
    """Return [(status, path, chunk), ...] where status is A/M/D/R."""
    if not diff.strip():
        return []
    parts = DIFF_SPLIT_RE.split(diff)
    out: list[tuple[str, str, str]] = []
    for part in parts[1:]:
        m = FILE_PATH_RE.match(part)
        if not m:
            continue
        path = m.group(2)
        header = part[:500]
        if "new file mode" in header:
            status = "A"
        elif "deleted file mode" in header:
            status = "D"
        elif "rename from" in header:
            status = "R"
        else:
            status = "M"
        out.append((status, path, "diff --git " + part))
    return out


def approx_tokens(text: str) -> int:
    return len(text) // 4


def _resolve_mode(
    mode: ChunkMode,
    files: list[tuple[str, str, str]],
    persona: str,
    diff: str,
    threshold: int,
) -> ChunkMode:
    if mode != ChunkMode.AUTO:
        return mode
    if len(files) <= 1:
        return ChunkMode.WHOLE
    if approx_tokens(persona) + approx_tokens(diff) < threshold:
        return ChunkMode.WHOLE
    return ChunkMode.PER_FILE


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


def _dedupe(items: list[ChecklistItem]) -> list[ChecklistItem]:
    seen: set[str] = set()
    out: list[ChecklistItem] = []
    for item in items:
        key = _norm(item.concern)[:40]
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", text.lower()).strip()
