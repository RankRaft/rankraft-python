from __future__ import annotations

from dataclasses import replace

import pytest

from rankraft import OPERATIONS, RateLimitError, ValidationError
from rankraft._core.retry import backoff, decide, parse_retry_after

from .conftest import Reply, envelope

READ = OPERATIONS["report_visibility"]
WRITE = replace(OPERATIONS["create_prompts"], retryable=False)


def test_429_is_retried_even_for_an_operation_that_cannot_be_replayed():
    # The limiter rejects before the handler runs, so nothing happened.
    d = decide(operation=WRITE, attempt=1, max_retries=2, status=429, retry_after=60.0)
    assert (d.retry, d.wait, d.reason) == (True, 60.0, "rate_limit")


def test_retry_after_is_honoured_exactly_and_never_sooner():
    d = decide(operation=READ, attempt=1, max_retries=5, status=429, retry_after=60.0)
    assert d.wait == 60.0
    assert backoff(1, lambda: 1.0) < 60.0


def test_422_is_never_retried():
    assert decide(operation=READ, attempt=1, max_retries=5, status=422, retry_after=None).retry is False


def test_502_respects_the_operations_own_flag():
    assert decide(operation=WRITE, attempt=1, max_retries=5, status=502, retry_after=None).retry is False
    assert decide(operation=READ, attempt=1, max_retries=5, status=502, retry_after=None).retry is True


def test_retry_after_parses_seconds_and_http_dates():
    assert parse_retry_after("60") == 60.0
    assert parse_retry_after(None) is None
    assert parse_retry_after("not a date") is None
    assert parse_retry_after("Thu, 01 Jan 2026 00:00:30 GMT", now=1767225600.0) == 30.0


def test_backoff_is_capped_at_eight_seconds():
    assert backoff(99, lambda: 1.0) == 8.0


def test_retries_a_502_then_succeeds(fake):
    seen = []
    f = fake([Reply(502, {"error": {"code": "internal_error", "message": "x"}}, headers={"retry-after": "0"}), envelope([])])
    with f.client(max_retries=2, on_retry=seen.append) as rr:
        rr.sites.list()
    assert len(f.calls) == 2
    assert len(seen) == 1


def test_gives_up_rather_than_stalling_for_a_minute(fake):
    f = fake([Reply(429, {"error": {"code": "rate_limited", "message": "slow down"}}, headers={"retry-after": "60", "x-ratelimit-limit": "120"})])
    with f.client(max_retries=5, max_retry_wait=0.1) as rr, pytest.raises(RateLimitError) as excinfo:
        rr.sites.list()
    assert excinfo.value.retry_after_seconds == 60.0
    assert excinfo.value.limit == "120"
    assert len(f.calls) == 1


def test_a_validation_failure_is_not_retried(fake):
    f = fake([Reply(422, {"error": {"code": "validation_failed", "message": "no"}})])
    with f.client(max_retries=3) as rr, pytest.raises(ValidationError):
        rr.sites.list()
    assert len(f.calls) == 1


def test_every_attempts_request_id_is_reported(fake):
    # cf-ray changes per attempt, so one id does not identify a logical call.
    f = fake([
        Reply(503, {"error": {"code": "internal_error", "message": "x"}, "request_id": "ray1"}, headers={"retry-after": "0"}),
        Reply(503, {"error": {"code": "internal_error", "message": "x"}, "request_id": "ray2"}, headers={"retry-after": "0"}),
    ])
    with f.client(max_retries=1, max_retry_wait=1.0) as rr, pytest.raises(Exception) as excinfo:
        rr.sites.list()
    assert excinfo.value.attempt_request_ids == ["ray1", "ray2"]
