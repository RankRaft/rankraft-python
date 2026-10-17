from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import httpx
import pytest

from rankraft import RankRaft

KEY = "rr_api_TESTKEY_do_not_log_me_0123456789"


@dataclass
class Recorded:
    method: str
    url: str
    headers: dict[str, str]
    body: str | None


@dataclass
class Reply:
    status: int = 200
    body: Any = None
    text: str | None = None
    headers: dict[str, str] = field(default_factory=dict)


def envelope(data: Any, info: dict[str, Any] | None = None) -> Reply:
    return Reply(body={"info": info or {}, "data": data})


class Fake:
    """A transport that replays canned replies and records what was sent."""

    def __init__(self, replies: list[Reply]) -> None:
        self.replies = replies
        self.calls: list[Recorded] = []
        self._i = 0

    def handler(self, request: httpx.Request) -> httpx.Response:
        content = request.content.decode() if request.content else None
        self.calls.append(
            Recorded(
                method=request.method,
                url=str(request.url),
                headers={k.lower(): v for k, v in request.headers.items()},
                body=content,
            )
        )
        reply = self.replies[min(self._i, len(self.replies) - 1)]
        self._i += 1
        payload = reply.text if reply.text is not None else json.dumps(reply.body if reply.body is not None else {})
        return httpx.Response(
            reply.status,
            content=payload,
            headers={"content-type": "application/json", **reply.headers},
        )

    def client(self, **kwargs: Any) -> RankRaft:
        kwargs.setdefault("api_key", KEY)
        kwargs.setdefault("max_retries", 0)
        return RankRaft(transport=httpx.MockTransport(self.handler), **kwargs)


@pytest.fixture
def fake() -> Any:
    def make(replies: list[Reply]) -> Fake:
        return Fake(replies)

    return make


def pytest_report_header(config: pytest.Config) -> list[str]:
    """Say out loud what was not checked.

    A skipped conformance run means the SDK was not compared against the API
    contract at all. That must never be quiet - the same bargain the main repo
    strikes when php is missing and the plugin suite skips.
    """
    import os
    from pathlib import Path

    notes = []
    if not (Path(__file__).resolve().parent.parent / "spec" / "openapi.json").exists():
        notes.append(
            "WARNING conformance: spec/openapi.json is missing, so the SDK was NOT checked "
            "against the API contract. Run scripts/sync_spec.py once api.rankraft.ai is live."
        )
    if os.environ.get("RANKRAFT_LIVE") != "1" or not os.environ.get("RANKRAFT_API_KEY"):
        notes.append("WARNING live smoke suite skipped: set RANKRAFT_LIVE=1 and RANKRAFT_API_KEY.")
    return notes
