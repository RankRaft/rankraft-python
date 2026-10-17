"""Request and response shapes, written from the API's own zod schemas
(apps/api/src/routes/*) and kept honest by tests/test_conformance.py.

``total=False`` wherever the row shape is chosen at call time by ``group_by``
and ``metrics``: a static type cannot know which columns a given call asked
for. TypedDict rather than pydantic on purpose — pydantic as a runtime
dependency on every Airflow worker is a real cost, and a second set of models
is a second thing to keep in step with the API.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Literal, TypedDict

#: Inclusive ``YYYY-MM-DD`` in UTC. A ``date`` is serialised with isoformat().
DateInput = str | date

Platform = str  # open on purpose: a new engine must not break a pinned install
PromptCategory = str
ApiKeyPermission = Literal["read", "write"]
SortDir = Literal["asc", "desc"]


class Sort(TypedDict, total=False):
    field: str
    dir: SortDir


class PromptRef(TypedDict):
    id: str
    text: str


# ---- Discovery -------------------------------------------------------------


class KeyInfo(TypedDict):
    id: str
    name: str
    permission: ApiKeyPermission
    expires_at: str


class OrganizationInfo(TypedDict):
    id: str
    name: str
    plan: str


class RateLimits(TypedDict):
    requests_per_minute: int
    writes_per_minute: int


class Me(TypedDict):
    key: KeyInfo
    organization: OrganizationInfo
    rate_limits: RateLimits


class LastScan(TypedDict):
    date: str
    status: str


class Site(TypedDict):
    id: str
    name: str
    domain: str
    created_at: str
    platforms: list[Platform]
    last_answer_scan: LastScan | None


class Competitor(TypedDict):
    id: str
    name: str
    domains: list[str]
    confirmed: bool
    source: str


class PlatformInfo(TypedDict):
    id: Platform
    name: str
    available: bool


class ActionOutcome(TypedDict):
    marked_done_at: str
    result_due: str
    verdict: str | None
    summary: str | None


class ActionItem(TypedDict):
    id: str
    title: str
    why: str
    detail: str
    category: str
    impact: Literal["High", "Medium", "Low"]
    effort: str
    target_metric: Literal["mention", "citation", "coverage"]
    kind: Literal["one_off", "ongoing"]
    cadence: str | None
    period: str | None
    status: Literal["open", "done", "dismissed"]
    target_prompts: list[PromptRef]
    target_platforms: list[Platform]
    target_url: str | None
    created_at: str
    outcome: ActionOutcome | None


# ---- Prompts ---------------------------------------------------------------


class Prompt(TypedDict):
    id: str
    text: str
    category: PromptCategory
    market: str | None
    status: Literal["active", "disabled"]
    created_at: str
    updated_at: str


class NewPrompt(TypedDict, total=False):
    text: str
    category: PromptCategory
    market: str | None
    active: bool


class PromptPatch(TypedDict, total=False):
    id: str
    category: PromptCategory
    market: str | None


class CreatePromptsResult(TypedDict):
    dry_run: bool
    created: int
    existing: int
    #: In a dry run, would-be-created prompts have no id or timestamps yet.
    data: list[dict[str, Any]]


class UpdatePromptsResult(TypedDict):
    dry_run: bool
    not_found: list[str]
    data: list[Prompt]


class SetPromptStatusResult(TypedDict):
    dry_run: bool
    changed: list[str]
    unchanged: list[str]
    not_found: list[str]


# ---- Reports ---------------------------------------------------------------

VisibilityMetric = Literal[
    "visibility_score",
    "mention_rate",
    "citation_rate",
    "prompt_coverage",
    "average_position",
    "share_of_voice",
    "answers",
]
AnswerDimension = Literal["date", "platform", "prompt", "category"]
CitationMetric = Literal["answers", "citations", "citation_share"]
AnswerField = Literal[
    "prompt", "platform", "date", "text", "brand_mentioned", "brand_position", "sentiment", "mentions", "citations"
]


class Brand(TypedDict):
    name: str
    owned: bool


class VisibilityRow(TypedDict, total=False):
    date: str
    platform: Platform
    prompt: PromptRef
    category: PromptCategory
    brand: Brand
    rank: int
    visibility_score: float
    mention_rate: float
    citation_rate: float
    prompt_coverage: float
    average_position: float | None
    share_of_voice: float
    answers: int


class CitationRow(TypedDict, total=False):
    date: str
    platform: Platform
    prompt: PromptRef
    domain: str
    page: str
    owner: Literal["own", "competitor", "third_party"]
    source_kind: str
    rank: int
    answers: int
    citations: int
    citation_share: float


class SentimentRow(TypedDict, total=False):
    date: str
    platform: Platform
    prompt: PromptRef
    category: PromptCategory
    positive: float
    neutral: float
    negative: float
    answers_mentioning: int
    answers: int


class AnswerCitation(TypedDict):
    url: str
    domain: str
    title: str | None
    position: int
    own_site: bool


class AnswerRow(TypedDict, total=False):
    id: str
    date: str
    platform: Platform
    prompt: PromptRef
    text: str
    brand_mentioned: bool
    brand_position: int | None
    sentiment: str | None
    mentions: list[str]
    citations: list[AnswerCitation]


# ---- Agent Analytics (traffic) -------------------------------------------

BotDimension = Literal["date", "hour", "bot_name", "bot_provider", "bot_type", "path", "page_type"]
BotMetric = Literal["hits", "pages", "verified_share", "error_hits", "last_visit"]
ReferralDimension = Literal["date", "hour", "referral_source", "path", "page_type"]
ReferralMetric = Literal["visits", "landing_pages", "last_visit"]


class BotRow(TypedDict, total=False):
    date: str
    hour: str
    bot_name: str | None
    bot_provider: str | None
    bot_type: str | None
    path: str
    page_type: str
    hits: int
    pages: int
    verified_share: float
    error_hits: int
    last_visit: str


class ReferralRow(TypedDict, total=False):
    date: str
    hour: str
    referral_source: str | None
    path: str
    page_type: str
    visits: int
    landing_pages: int
    last_visit: str
