from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from ..types import ActionItem, Competitor, Site

if TYPE_CHECKING:  # pragma: no cover
    from ..client import RankRaft

# Declared out here because the `list` method below shadows the builtin inside
# the class body, which would make `list[Site]` resolve to the method.
SiteList = list[Site]
CompetitorList = list[Competitor]
ActionItemList = list[ActionItem]


class SitesResource:
    def __init__(self, client: RankRaft) -> None:
        self._client = client

    def list(self) -> SiteList:
        """Every site (project) in the organization the key belongs to."""
        return self._client._call("list_sites").data  # type: ignore[no-any-return]

    def get(self, *, site_id: str) -> Site:
        """One site.

        A site id belonging to another organization returns 404, never 403
        - the API refuses to confirm that an id exists. ``NotFoundError`` here
        means "no such site in this organization", not "no such site".
        """
        return self._client._call("get_site", path_params={"site_id": site_id}).data  # type: ignore[no-any-return]

    def competitors(self, *, site_id: str) -> CompetitorList:
        """Brands the site is compared against. Only ``confirmed`` ones count in leaderboards."""
        return self._client._call("list_competitors", path_params={"site_id": site_id}).data  # type: ignore[no-any-return]

    def actions(self, *, site_id: str, status: Literal["open", "done", "all"] | None = None) -> ActionItemList:
        """Stored Action Center cards. Read-only: this never regenerates them."""
        return self._client._call(  # type: ignore[no-any-return]
            "list_actions", path_params={"site_id": site_id}, params={"status": status}
        ).data
