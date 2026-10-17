"""Every error this client raises.

Mapping is by ``error.code`` first and HTTP status second, so a code the API
adds later lands on the right status class instead of crashing a pinned
install. The same names and hierarchy exist in the Node SDK, so one support
answer covers both.
"""

from __future__ import annotations

from typing import Any


class RankRaftError(Exception):
    """Base class for everything this library raises."""


class ConfigurationError(RankRaftError):
    """Something about how the client was constructed, before any request."""


class APIConnectionError(RankRaftError):
    """The request never produced an HTTP response."""

    def __init__(self, message: str, cause: BaseException | None = None) -> None:
        super().__init__(message)
        self.__cause__ = cause


class APITimeoutError(APIConnectionError):
    pass


class PaginationError(RankRaftError):
    """Auto-pagination could not make progress."""


class APIError(RankRaftError):
    """An HTTP error response from the API."""

    def __init__(
        self,
        *,
        status: int,
        code: str,
        message: str,
        details: Any = None,
        request_id: str | None = None,
        headers: dict[str, str] | None = None,
        attempts: int = 1,
        attempt_request_ids: list[str] | None = None,
    ) -> None:
        # The id goes in the message, not only on an attribute. People paste
        # tracebacks; they do not know to read ``err.request_id``.
        suffix = ", ".join(
            part
            for part in (
                f"request_id={request_id}" if request_id else "",
                f"attempt {attempts}" if attempts > 1 else "",
            )
            if part
        )
        super().__init__(f"rankraft {status} {code}: {message}" + (f" ({suffix})" if suffix else ""))
        self.status = status
        self.code = code
        self.details = details
        #: The last attempt's id. ``cf-ray`` differs per attempt.
        self.request_id = request_id
        self.headers = headers or {}
        self.attempts = attempts
        self.attempt_request_ids = attempt_request_ids or []


class BadRequestError(APIError):
    pass


class InvalidCursorError(BadRequestError):
    """400 ``invalid_cursor``. The cursor belongs to a different query.

    The server fingerprints every field except ``cursor`` and ``limit``, so
    this means the filter, range, grouping or metrics changed between pages.
    Start again without a cursor.
    """


class AuthenticationError(APIError):
    """401. Missing, unknown, revoked or expired - one indistinguishable answer."""


class PlanRequiredError(APIError):
    """403. The organization is not on a live Enterprise plan."""


class PermissionDeniedError(APIError):
    """403. A read key tried to write."""


class NotFoundError(APIError):
    """404. No site with that id **in this organization** - the API will not
    confirm whether it exists elsewhere, so ids cannot be enumerated."""


class ConflictError(APIError):
    """409. Today only ``site_not_set_up``: the site has no brand profile yet."""


class PayloadTooLargeError(APIError):
    pass


class ValidationError(APIError):
    @property
    def issues(self) -> list[Any]:
        return self.details if isinstance(self.details, list) else []


class PromptLimitError(ValidationError):
    """422 ``prompt_limit_reached``. ``details`` carries limit, active, requested, remaining."""

    @property
    def remaining(self) -> int | None:
        value = self.details.get("remaining") if isinstance(self.details, dict) else None
        return value if isinstance(value, int) else None

    @property
    def limit(self) -> int | None:
        value = self.details.get("limit") if isinstance(self.details, dict) else None
        return value if isinstance(value, int) else None


class RateLimitError(APIError):
    @property
    def retry_after_seconds(self) -> float | None:
        from ._core.retry import parse_retry_after

        return parse_retry_after(self.headers.get("retry-after"))

    @property
    def limit(self) -> str | None:
        return self.headers.get("x-ratelimit-limit")

    @property
    def policy(self) -> str | None:
        return self.headers.get("x-ratelimit-policy")


class InternalServerError(APIError):
    pass


#: Codes we know by name. Unknown codes fall through to the status class,
#: which is why a new server-side code can never break an older client.
#: The conformance test asserts these keys equal the spec's error-code enum.
ERROR_CODE_CLASSES: dict[str, type[APIError]] = {
    # 400
    "invalid_json": BadRequestError,
    "invalid_cursor": InvalidCursorError,
    "api_key_in_url": BadRequestError,
    # 401 / 403
    "invalid_api_key": AuthenticationError,
    "plan_required": PlanRequiredError,
    "insufficient_permission": PermissionDeniedError,
    # 404 / 409 / 413 / 415
    "not_found": NotFoundError,
    "site_not_set_up": ConflictError,
    "payload_too_large": PayloadTooLargeError,
    "unsupported_media_type": BadRequestError,
    # 422 - all validation, one of them with structured details
    "invalid_request": ValidationError,
    "invalid_filter": ValidationError,
    "invalid_date_range": ValidationError,
    "invalid_timezone": ValidationError,
    "invalid_sort": ValidationError,
    "prompt_limit_reached": PromptLimitError,
    # 429 / 5xx
    "rate_limited": RateLimitError,
    "internal_error": InternalServerError,
}

_STATUS_CLASSES: dict[int, type[APIError]] = {
    400: BadRequestError,
    401: AuthenticationError,
    403: PlanRequiredError,
    404: NotFoundError,
    409: ConflictError,
    413: PayloadTooLargeError,
    422: ValidationError,
    429: RateLimitError,
}


def error_from(
    *,
    status: int,
    code: str,
    message: str,
    details: Any = None,
    request_id: str | None = None,
    headers: dict[str, str] | None = None,
    attempts: int = 1,
    attempt_request_ids: list[str] | None = None,
) -> APIError:
    cls = ERROR_CODE_CLASSES.get(code)
    if cls is None:
        # 403 is ambiguous by status alone - plan_required and
        # insufficient_permission share it - so the code above is what
        # distinguishes them and this is only the fallback.
        cls = _STATUS_CLASSES.get(status, InternalServerError if status >= 500 else APIError)
    return cls(
        status=status,
        code=code,
        message=message,
        details=details,
        request_id=request_id,
        headers=headers,
        attempts=attempts,
        attempt_request_ids=attempt_request_ids,
    )
