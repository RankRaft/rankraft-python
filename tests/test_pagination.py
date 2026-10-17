from __future__ import annotations

import json

import pytest

from rankraft import F, PaginationError, serialize_with_cursor

from .conftest import envelope

PARAMS = dict(
    site_id="st_1",
    start_date="2026-09-01",
    end_date="2026-09-30",
    group_by=["platform"],
    metrics=["visibility_score"],
    filter=F("platform").in_(["chatgpt", "ai_mode"]) & ~F("category").is_("Brand"),
)


def _strip_cursor(body: str) -> str:
    parsed = json.loads(body)
    parsed.pop("cursor", None)
    return json.dumps(parsed, separators=(",", ":"))


def test_resends_a_byte_identical_body_with_only_the_cursor_appended(fake):
    # The server binds the cursor to a hash of the body. Any re-serialisation
    # that reorders keys or re-applies defaults would 400 on page two.
    f = fake([
        envelope([{"visibility_score": 41}], {"next_cursor": "c2"}),
        envelope([{"visibility_score": 42}], {"next_cursor": "c3"}),
        envelope([{"visibility_score": 43}], {"next_cursor": None}),
    ])
    with f.client() as rr:
        rows = list(rr.reports.visibility(**PARAMS).auto_paging())

    assert len(rows) == 3
    assert len(f.calls) == 3
    first = _strip_cursor(f.calls[0].body)
    assert _strip_cursor(f.calls[1].body) == first
    assert _strip_cursor(f.calls[2].body) == first
    assert json.loads(f.calls[1].body)["cursor"] == "c2"
    assert json.loads(f.calls[2].body)["cursor"] == "c3"


def test_never_rebuilds_the_body_from_the_echoed_filter(fake):
    # The server echoes a *normalised* filter. Round-tripping it is the exact
    # bug that produces a 400 on page two.
    f = fake([
        envelope([{}], {"next_cursor": "c2", "filter": {"and": [{"field": "platform", "op": "in", "value": ["CHATGPT"]}]}}),
        envelope([{}], {"next_cursor": None}),
    ])
    with f.client() as rr:
        rr.reports.visibility(**PARAMS).all()
    assert '"chatgpt"' in f.calls[1].body
    assert "CHATGPT" not in f.calls[1].body


def test_refuses_to_loop_on_a_repeated_cursor(fake):
    f = fake([envelope([{}], {"next_cursor": "same"}), envelope([{}], {"next_cursor": "same"})])
    with f.client() as rr, pytest.raises(PaginationError):
        rr.reports.visibility(**PARAMS).all()


def test_iterating_a_page_does_not_touch_the_network(fake):
    # A bare `for row in page` fetching more pages inside a notebook cell is
    # the surprise this asymmetry exists to avoid.
    f = fake([envelope([{"a": 1}], {"next_cursor": "c2"}), envelope([{"a": 2}], {"next_cursor": None})])
    with f.client() as rr:
        page = rr.reports.citations(**PARAMS)
        assert list(page) == [{"a": 1}]
        assert len(f.calls) == 1
        assert list(page.auto_paging()) == [{"a": 1}, {"a": 2}]
        assert len(f.calls) == 2


def test_paginates_a_get_through_the_query_string(fake):
    f = fake([envelope([{"id": "p1"}], {"next_cursor": "c2"}), envelope([{"id": "p2"}], {"next_cursor": None})])
    with f.client() as rr:
        prompts = rr.prompts.list(site_id="st_1", status="active").all()
    assert len(prompts) == 2
    assert "status=active" in f.calls[0].url
    assert "cursor=" not in f.calls[0].url
    assert "cursor=c2" in f.calls[1].url


def test_cursor_is_dropped_from_the_frozen_body_and_appended_last():
    assert serialize_with_cursor({"b": 2, "cursor": "stale", "a": 1}, "fresh") == '{"b":2,"a":1,"cursor":"fresh"}'
    assert serialize_with_cursor({"b": 2, "a": 1}) == '{"b":2,"a":1}'


def test_to_pandas_sets_real_dtypes(fake):
    pd = pytest.importorskip("pandas")
    f = fake([envelope([{"date": "2026-09-01", "platform": "chatgpt", "visibility_score": 41}], {"next_cursor": None})])
    with f.client() as rr:
        frame = rr.reports.visibility(**PARAMS).to_pandas()
    assert pd.api.types.is_datetime64_any_dtype(frame["date"])
    assert isinstance(frame["platform"].dtype, pd.CategoricalDtype)
    assert pd.api.types.is_numeric_dtype(frame["visibility_score"])
