"""Cursor pagination, where the cursor is bound to a hash of the request body.

That binding is why this module is careful. The body sent on page one is frozen
and re-sent verbatim; only ``cursor`` is substituted. Two things are therefore
forbidden, and both are tempting:

* rebuilding the body from ``info["filter"]``. The server echoes a *normalised*
  filter, so round-tripping it changes the bytes and page two returns 400.
* re-serialising the caller's object each page. A caller who mutates their
  filter inside the loop would silently change the query mid-iteration.

``cursor`` is always dropped and re-appended last, so every page's body is
byte-identical except for one trailing field.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from typing import TYPE_CHECKING, Any, Generic, TypeVar

from .errors import PaginationError

if TYPE_CHECKING:  # pragma: no cover
    import pandas

TRow = TypeVar("TRow")

# Which columns to_pandas() treats as dimensions and which as measures. The
# API decides the row shape at call time, so this is a shape heuristic rather
# than a schema - anything unlisted is left exactly as the API sent it.
_DIMENSIONS = (
    "platform",
    "category",
    "bot_name",
    "bot_provider",
    "bot_type",
    "page_type",
    "referral_source",
    "owner",
    "source_kind",
)
_METRIC_SUFFIXES = ("_rate", "_score", "_share", "_position")
_METRIC_NAMES = frozenset({"answers", "citations", "hits", "pages", "visits", "rank"})


def serialize_with_cursor(base: dict[str, Any], cursor: str | None = None) -> str:
    rest = {k: v for k, v in base.items() if k != "cursor" and v is not None}
    if cursor is not None:
        rest["cursor"] = cursor
    return json.dumps(rest, separators=(",", ":"))


class Page(Generic[TRow]):
    def __init__(
        self,
        *,
        data: list[TRow],
        info: dict[str, Any],
        request_id: str | None,
        cursor: str | None,
        fetch_page: Callable[[str | None], Page[TRow]],
    ) -> None:
        self.data = data
        self.info = info
        self.request_id = request_id
        #: The cursor that produced this page; None for the first.
        self.cursor = cursor
        self._fetch_page = fetch_page

    @property
    def next_cursor(self) -> str | None:
        value = self.info.get("next_cursor")
        return value if isinstance(value, str) and value else None

    def has_next_page(self) -> bool:
        return self.next_cursor is not None

    def next_page(self) -> Page[TRow]:
        nxt = self.next_cursor
        if nxt is None:
            raise PaginationError("rankraft: there is no next page")
        # Fail closed rather than loop forever. A server handing back the
        # cursor it was given is a bug, and an infinite loop is the worst
        # possible way to discover it.
        if nxt == self.cursor:
            raise PaginationError(
                f"rankraft: the API returned the same cursor twice ({nxt[:12]}…), which would loop forever"
            )
        return self._fetch_page(nxt)

    def __iter__(self) -> Iterator[TRow]:
        """This page only.

        Deliberately not every page: a bare ``for row in page`` silently
        hitting the network inside a notebook cell surprises people. Use
        :meth:`auto_paging` to cross page boundaries, where the name says so.
        """
        return iter(self.data)

    def __len__(self) -> int:
        return len(self.data)

    def auto_paging(self) -> Iterator[TRow]:
        """Every row on every page."""
        page: Page[TRow] = self
        while True:
            yield from page.data
            if not page.has_next_page():
                return
            page = page.next_page()

    def iter_pages(self) -> Iterator[Page[TRow]]:
        page: Page[TRow] = self
        while True:
            yield page
            if not page.has_next_page():
                return
            page = page.next_page()

    def all(self) -> list[TRow]:
        """Every row, collected. Unbounded by design."""
        return list(self.auto_paging())

    def to_pandas(self, *, all_pages: bool = False) -> pandas.DataFrame:
        """A DataFrame with dtypes that are actually right.

        ``pd.DataFrame(page.data)`` is one line shorter and subtly wrong: dates
        land as object strings, sparse metrics as ``object``, and dimension
        columns are not categorical. Getting that right is the reason this
        method exists rather than a docs snippet.
        """
        try:
            import pandas as pd
        except ImportError as exc:  # pragma: no cover - exercised by hand
            raise ImportError(
                "rankraft: to_pandas() needs pandas. Install it with: pip install 'rankraft[pandas]'"
            ) from exc

        rows = self.all() if all_pages else self.data
        frame = pd.DataFrame(rows)
        if frame.empty:
            return frame

        if "date" in frame.columns:
            frame["date"] = pd.to_datetime(frame["date"], utc=True, errors="coerce")
        for column in ("hour", "last_visit"):
            if column in frame.columns:
                frame[column] = pd.to_datetime(frame[column], utc=True, errors="coerce")
        for column in _DIMENSIONS:
            if column in frame.columns:
                frame[column] = frame[column].astype("category")
        for column in frame.columns:
            if column.endswith(_METRIC_SUFFIXES) or column in _METRIC_NAMES:
                frame[column] = pd.to_numeric(frame[column], errors="coerce")
        return frame
