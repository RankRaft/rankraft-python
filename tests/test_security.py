from __future__ import annotations

import json

import pytest

from rankraft import (
    APIError,
    AuthenticationError,
    ConfigurationError,
    NotFoundError,
    RankRaft,
    RateLimitError,
    ValidationError,
)

from .conftest import KEY, envelope

CLASSES = [APIError, AuthenticationError, NotFoundError, ValidationError, RateLimitError]


def test_the_key_appears_in_no_serialised_error():
    for cls in CLASSES:
        err = cls(
            status=401,
            code="invalid_api_key",
            message="nope",
            details={"note": "nothing here"},
            request_id="r1",
            headers={"retry-after": "60"},
        )
        assert KEY not in str(err)
        assert KEY not in repr(err)
        assert KEY not in json.dumps({"message": str(err), "details": err.details})


def test_the_key_appears_in_no_request_url_for_any_operation(fake):
    f = fake([envelope([])])
    with f.client() as rr:
        rr.sites.list()
        rr.platforms.list()
        rr.prompts.list(site_id="s1")
        rr.reports.visibility(site_id="s1", start_date="2026-01-01", end_date="2026-01-02")
    for call in f.calls:
        assert KEY not in call.url
        assert KEY not in (call.body or "")


@pytest.mark.parametrize(
    "bad",
    [
        "https://api.rankraft.ai/v1?api_key=x",
        "https://api.rankraft.ai/v1?token=x",
        "https://api.rankraft.ai/v1?key=x",
    ],
)
def test_refuses_a_base_url_carrying_a_credential(bad):
    # The API rejects a key in the query string with a 400 so that keys stay
    # out of access logs. This client will not smuggle one in via config.
    with pytest.raises(ConfigurationError):
        RankRaft(api_key=KEY, base_url=bad)


def test_allows_an_ordinary_base_url_query():
    RankRaft(api_key=KEY, base_url="https://api.rankraft.ai/v1?region=eu").close()


def test_will_not_construct_without_a_key(monkeypatch):
    monkeypatch.delenv("RANKRAFT_API_KEY", raising=False)
    with pytest.raises(ConfigurationError):
        RankRaft()
