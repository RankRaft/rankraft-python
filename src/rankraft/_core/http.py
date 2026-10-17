"""The transport: one request, with retries, against the RankRaft AI API."""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import httpx

from ..errors import APIConnectionError, APITimeoutError, error_from
from ..operations import Operation, expand_path
from .retry import RetryInfo, decide, parse_retry_after


@dataclass
class Response:
    data: Any
    #: The whole parsed body. Most routes answer ``{info, data}`` and ``data`` is
    #: what callers want; the prompt writes answer ``{dry_run, created, …, data}``
    #: where the fields beside ``data`` are the point, so they read this instead.
    body: Any
    info: dict[str, Any]
    request_id: str | None
    status: int
    headers: dict[str, str]
    #: The exact bytes sent, so pagination can assert it resends them.
    sent_body: str | None = None


@dataclass
class Transport:
    api_key: str
    base_url: str
    client: httpx.Client
    user_agent: str
    max_retries: int = 2
    max_retry_wait: float = 70.0
    default_headers: dict[str, str] = field(default_factory=dict)
    on_retry: Callable[[RetryInfo], None] | None = None
    sleep: Callable[[float], None] = time.sleep

    def request(
        self,
        operation: Operation,
        *,
        path_params: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        body_text: str | None = None,
        max_retries: int | None = None,
    ) -> Response:
        url = self.base_url.rstrip("/") + expand_path(operation.path, path_params)
        query = {k: v for k, v in (params or {}).items() if v is not None}

        headers: dict[str, str] = {"accept": "application/json", "user-agent": self.user_agent, **self.default_headers}
        # The key is a header, always. The API rejects a key in the query
        # string with a 400 precisely so keys stay out of access logs; this
        # client is not going to be the thing that puts one there.
        if operation.authenticated:
            headers["x-api-key"] = self.api_key
        if body_text is not None:
            headers["content-type"] = "application/json"

        retries = self.max_retries if max_retries is None else max_retries
        attempt = 0
        slept = 0.0
        attempt_request_ids: list[str] = []

        while True:
            attempt += 1
            response: httpx.Response | None = None
            timed_out = False
            cause: BaseException | None = None

            try:
                response = self.client.request(
                    operation.method,
                    url,
                    params=query or None,
                    headers=headers,
                    content=body_text,
                )
            except httpx.TimeoutException as exc:
                timed_out, cause = True, exc
            except httpx.TransportError as exc:
                cause = exc

            if response is not None:
                res_headers = {k.lower(): v for k, v in response.headers.items()}
                parsed = _json_or_none(response.text)
                request_id = _request_id(parsed, res_headers)
                if request_id:
                    attempt_request_ids.append(request_id)

                if response.is_success:
                    envelope = parsed if isinstance(parsed, dict) else None
                    # The spec route is not enveloped; everything else is.
                    data = envelope["data"] if operation.authenticated and envelope and "data" in envelope else parsed
                    info = envelope.get("info") or {} if envelope else {}
                    return Response(
                        data=data,
                        body=parsed,
                        info=info if isinstance(info, dict) else {},
                        request_id=request_id,
                        status=response.status_code,
                        headers=res_headers,
                        sent_body=body_text,
                    )

                retry_after = parse_retry_after(res_headers.get("retry-after"))
                decision = decide(
                    operation=operation,
                    attempt=attempt,
                    max_retries=retries,
                    status=response.status_code,
                    retry_after=retry_after,
                )
                if decision.retry and slept + decision.wait <= self.max_retry_wait:
                    if self.on_retry and decision.reason:
                        self.on_retry(RetryInfo(attempt, retries, decision.wait, decision.reason, response.status_code))
                    self.sleep(decision.wait)
                    slept += decision.wait
                    continue

                body = parsed if isinstance(parsed, dict) else {}
                raw_error = body.get("error")
                err: dict[str, Any] = raw_error if isinstance(raw_error, dict) else {}
                raise error_from(
                    status=response.status_code,
                    code=err.get("code") or _fallback_code(response.status_code),
                    message=err.get("message") or response.reason_phrase or "request failed",
                    details=err.get("details"),
                    request_id=request_id,
                    headers=res_headers,
                    attempts=attempt,
                    attempt_request_ids=attempt_request_ids,
                )

            decision = decide(
                operation=operation,
                attempt=attempt,
                max_retries=retries,
                status=None,
                retry_after=None,
                network_error=True,
                timed_out=timed_out,
            )
            if decision.retry and slept + decision.wait <= self.max_retry_wait:
                if self.on_retry and decision.reason:
                    self.on_retry(RetryInfo(attempt, retries, decision.wait, decision.reason, None))
                self.sleep(decision.wait)
                slept += decision.wait
                continue

            if timed_out:
                raise APITimeoutError(f"rankraft: {operation.method} {operation.path} timed out", cause)
            raise APIConnectionError(f"rankraft: could not reach {self.base_url}", cause)


def _json_or_none(text: str) -> Any:
    if not text:
        return None
    try:
        return json.loads(text)
    except ValueError:
        return None


def _request_id(parsed: Any, headers: dict[str, str]) -> str | None:
    # The header fallback is not cosmetic: a Cloudflare-level 502, or a body
    # rejected before the handler ran, returns no JSON at all - and that is
    # exactly when the id matters most.
    if isinstance(parsed, dict):
        value = parsed.get("request_id")
        if isinstance(value, str):
            return value
    return headers.get("x-request-id") or headers.get("cf-ray")


def _fallback_code(status: int) -> str:
    return {
        401: "invalid_api_key",
        404: "not_found",
        413: "payload_too_large",
        409: "conflict",
        422: "invalid_request",
        429: "rate_limited",
    }.get(status, "internal_error" if status >= 500 else "bad_request")
