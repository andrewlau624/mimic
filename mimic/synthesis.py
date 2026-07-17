from datetime import datetime

from mimic.prompts import SYNTHESIS_SYSTEM, synthesis_user_prompt
from mimic.providers import Provider
from mimic.types import CommitSample, Persona, ReviewComment


class SynthesisService:
    def __init__(self, provider: Provider):
        self._provider = provider

    def build_persona(
        self,
        user: str,
        comments: list[ReviewComment],
        commits: list[CommitSample],
        since: datetime | None,
    ) -> Persona:
        if not comments and not commits:
            raise ValueError(f"no signals found for @{user}.")
        body = self._provider.complete(
            SYNTHESIS_SYSTEM,
            synthesis_user_prompt(user, comments, commits),
        )
        repos = sorted({c.repo for c in comments} | {c.repo for c in commits})
        return Persona(
            user=user,
            generated_at=datetime.now().astimezone(),
            comment_count=len(comments),
            commit_count=len(commits),
            repos=repos,
            since=since,
            body=body,
        )
