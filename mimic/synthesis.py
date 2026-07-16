from datetime import datetime

from mimic.prompts import SYNTHESIS_SYSTEM, synthesis_user_prompt
from mimic.providers import Provider
from mimic.types import Persona, ReviewComment


class SynthesisService:
    def __init__(self, provider: Provider):
        self._provider = provider

    def build_persona(
        self,
        user: str,
        comments: list[ReviewComment],
        since: datetime | None,
    ) -> Persona:
        if not comments:
            raise ValueError(f"no reviewable comments found for @{user}.")
        body = self._provider.complete(SYNTHESIS_SYSTEM, synthesis_user_prompt(user, comments))
        return Persona(
            user=user,
            generated_at=datetime.now().astimezone(),
            comment_count=len(comments),
            repos=sorted({c.repo for c in comments}),
            since=since,
            body=body,
        )
