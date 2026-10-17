from __future__ import annotations

from typing import TYPE_CHECKING

from ..types import PlatformInfo

if TYPE_CHECKING:  # pragma: no cover
    from ..client import RankRaft

# See the note in sites.py: the `list` method shadows the builtin in class scope.
PlatformInfoList = list[PlatformInfo]


class PlatformsResource:
    def __init__(self, client: RankRaft) -> None:
        self._client = client

    def list(self) -> PlatformInfoList:
        """Engine ids and their display labels."""
        return self._client._call("list_platforms").data  # type: ignore[no-any-return]
