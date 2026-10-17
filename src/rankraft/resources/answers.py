"""Raw stored answers, newest first.

Lives at ``/v1/answers`` rather than under ``/v1/reports/``, which is why it is
``client.answers.query()`` and not ``client.reports.answers()`` - the client
mirrors the routes rather than tidying them, so a path in the docs is findable
in the SDK. Pages are small (at most 50) because answers are long.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from ..pagination import Page
from ..types import AnswerField, AnswerRow, DateInput, Platform
from ._body import report_body

if TYPE_CHECKING:  # pragma: no cover
    from ..client import RankRaft


class AnswersResource:
    def __init__(self, client: RankRaft) -> None:
        self._client = client

    def query(
        self,
        *,
        site_id: str,
        start_date: DateInput,
        end_date: DateInput,
        platforms: Sequence[Platform] | None = None,
        prompt_ids: Sequence[str] | None = None,
        include: Sequence[AnswerField] | None = None,
        limit: int | None = None,
        cursor: str | None = None,
    ) -> Page[AnswerRow]:
        """``platforms`` up to 10, ``prompt_ids`` up to 100, ``include`` defaults to every field."""
        body = report_body(
            site_id=site_id,
            start_date=start_date,
            end_date=end_date,
            platforms=list(platforms) if platforms else None,
            prompt_ids=list(prompt_ids) if prompt_ids else None,
            include=list(include) if include else None,
            limit=limit,
            cursor=cursor,
        )
        return self._client._paginate_body("query_answers", body)
