from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class ProviderKind(StrEnum):
    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    OLLAMA = "ollama"


class ChunkMode(StrEnum):
    AUTO = "auto"
    WHOLE = "whole"
    PER_FILE = "per-file"


class CommentKind(StrEnum):
    REVIEW_COMMENT = "review_comment"
    REVIEW_BODY = "review_body"
    ISSUE_COMMENT = "issue_comment"


class ReviewComment(BaseModel):
    kind: CommentKind
    repo: str
    pr_number: int
    pr_title: str
    author: str
    body: str
    path: str | None = None
    line: int | None = None
    diff_hunk: str | None = None
    created_at: datetime
    url: str


class CommitSample(BaseModel):
    repo: str
    sha: str
    subject: str
    body: str = ""
    created_at: datetime
    url: str


class Persona(BaseModel):
    user: str
    generated_at: datetime
    comment_count: int
    commit_count: int = 0
    repos: list[str]
    since: datetime | None = None
    body: str

    def render(self) -> str:
        signal_bits = [f"{self.comment_count} comments"]
        if self.commit_count:
            signal_bits.append(f"{self.commit_count} commits")
        lines = [
            f"# style persona: @{self.user}",
            "",
            f"_generated {self.generated_at.strftime('%Y-%m-%d')} from {' + '.join(signal_bits)}"
            + (f" across {len(self.repos)} repos" if len(self.repos) > 1 else "")
            + (f", since {self.since.strftime('%Y-%m-%d')}" if self.since else "")
            + "_",
            "",
            self.body.strip(),
            "",
        ]
        return "\n".join(lines)


class ChecklistItem(BaseModel):
    file: str | None = None
    line: int | None = None
    concern: str
    suggestion: str = Field(default="")

    def render(self) -> str:
        loc = ""
        if self.file:
            loc = f"{self.file}"
            if self.line:
                loc += f":{self.line}"
            loc = f" ({loc})"
        out = f"- {self.concern}{loc}"
        if self.suggestion:
            out += f"\n  → {self.suggestion}"
        return out


class Checklist(BaseModel):
    user: str
    items: list[ChecklistItem]

    def render(self) -> str:
        if not self.items:
            return f"no likely nits from @{self.user}.\n"
        header = f"likely nits from @{self.user} ({len(self.items)}):\n"
        return header + "\n".join(item.render() for item in self.items) + "\n"
