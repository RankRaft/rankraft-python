"""The SDK against the published contract.

The only thing standing between a hand-written client and silent drift. It
catches the failure mode that matters most - the API grows an endpoint and
nobody here ever learns.

``spec/openapi.json`` is vendored by ``scripts/sync_spec.py`` and refreshed by
a daily workflow that opens a PR on any change. Until the API Worker ships
there is nothing to fetch, so this skips - loudly, never silently.

The Node SDK runs the same comparison against the same document, which is what
keeps the two clients in step with each other without a cross-language test.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from rankraft import ERROR_CODE_CLASSES, OPERATIONS

SPEC = Path(__file__).resolve().parent.parent / "spec" / "openapi.json"

pytestmark = pytest.mark.skipif(not SPEC.exists(), reason="spec/openapi.json has not been vendored yet")


def _spec() -> dict:
    return json.loads(SPEC.read_text())


def _norm(path: str) -> str:
    # The Worker may mount routes with or without the /v1 prefix depending on
    # how the base path is declared; compare on the suffix either way.
    return re.sub(r"^/v1", "", path)


def _spec_operations(doc: dict) -> set[str]:
    out = set()
    for path, item in (doc.get("paths") or {}).items():
        for method in item:
            if method.lower() in {"get", "post", "patch", "put", "delete"}:
                out.add(f"{method.upper()} {_norm(path)}")
    return out


def _sdk_operations() -> set[str]:
    return {f"{op.method} {_norm(op.path)}" for op in OPERATIONS.values()}


def test_models_every_endpoint_the_api_publishes():
    missing = sorted(_spec_operations(_spec()) - _sdk_operations())
    assert not missing, f"the API has endpoints this SDK does not model: {missing}"


def test_models_no_endpoint_the_api_does_not_publish():
    extra = sorted(_sdk_operations() - _spec_operations(_spec()))
    assert not extra, f"this SDK models endpoints the API does not publish: {extra}"


def test_knows_every_error_code_the_api_can_return():
    schemas = (_spec().get("components") or {}).get("schemas") or {}
    schema = schemas.get("Error") or schemas.get("ApiError") or {}
    codes = ((schema.get("properties") or {}).get("code") or {}).get("enum")
    if not codes:
        pytest.skip("the spec does not enumerate error codes")
    unknown = sorted(c for c in codes if c not in ERROR_CODE_CLASSES)
    assert not unknown, f"error codes with no mapped class: {unknown}"
