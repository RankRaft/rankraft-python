"""The operation table.

Load-bearing code, not documentation. It drives method dispatch, the retry
decision, whether a response paginates, and the conformance test that compares
this SDK against the published OpenAPI document. A hand-written client only
stays honest if exactly one place enumerates what the API can do.

The TypeScript SDK carries the identical table. Both are checked against the
same spec, which is what keeps the two clients in step with each other.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Method = Literal["GET", "POST", "PATCH"]


@dataclass(frozen=True)
class Operation:
    method: Method
    #: Route template with ``{site_id}``-style placeholders. Never an expanded URL.
    path: str
    #: Whether replaying this request is safe.
    #:
    #: Per-operation and never inferred from the HTTP method. Six of the report
    #: endpoints are POST but are pure reads, so a method-based policy would be
    #: wrong in both directions: it would refuse to retry a timed-out report and
    #: would happily replay a genuine mutation. The first operation that is
    #: unsafe to replay sets this False and nobody has to remember.
    retryable: bool
    #: Whether the response carries ``info.next_cursor``.
    paginates: bool
    #: False only for the public spec route, which must not receive a key.
    authenticated: bool = True


OPERATIONS: dict[str, Operation] = {
    # Discovery
    "get_me": Operation("GET", "/me", True, False),
    "list_sites": Operation("GET", "/sites", True, False),
    "get_site": Operation("GET", "/sites/{site_id}", True, False),
    "list_competitors": Operation("GET", "/sites/{site_id}/competitors", True, False),
    "list_platforms": Operation("GET", "/platforms", True, False),
    "list_actions": Operation("GET", "/sites/{site_id}/actions", True, False),
    # Prompts
    "list_prompts": Operation("GET", "/sites/{site_id}/prompts", True, True),
    # Retryable because text that already exists returns the existing prompt,
    # so a replay cannot create a duplicate.
    "create_prompts": Operation("POST", "/sites/{site_id}/prompts", True, False),
    # Retryable because applying the same patch twice yields the same state.
    "update_prompts": Operation("PATCH", "/sites/{site_id}/prompts", True, False),
    "set_prompt_status": Operation("PATCH", "/sites/{site_id}/prompts/status", True, False),
    # Reports — POST bodies, but pure reads
    "report_visibility": Operation("POST", "/reports/visibility", True, True),
    "report_citations": Operation("POST", "/reports/citations", True, True),
    "report_sentiment": Operation("POST", "/reports/sentiment", True, True),
    "report_bots": Operation("POST", "/reports/bots", True, True),
    "report_referrals": Operation("POST", "/reports/referrals", True, True),
    "query_answers": Operation("POST", "/answers", True, True),
    # Spec
    "get_openapi": Operation("GET", "/openapi.json", True, False, authenticated=False),
}


def expand_path(template: str, params: dict[str, str] | None = None) -> str:
    """Fill a route template. Values are percent-encoded; a missing one raises."""
    from urllib.parse import quote

    params = params or {}
    out = template
    for key, value in params.items():
        out = out.replace("{" + key + "}", quote(str(value), safe=""))
    if "{" in out:
        missing = out[out.index("{") + 1 : out.index("}")]
        raise ValueError(f"rankraft: missing path parameter {missing!r} for {template}")
    return out
