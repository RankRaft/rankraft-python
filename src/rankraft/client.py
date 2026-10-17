"""The RankRaft AI client.

Synchronous only in v1. ``httpx`` is here partly so an ``AsyncRankRaft`` can be
added later without a rewrite — the retry decision, the envelope handling and
the paginator are all transport-agnostic already.
"""

from __future__ import annotations

import os
import platform
from collections.abc import Callable
from types import TracebackType
from typing import Any, TypeVar
from urllib.parse import parse_qs, urlparse

import httpx

from ._core.http import Response, Transport
from ._core.retry import RetryInfo
from ._version import SPEC_VERSION, VERSION
from .errors import ConfigurationError
from .operations import OPERATIONS
from .pagination import Page, serialize_with_cursor
from .resources.answers import AnswersResource
from .resources.platforms import PlatformsResource
from .resources.prompts import PromptsResource
from .resources.reports import ReportsResource
from .resources.sites import SitesResource
from .types import Me

TRow = TypeVar("TRow")

DEFAULT_BASE_URL = "https://api.rankraft.ai/v1"
_KEY_LIKE_PARAMS = ("api_key", "apikey", "key", "token", "access_token")
#: Every RankRaft AI API key starts with this. Site keys (``rr_live_``) are a different thing.
KEY_PREFIX = "rr_api_"


class RankRaft:
    """A client for one organization's RankRaft AI data.

    :param api_key: defaults to ``RANKRAFT_API_KEY``.
    :param base_url: defaults to ``RANKRAFT_BASE_URL`` or the production API.
    :param timeout: seconds, per attempt rather than per call.
    :param max_retries: attempts after the first. 0 disables retrying.
    :param max_retry_wait: total seconds this client may spend asleep inside
        one logical call. A 429 carries ``Retry-After: 60`` and the window has
        no remaining-count header, so honouring it means a real 60-second
        pause; the default of 70 permits exactly one such retry and then
        raises. A library that silently blocks for two minutes is hostile.
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float = 60.0,
        max_retries: int = 2,
        max_retry_wait: float = 70.0,
        transport: httpx.BaseTransport | None = None,
        http_client: httpx.Client | None = None,
        default_headers: dict[str, str] | None = None,
        user_agent_suffix: str | None = None,
        on_retry: Callable[[RetryInfo], None] | None = None,
    ) -> None:
        key = (api_key or os.environ.get("RANKRAFT_API_KEY") or "").strip()
        if not key:
            raise ConfigurationError(
                "rankraft: no API key. Pass api_key= or set RANKRAFT_API_KEY. "
                "Create a key in the dashboard under Settings → API."
            )
        # The prefix only — never the full shape, which a pinned client must
        # not enforce. This catches the one mistake that is otherwise a
        # confusing 401: pasting a site key (rr_live_…) where an API key belongs.
        if not key.startswith(KEY_PREFIX):
            raise ConfigurationError(
                f"rankraft: that is not an API key — API keys start with {KEY_PREFIX!r}. "
                "A site key (rr_live_…) is for sending traffic, not reading it."
            )

        url = base_url or os.environ.get("RANKRAFT_BASE_URL") or DEFAULT_BASE_URL
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            raise ConfigurationError(f"rankraft: base_url is not a valid URL: {url!r}")
        # Refuse a base URL carrying a credential. The API rejects a key in the
        # query string with a 400 so that keys stay out of access logs; this
        # client will not smuggle one in through configuration.
        for name in parse_qs(parsed.query):
            if name.lower() in _KEY_LIKE_PARAMS:
                raise ConfigurationError(
                    f"rankraft: base_url carries a {name!r} query parameter. "
                    "Credentials belong in the X-API-Key header, never in a URL."
                )

        user_agent = " ".join(
            part
            for part in (
                f"rankraft-python/{VERSION}",
                f"spec/{SPEC_VERSION}",
                f"python/{platform.python_version()}",
                user_agent_suffix,
            )
            if part
        )

        self._owns_client = http_client is None
        client = http_client or httpx.Client(timeout=timeout, transport=transport)
        self._transport = Transport(
            api_key=key,
            base_url=url,
            client=client,
            user_agent=user_agent,
            max_retries=max_retries,
            max_retry_wait=max_retry_wait,
            default_headers=default_headers or {},
            on_retry=on_retry,
        )

        self.sites = SitesResource(self)
        self.platforms = PlatformsResource(self)
        self.prompts = PromptsResource(self)
        self.reports = ReportsResource(self)
        self.answers = AnswersResource(self)

    # -- lifecycle ---------------------------------------------------------

    def close(self) -> None:
        if self._owns_client:
            self._transport.client.close()

    def __enter__(self) -> RankRaft:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    # -- public ------------------------------------------------------------

    def me(self) -> Me:
        """The key, the organization, the plan and the rate limits it is under."""
        return self._call("get_me").data  # type: ignore[no-any-return]

    def openapi(self) -> dict[str, Any]:
        """The published OpenAPI document. Unauthenticated; no key is sent."""
        return self._call("get_openapi").data  # type: ignore[no-any-return]

    def request(
        self,
        method: str,
        path: str,
        *,
        body: Any = None,
        params: dict[str, Any] | None = None,
    ) -> Response:
        """Escape hatch for a route this version does not model yet."""
        import json

        from .operations import Operation

        operation = Operation(method=method, path=path, retryable=method == "GET", paginates=False)  # type: ignore[arg-type]
        return self._transport.request(
            operation,
            params=params,
            body_text=None if body is None else json.dumps(body, separators=(",", ":")),
        )

    # -- internal ----------------------------------------------------------

    def _call(
        self,
        name: str,
        *,
        path_params: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        body_text: str | None = None,
    ) -> Response:
        return self._transport.request(
            OPERATIONS[name], path_params=path_params, params=params, body_text=body_text
        )

    def _paginate_body(self, name: str, base_body: dict[str, Any]) -> Page[Any]:
        """Paginate a POST whose cursor lives in the body.

        ``serialize_with_cursor`` drops any cursor and appends the live one
        last, so every page's bytes are identical apart from one trailing
        field — which is what the server's body-hash-bound cursor requires.
        """
        frozen = dict(base_body)
        initial = frozen.get("cursor") if isinstance(frozen.get("cursor"), str) else None

        def fetch_page(cursor: str | None) -> Page[Any]:
            res = self._call(name, body_text=serialize_with_cursor(frozen, cursor))
            return Page(
                data=res.data or [],
                info=res.info,
                request_id=res.request_id,
                cursor=cursor,
                fetch_page=fetch_page,
            )

        return fetch_page(initial)

    def _paginate_query(
        self, name: str, *, path_params: dict[str, str], query: dict[str, Any]
    ) -> Page[Any]:
        """Paginate a GET whose cursor is a query parameter."""
        frozen = {k: v for k, v in query.items() if k != "cursor"}
        initial = query.get("cursor") if isinstance(query.get("cursor"), str) else None

        def fetch_page(cursor: str | None) -> Page[Any]:
            res = self._call(
                name,
                path_params=path_params,
                params={**frozen, **({} if cursor is None else {"cursor": cursor})},
            )
            return Page(
                data=res.data or [],
                info=res.info,
                request_id=res.request_id,
                cursor=cursor,
                fetch_page=fetch_page,
            )

        return fetch_page(initial)
