"""When to try again, and how long to wait.

Two rules carry the weight. Retryability comes from the operation table, not
the HTTP method, because this API's reports are POSTs that read. And a 429 is
always retryable regardless of the operation, because the rate limiter rejects
the request *before* the handler runs, so nothing happened.
"""

from __future__ import annotations

import random as _random
import time
from collections.abc import Callable
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from typing import Literal

from ..operations import Operation

RetryReason = Literal["connection", "timeout", "status", "rate_limit"]

_RETRYABLE_STATUS = frozenset({408, 500, 502, 503, 504})


@dataclass(frozen=True)
class RetryDecision:
    retry: bool
    wait: float
    reason: RetryReason | None


@dataclass(frozen=True)
class RetryInfo:
    attempt: int
    max_retries: int
    wait: float
    reason: RetryReason
    status: int | None


def parse_retry_after(raw: str | None, now: float | None = None) -> float | None:
    """``Retry-After`` is seconds or an HTTP date. Anything else is ignored."""
    if raw is None or raw == "":
        return None
    try:
        return max(0.0, float(raw))
    except ValueError:
        pass
    try:
        when = float(parsedate_to_datetime(raw).timestamp())
        elapsed: float = when - (now if now is not None else time.time())
        return max(0.0, elapsed)
    except (TypeError, ValueError):
        return None


def backoff(attempt: int, rand: Callable[[], float] = _random.random) -> float:
    """Exponential with full jitter. Used for everything except a 429."""
    return rand() * min(0.5 * 2.0 ** (attempt - 1), 8.0)


def decide(
    *,
    operation: Operation,
    attempt: int,
    max_retries: int,
    status: int | None,
    retry_after: float | None,
    network_error: bool = False,
    timed_out: bool = False,
    rand: Callable[[], float] = _random.random,
) -> RetryDecision:
    none = RetryDecision(False, 0.0, None)
    if attempt > max_retries:
        return none

    if status == 429:
        # Honour Retry-After exactly and never sooner. The window is a fixed
        # 60s with no remaining-count header, so an early retry is guaranteed
        # to fail *and* spends another request from the caller's budget.
        return RetryDecision(True, retry_after if retry_after is not None else 60.0, "rate_limit")

    if not operation.retryable:
        return none

    if network_error or timed_out:
        return RetryDecision(True, backoff(attempt, rand), "timeout" if timed_out else "connection")
    if status is not None and status in _RETRYABLE_STATUS:
        return RetryDecision(True, retry_after if retry_after is not None else backoff(attempt, rand), "status")
    return none
