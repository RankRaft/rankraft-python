"""Turn report parameters into the dict the paginator will freeze."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from ..filters import Node, to_filter
from ..types import DateInput


def to_day(value: DateInput) -> str:
    """Inclusive ``YYYY-MM-DD`` in UTC, which is how the API defines a scan day."""
    if isinstance(value, datetime):
        # A datetime is a subclass of date, and its isoformat() carries a time.
        # Aware datetimes are read in UTC, because that is what a scan day is.
        return (value.astimezone(timezone.utc) if value.tzinfo else value).date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str) and len(value) == 10 and value[4] == "-" and value[7] == "-":
        return value
    raise ValueError(f"rankraft: dates must be YYYY-MM-DD or a datetime.date, got {value!r}")


def report_body(
    *,
    site_id: str,
    start_date: DateInput,
    end_date: DateInput,
    filter: Node | dict[str, Any] | None = None,
    **rest: Any,
) -> dict[str, Any]:
    """Drop ``None`` keys, normalise the dates, grammar-check the filter.

    The filter is checked here so a malformed node raises in the caller's own
    stack frame rather than coming back as a 422 one round trip later. Only the
    grammar: depth and list length are the server's limits and are not copied.
    """
    body: dict[str, Any] = {"site_id": site_id}
    for key, value in rest.items():
        if value is not None:
            body[key] = value
    if filter is not None:
        body["filter"] = to_filter(filter)
    body["start_date"] = to_day(start_date)
    body["end_date"] = to_day(end_date)
    return body
