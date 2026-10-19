<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset=".github/brand/rankraft-mark-dark-bg.svg">
    <img src=".github/brand/rankraft-mark-light-bg.svg" alt="RankRaft AI" width="72" height="72">
  </picture>
</p>

<h1 align="center">rankraft</h1>

<p align="center">Official Python client for the <a href="https://rankraft.ai">RankRaft AI</a> API - how AI answer engines and AI crawlers see your brand.</p>

<p align="center">
  <a href="https://rankraft.ai"><b>rankraft.ai</b></a> &nbsp;·&nbsp;
  <a href="https://docs.rankraft.ai">Docs</a> &nbsp;·&nbsp;
  <a href="https://app.rankraft.ai">Dashboard</a> &nbsp;·&nbsp;
  <a href="https://docs.rankraft.ai/api-reference/introduction">API reference</a>
</p>

```bash
pip install rankraft-py
pip install 'rankraft-py[pandas]'   # adds .to_pandas()
```

The API is **Enterprise-only**. Create a key in the dashboard under
**Settings → API**; it is shown once.

## Quick start

```python
from datetime import date
from rankraft import RankRaft, F

with RankRaft() as rr:                       # reads RANKRAFT_API_KEY
    site = rr.sites.list()[0]                # or rr.sites.get(site_id=...)

    page = rr.reports.visibility(
        site_id=site["id"],
        start_date=date(2026, 9, 1),
        end_date=date(2026, 9, 30),
        group_by=["platform"],
        metrics=["visibility_score", "mention_rate", "citation_rate"],
        filter=F("platform").in_(["chatgpt", "ai_mode"]) & ~F("category").is_("Brand"),
    )

    print(page.info["total_results"])
    df = page.to_pandas()
```

Numbers here equal the numbers on your dashboard by construction - both are
scored by the same package, not by two implementations of the same formula.

Every parameter is keyword-only. A nine-argument report call taken positionally
is a bug factory, and keyword-only means adding a field is never a breaking
change.

## Pagination

```python
page = rr.reports.citations(site_id=..., start_date=..., end_date=...)

for row in page:                     # this page only - no hidden network I/O
    ...

for row in page.auto_paging():       # every row, every page
    warehouse.write(row)

for p in page.iter_pages():          # page at a time
    ...

rows = page.all()                    # collect everything
df = page.to_pandas(all_pages=True)
```

`__iter__` stops at the end of the page on purpose. A bare `for row in page`
silently fetching more pages inside a notebook cell is a surprise; the method
that crosses a page boundary says so in its name.

The cursor carries a fingerprint of the query that produced it (every field
except `cursor` and `limit`, canonicalised). The client freezes the body it
sent on page one and re-sends it with only `cursor` substituted, so the
fingerprint always matches. Change the filter, range, grouping or metrics
between pages and the API answers `InvalidCursorError` - start again without a
cursor. `limit` may change between pages.

### `to_pandas()`

`pd.DataFrame(page.data)` is one line shorter and subtly wrong: dates arrive as
object strings, sparse metrics as `object`, and dimension columns are not
categorical. `to_pandas()` sets UTC datetimes, numeric metrics and categorical
dimensions, which is the reason it exists.

## Errors

```python
from rankraft import RateLimitError, ValidationError, PlanRequiredError

try:
    rr.reports.visibility(...)
except RateLimitError as err:
    print(err.retry_after_seconds)
except ValidationError as err:
    print(err.issues)
except PlanRequiredError:
    print("needs an Enterprise plan")
```

Every `APIError` carries `status`, `code`, `details`, `request_id` and
`attempt_request_ids`. The request id is in the message too, so a pasted
traceback is enough for support.

| Class | Status · `code` |
|---|---|
| `BadRequestError` | 400 · `invalid_json`, `api_key_in_url` |
| `InvalidCursorError` | 400 · `invalid_cursor` - the query changed between pages |
| `AuthenticationError` | 401 · `invalid_api_key` - missing, unknown, revoked or expired; deliberately one message |
| `PlanRequiredError` | 403 · `plan_required` - not on a live Enterprise plan |
| `PermissionDeniedError` | 403 · `insufficient_permission` - a read key tried to write |
| `NotFoundError` | 404 · `not_found` - no such site **in this organization** (never 403, so ids can't be enumerated) |
| `ConflictError` | 409 · `site_not_set_up` - finish the site's brand profile in the dashboard first |
| `PayloadTooLargeError` | 413 · `payload_too_large` - bodies are capped at 256 KB |
| `ValidationError` | 422 · `invalid_request`, `invalid_filter`, `invalid_date_range`, `invalid_timezone`, `invalid_sort` - `err.issues` has the detail |
| `PromptLimitError` | 422 · `prompt_limit_reached` - `err.remaining` and `err.limit` |
| `RateLimitError` | 429 · `rate_limited` - `err.retry_after_seconds` |
| `InternalServerError` | 5xx · `internal_error` |

A code this client does not know falls back to the class for its status, so a
new server-side code never crashes a pinned install.

## Retries

On by default, two attempts after the first.

- A **429 is always retried**, because the limiter rejects before the handler
  runs, so nothing happened. `Retry-After` is honoured **exactly** - the window
  has no remaining-count header, so retrying early is guaranteed to fail and
  spends another request from your budget.
- Everything else is retried only when the operation is safe to replay. That is
  a per-operation property, not an HTTP-method guess: the report endpoints are
  POSTs that read.
- `max_retry_wait` (default 70 s) bounds the **total** time the client may
  spend asleep inside one call, so a `Retry-After: 60` cannot silently stall
  you for two minutes. Past that it raises `RateLimitError` and you decide.

```python
rr = RankRaft(max_retries=2, max_retry_wait=70.0, on_retry=lambda info: log.warning(info))
```

## Writing prompts

Prompts are the only thing this API writes, and it cannot delete them - deleting cascades away answer history and any Action Center baseline that
targeted the prompt.

```python
result = rr.prompts.create(
    site_id=site_id,
    prompts=[{"text": "best mixed pickle brand", "category": "Discovery"}],
    dry_run=True,    # see what would happen, change nothing
)
result["created"], result["existing"]   # new vs already-present (returned, not duplicated)

rr.prompts.set_status(site_id=site_id, prompt_ids=["pr_1"], status="disabled")
```

Up to 100 prompts per call. A request that would exceed the plan's
active-prompt cap is refused whole with `PromptLimitError`.

Text that already exists returns the existing prompt rather than a duplicate.
Prompt text is immutable: changing it would make the history either side of the
edit incomparable while still looking like one series.

## Filters

Pass a plain dict, or build one with `&`, `|` and `~`:

```python
from rankraft import F

F("platform").in_(["chatgpt", "ai_mode"]) & ~F("category").is_("Brand")
F("prompt").contains("pricing") | F("bot_type").not_is("index")
```

Operators: `is_`, `not_is`, `in_`, `not_in`, `contains`, `not_contains` - all
case-insensitive. Values are strings on the wire; the builder stringifies
numbers and booleans for you (`F("verified").is_(True)` sends `"true"`).
`a & b & c` flattens into one `and` node rather than nesting three deep.

Which fields a report accepts: answer reports take `platform`, `prompt` (id
or text) and `category`; citations add `domain`, `owner` and `source_kind`;
traffic reports take `bot_name`, `bot_provider`, `bot_type`, `verified`,
`path`, `page_type` and `referral_source`.

The builder checks grammar and nothing else. Depth, list length, `limit` and
date spans are the server's limits and are not duplicated here - a copy in the
client is a copy that goes stale, and the 422 carries the real number.

## Dates

Inclusive `YYYY-MM-DD` in **UTC**, matching RankRaft AI's scan days. Pass a string
or a `datetime.date`. A `datetime` is reduced to its UTC calendar day. Traffic
reports (`bots`, `referrals`) also accept an IANA `timezone`.

## Notes

- Requires **Python 3.10+**. One runtime dependency: `httpx`.
- Synchronous only in v1. An async client is additive and will share this
  transport; nothing here will need rewriting.
- Server-side use. `api.rankraft.ai` sends no CORS headers and a RankRaft AI key
  reads every site in your organization - keep it out of anything a browser
  can read.

## The MCP server

If what you want is to ask questions in Claude, ChatGPT or Cursor rather than
write code, RankRaft AI also serves an MCP server at `mcp.rankraft.ai`. It is
OAuth-based (sign in with your dashboard account), available on every paid
plan, and read-only. This client is for the REST API, which is Enterprise-only
and can also manage prompts.

## Contributing

```bash
python -m venv .venv && .venv/bin/pip install -e '.[pandas]' pytest mypy ruff
.venv/bin/pytest
.venv/bin/mypy
.venv/bin/ruff check .
.venv/bin/python scripts/sync_spec.py    # refresh spec/openapi.json
```

`tests/test_conformance.py` compares this client against the vendored
`spec/openapi.json` and is the thing that catches an endpoint we have not
modelled. Refresh the spec with `scripts/sync_spec.py`.

One trap: do not run `python` from inside `src/rankraft/` - our `types.py`
shadows the standard library's `types` module there and the interpreter fails
to start. Run from the repo root.

## Licence

MIT

---

RankRaft AI - [rankraft.ai](https://rankraft.ai) · [docs.rankraft.ai](https://docs.rankraft.ai) · hello@rankraft.ai
