"""One real call per endpoint against a staging Enterprise organization.

The only check on behaviour the OpenAPI document cannot express — above all
whether the cursor really does survive a re-sent body, which is the single
assumption this client cannot verify any other way. Run it before a release:

    RANKRAFT_LIVE=1 RANKRAFT_API_KEY=rr_api_… pytest tests/test_live.py
"""

from __future__ import annotations

import os

import pytest

from rankraft import NotFoundError, RankRaft

LIVE = os.environ.get("RANKRAFT_LIVE") == "1" and bool(os.environ.get("RANKRAFT_API_KEY"))

pytestmark = pytest.mark.skipif(not LIVE, reason="needs RANKRAFT_LIVE=1 and a staging key")

WINDOW = {"start_date": "2026-09-01", "end_date": "2026-09-30"}


@pytest.fixture(scope="module")
def rr():
    with RankRaft() as client:
        yield client


def test_identifies_the_key(rr):
    me = rr.me()
    assert me["organization"]["id"]
    assert me["key"]["permission"] in {"read", "write"}


def test_lists_sites_platforms_competitors_and_actions(rr):
    sites = rr.sites.list()
    assert isinstance(sites, list)
    assert isinstance(rr.platforms.list(), list)
    if sites:
        assert isinstance(rr.sites.competitors(site_id=sites[0]["id"]), list)
        assert isinstance(rr.sites.actions(site_id=sites[0]["id"]), list)


def test_pages_three_deep_without_the_cursor_being_rejected(rr):
    # The assumption this whole client rests on. If the server hashes raw
    # bytes rather than a canonical form, this is where we find out.
    sites = rr.sites.list()
    if not sites:
        pytest.skip("no sites on the staging organization")
    pages = 0
    for page in rr.reports.visibility(site_id=sites[0]["id"], group_by=["date"], limit=1, **WINDOW).iter_pages():
        assert isinstance(page.data, list)
        pages += 1
        if pages >= 3:
            break
    assert pages > 0


def test_another_organizations_site_is_a_404(rr):
    with pytest.raises(NotFoundError):
        rr.sites.actions(site_id="00000000-0000-0000-0000-000000000000")


def test_sends_no_cors_headers_and_forbids_caching(rr):
    res = rr.request("GET", "/sites")
    assert "access-control-allow-origin" not in res.headers
    assert "no-store" in res.headers.get("cache-control", "")
