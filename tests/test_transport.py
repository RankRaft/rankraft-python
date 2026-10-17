from __future__ import annotations

import json

import pytest

from rankraft import (
    AuthenticationError,
    ConfigurationError,
    ConflictError,
    InvalidCursorError,
    NotFoundError,
    PlanRequiredError,
    PromptLimitError,
    RankRaft,
    ValidationError,
)

from .conftest import KEY, Reply, envelope


def test_key_is_a_header_and_never_in_the_url(fake):
    f = fake([envelope([{"id": "s1"}])])
    with f.client() as rr:
        rr.sites.list()
    call = f.calls[0]
    assert call.headers["x-api-key"] == KEY
    assert KEY not in call.url
    assert call.url == "https://api.rankraft.ai/v1/sites"


def test_unwraps_the_envelope(fake):
    f = fake([envelope([{"id": "s1", "name": "Acme"}], {"count": 1})])
    with f.client() as rr:
        assert rr.sites.list() == [{"id": "s1", "name": "Acme"}]


def test_path_parameters_are_encoded(fake):
    f = fake([envelope([])])
    with f.client() as rr:
        rr.sites.competitors(site_id="a/b")
    assert f.calls[0].url == "https://api.rankraft.ai/v1/sites/a%2Fb/competitors"


def test_error_code_decides_the_class_not_the_status(fake):
    # 403 is two different failures. Only the code tells them apart.
    f = fake([Reply(403, {"error": {"code": "plan_required", "message": "Enterprise only"}, "request_id": "r1"})])
    with f.client() as rr, pytest.raises(PlanRequiredError):
        rr.sites.list()


def test_unknown_code_falls_back_to_the_status(fake):
    f = fake([Reply(401, {"error": {"code": "some_future_code", "message": "nope"}})])
    with f.client() as rr, pytest.raises(AuthenticationError):
        rr.sites.list()


def test_request_id_is_in_the_message(fake):
    f = fake([Reply(422, {"error": {"code": "validation_failed", "message": "bad limit", "details": ["limit"]}, "request_id": "req_abc"})])
    with f.client() as rr, pytest.raises(ValidationError) as excinfo:
        rr.sites.list()
    assert "req_abc" in str(excinfo.value)
    assert excinfo.value.issues == ["limit"]


def test_request_id_falls_back_to_the_header_when_there_is_no_json(fake):
    # A Cloudflare-level 502 returns HTML. That is exactly when the id matters.
    f = fake([Reply(502, text="<html>bad gateway</html>", headers={"cf-ray": "ray123"})])
    with f.client() as rr, pytest.raises(Exception) as excinfo:
        rr.sites.list()
    assert "ray123" in str(excinfo.value)


def test_another_organizations_site_is_a_404_not_a_403(fake):
    f = fake([Reply(404, {"error": {"code": "not_found", "message": "no such site"}})])
    with f.client() as rr, pytest.raises(NotFoundError):
        rr.sites.actions(site_id="someone-elses")


def test_the_public_spec_route_gets_no_key(fake):
    f = fake([Reply(200, {"openapi": "3.1.0", "paths": {}})])
    with f.client() as rr:
        spec = rr.openapi()
    assert "x-api-key" not in f.calls[0].headers
    assert spec["openapi"] == "3.1.0"


def test_fetches_one_site_and_sends_the_actions_status_as_a_query(fake):
    f = fake([envelope({"id": "s1", "name": "Acme"}), envelope([])])
    with f.client() as rr:
        assert rr.sites.get(site_id="s1") == {"id": "s1", "name": "Acme"}
        rr.sites.actions(site_id="s1", status="all")
    assert f.calls[1].url == "https://api.rankraft.ai/v1/sites/s1/actions?status=all"


def test_prompt_writes_return_the_whole_body(fake):
    # `{dry_run, created, existing, data}` - unwrapping to `data` alone would
    # silently drop the counts the caller asked for.
    f = fake([Reply(200, {"dry_run": True, "created": 1, "existing": 0, "data": [{"text": "x", "status": "active"}]})])
    with f.client() as rr:
        result = rr.prompts.create(site_id="s1", prompts=[{"text": "x"}], dry_run=True)
    assert result == {"dry_run": True, "created": 1, "existing": 0, "data": [{"text": "x", "status": "active"}]}
    assert json.loads(f.calls[0].body) == {"prompts": [{"text": "x"}], "dry_run": True}


@pytest.mark.parametrize(
    ("status", "code", "cls"),
    [
        (400, "invalid_cursor", InvalidCursorError),
        (409, "site_not_set_up", ConflictError),
        (422, "invalid_filter", ValidationError),
        (422, "invalid_date_range", ValidationError),
        (422, "prompt_limit_reached", PromptLimitError),
    ],
)
def test_maps_every_code_the_api_actually_emits(fake, status, code, cls):
    f = fake([Reply(status, {"error": {"code": code, "message": "m", "details": {"remaining": 3, "limit": 20}}, "request_id": "r"})])
    with f.client() as rr, pytest.raises(cls) as excinfo:
        rr.sites.list()
    if cls is PromptLimitError:
        assert excinfo.value.remaining == 3
        assert excinfo.value.limit == 20


def test_refuses_a_site_key_where_an_api_key_belongs():
    # The common paste mistake, which would otherwise surface as a bare 401.
    with pytest.raises(ConfigurationError):
        RankRaft(api_key="rr_live_abcdefghijklmnop")


def test_a_datetime_is_reduced_to_its_utc_day(fake):
    from datetime import datetime, timedelta, timezone

    f = fake([envelope([], {"next_cursor": None})])
    with f.client() as rr:
        # 23:30 on the 1st in UTC+5 is 18:30 on the 1st in UTC - still the 1st.
        rr.reports.sentiment(
            site_id="s1",
            start_date=datetime(2026, 9, 1, 23, 30, tzinfo=timezone(timedelta(hours=5))),
            end_date=datetime(2026, 9, 2, 1, 0, tzinfo=timezone(timedelta(hours=5))),  # 20:00 UTC on the 1st
        )
    body = json.loads(f.calls[0].body)
    assert (body["start_date"], body["end_date"]) == ("2026-09-01", "2026-09-01")
