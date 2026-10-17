"""Prompts are the only thing this API can write, and it cannot delete them.

Deleting a prompt cascades away its answer history and any Action Center
baseline that targeted it, so the API offers ``set_status(..., "disabled")``
instead. Prompt text is immutable for the same reason: changing it would make
the history either side of the edit incomparable while still looking like one
continuous series.

The write endpoints answer ``{dry_run, created, …, data}`` rather than the
usual ``{info, data}``, and the fields beside ``data`` are the point - so these
methods return the whole body, not the unwrapped ``data``.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import TYPE_CHECKING, Literal

from ..pagination import Page
from ..types import CreatePromptsResult, NewPrompt, Prompt, PromptPatch, SetPromptStatusResult, UpdatePromptsResult

if TYPE_CHECKING:  # pragma: no cover
    from ..client import RankRaft


def _dumps(body: dict[str, object]) -> str:
    return json.dumps(body, separators=(",", ":"))


class PromptsResource:
    def __init__(self, client: RankRaft) -> None:
        self._client = client

    def list(
        self,
        *,
        site_id: str,
        status: Literal["active", "disabled"] | None = None,
        category: str | None = None,
        limit: int | None = None,
        cursor: str | None = None,
    ) -> Page[Prompt]:
        """Oldest first."""
        return self._client._paginate_query(
            "list_prompts",
            path_params={"site_id": site_id},
            query={"status": status, "category": category, "limit": limit, "cursor": cursor},
        )

    def create(self, *, site_id: str, prompts: Sequence[NewPrompt], dry_run: bool = False) -> CreatePromptsResult:
        """Up to 100 per call.

        Text that already exists (ignoring case and spacing) comes back as the
        existing prompt rather than a duplicate, which is also why this call is
        safe to retry. A request that would exceed the plan's active-prompt cap
        is refused whole with ``PromptLimitError``.
        """
        body = _dumps({"prompts": list(prompts), "dry_run": dry_run})
        return self._client._call("create_prompts", path_params={"site_id": site_id}, body_text=body).body  # type: ignore[no-any-return]

    def update(self, *, site_id: str, prompts: Sequence[PromptPatch], dry_run: bool = False) -> UpdatePromptsResult:
        """Category and market only. Text is immutable."""
        body = _dumps({"prompts": list(prompts), "dry_run": dry_run})
        return self._client._call("update_prompts", path_params={"site_id": site_id}, body_text=body).body  # type: ignore[no-any-return]

    def set_status(
        self,
        *,
        site_id: str,
        prompt_ids: Sequence[str],
        status: Literal["active", "disabled"],
        dry_run: bool = False,
    ) -> SetPromptStatusResult:
        """Disabled prompts stop being asked but keep their history.

        Activating past the plan's cap raises ``PromptLimitError`` with how many
        slots remain; this client keeps no copy of that cap.
        """
        body = _dumps({"prompt_ids": list(prompt_ids), "status": status, "dry_run": dry_run})
        return self._client._call("set_prompt_status", path_params={"site_id": site_id}, body_text=body).body  # type: ignore[no-any-return]
