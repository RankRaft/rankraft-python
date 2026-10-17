#!/usr/bin/env python3
"""Vendor the published OpenAPI document into spec/openapi.json.

The SDK never fetches this at runtime - it is a test fixture, and the
conformance suite is the thing that reads it. Committing it means a PR diff
shows the API surface change, and the daily spec-sync workflow turns a change
nobody told us about into a pull request.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path

URL = os.environ.get("RANKRAFT_SPEC_URL", "https://api.rankraft.ai/v1/openapi.json")
OUT = Path(__file__).resolve().parent.parent / "spec" / "openapi.json"


def main() -> int:
    request = urllib.request.Request(URL, headers={"accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            spec = json.loads(response.read().decode())
    except Exception as exc:
        print(f"sync-spec: could not fetch {URL}: {exc}", file=sys.stderr)
        return 1

    if not isinstance(spec.get("openapi"), str) or not isinstance(spec.get("paths"), dict):
        print("sync-spec: that did not look like an OpenAPI document", file=sys.stderr)
        return 1

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(spec, indent=2) + "\n")
    version = (spec.get("info") or {}).get("version", "?")
    print(f"sync-spec: wrote {len(spec['paths'])} paths from {URL} (info.version={version})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
