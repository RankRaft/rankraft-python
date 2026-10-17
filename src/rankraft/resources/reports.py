"""The report endpoints.

POST requests that read nothing but data — the body carries a date range and a
filter tree, which is too much for a query string. They are marked retryable in
the operation table for exactly that reason; nothing here mutates anything.

Numbers match the dashboard by construction: both sides score the same facts
with the same package, so a Visibility Score here equals the one on screen.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from ..filters import Node
from ..pagination import Page
from ..types import (
    AnswerDimension,
    BotDimension,
    BotMetric,
    BotRow,
    CitationMetric,
    CitationRow,
    DateInput,
    ReferralDimension,
    ReferralMetric,
    ReferralRow,
    SentimentRow,
    Sort,
    VisibilityMetric,
    VisibilityRow,
)
from ._body import report_body

if TYPE_CHECKING:  # pragma: no cover
    from ..client import RankRaft

Filter = Node | dict[str, Any]


def _list(values: Sequence[str] | None) -> list[str] | None:
    return list(values) if values else None


class ReportsResource:
    def __init__(self, client: RankRaft) -> None:
        self._client = client

    def visibility(
        self,
        *,
        site_id: str,
        start_date: DateInput,
        end_date: DateInput,
        group_by: Sequence[AnswerDimension] | None = None,
        metrics: Sequence[VisibilityMetric] | None = None,
        brands: str | Sequence[str] | None = None,
        filter: Filter | None = None,
        sort: Sort | None = None,
        limit: int | None = None,
        cursor: str | None = None,
    ) -> Page[VisibilityRow]:
        """Visibility Score and its parts. ``brands``: ``"owned"`` (default), ``"all"`` or a list of names."""
        body = report_body(
            site_id=site_id,
            start_date=start_date,
            end_date=end_date,
            filter=filter,
            group_by=_list(group_by),
            metrics=_list(metrics),
            brands=list(brands) if isinstance(brands, (list, tuple)) else brands,
            sort=sort,
            limit=limit,
            cursor=cursor,
        )
        return self._client._paginate_body("report_visibility", body)

    def citations(
        self,
        *,
        site_id: str,
        start_date: DateInput,
        end_date: DateInput,
        entity: str | None = None,
        group_by: Sequence[str] | None = None,
        metrics: Sequence[CitationMetric] | None = None,
        filter: Filter | None = None,
        limit: int | None = None,
        cursor: str | None = None,
    ) -> Page[CitationRow]:
        """Where the engines got their answers. ``entity``: ``"domain"`` (default) or ``"page"``."""
        body = report_body(
            site_id=site_id,
            start_date=start_date,
            end_date=end_date,
            filter=filter,
            entity=entity,
            group_by=_list(group_by),
            metrics=_list(metrics),
            limit=limit,
            cursor=cursor,
        )
        return self._client._paginate_body("report_citations", body)

    def sentiment(
        self,
        *,
        site_id: str,
        start_date: DateInput,
        end_date: DateInput,
        group_by: Sequence[AnswerDimension] | None = None,
        filter: Filter | None = None,
        limit: int | None = None,
        cursor: str | None = None,
    ) -> Page[SentimentRow]:
        """Shares of positive / neutral / negative among answers that name you."""
        body = report_body(
            site_id=site_id,
            start_date=start_date,
            end_date=end_date,
            filter=filter,
            group_by=_list(group_by),
            limit=limit,
            cursor=cursor,
        )
        return self._client._paginate_body("report_sentiment", body)

    def bots(
        self,
        *,
        site_id: str,
        start_date: DateInput,
        end_date: DateInput,
        group_by: Sequence[BotDimension] | None = None,
        metrics: Sequence[BotMetric] | None = None,
        filter: Filter | None = None,
        timezone: str | None = None,
        sort: Sort | None = None,
        limit: int | None = None,
        cursor: str | None = None,
    ) -> Page[BotRow]:
        """AI crawler traffic from your own server logs. Accepts an IANA ``timezone``."""
        body = report_body(
            site_id=site_id,
            start_date=start_date,
            end_date=end_date,
            filter=filter,
            group_by=_list(group_by),
            metrics=_list(metrics),
            timezone=timezone,
            sort=sort,
            limit=limit,
            cursor=cursor,
        )
        return self._client._paginate_body("report_bots", body)

    def referrals(
        self,
        *,
        site_id: str,
        start_date: DateInput,
        end_date: DateInput,
        group_by: Sequence[ReferralDimension] | None = None,
        metrics: Sequence[ReferralMetric] | None = None,
        filter: Filter | None = None,
        timezone: str | None = None,
        sort: Sort | None = None,
        limit: int | None = None,
        cursor: str | None = None,
    ) -> Page[ReferralRow]:
        """People who arrived from an AI answer. Accepts an IANA ``timezone``."""
        body = report_body(
            site_id=site_id,
            start_date=start_date,
            end_date=end_date,
            filter=filter,
            group_by=_list(group_by),
            metrics=_list(metrics),
            timezone=timezone,
            sort=sort,
            limit=limit,
            cursor=cursor,
        )
        return self._client._paginate_body("report_referrals", body)
