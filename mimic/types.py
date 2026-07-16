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


class SignalKind(StrEnum):
    PR = "pr"
    COMMITS = "commits"
    ISSUES = "issues"
    ALL = "all"


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


class CommitFile(BaseModel):
    path: str
    status: str
    additions: int = 0
    deletions: int = 0
    patch: str = ""


class CommitSample(BaseModel):
    repo: str
    sha: str
    subject: str
    body: str = ""
    files: list[CommitFile] = []
    created_at: datetime
    url: str


class IssueSample(BaseModel):
    repo: str
    number: int
    title: str
    body: str = ""
    created_at: datetime
    url: str


class SignalsBundle(BaseModel):
    comments: list[ReviewComment] = Field(default_factory=list)
    commits: list[CommitSample] = Field(default_factory=list)
    issues: list[IssueSample] = Field(default_factory=list)

    def total(self) -> int:
        return len(self.comments) + len(self.commits) + len(self.issues)

    def extend(self, other: "SignalsBundle") -> None:
        self.comments.extend(other.comments)
        self.commits.extend(other.commits)
        self.issues.extend(other.issues)


class Source(BaseModel):
    key: str
    kind: str
    scraped_at: datetime
    since: datetime | None = None
    comment_count: int
    commit_count: int
    issue_count: int


class Persona(BaseModel):
    user: str
    generated_at: datetime
    comment_count: int
    commit_count: int = 0
    issue_count: int = 0
    repos: list[str]
    since: datetime | None = None
    body: str

    def render(self) -> str:
        signal_bits = []
        if self.comment_count:
            signal_bits.append(f"{self.comment_count} comments")
        if self.commit_count:
            signal_bits.append(f"{self.commit_count} commits")
        if self.issue_count:
            signal_bits.append(f"{self.issue_count} issues")
        lines = [
            f"# style persona: @{self.user}",
            "",
            f"_generated {self.generated_at.strftime('%Y-%m-%d')} from {' + '.join(signal_bits) or 'a hand-edited body'}"
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
