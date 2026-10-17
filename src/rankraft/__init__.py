"""Official Python client for the RankRaft AI API.

Server-side only: ``api.rankraft.ai`` sends no CORS headers and a RankRaft AI key
reads every site in your organization.

    from rankraft import RankRaft, F

    with RankRaft() as rr:                       # reads RANKRAFT_API_KEY
        for row in rr.reports.visibility(
            site_id="…",
            start_date="2026-09-01",
            end_date="2026-09-30",
            group_by=["platform"],
            filter=F("platform").in_(["chatgpt", "ai_mode"]),
        ).auto_paging():
            print(row)
"""

from ._version import SPEC_VERSION, VERSION
from .client import DEFAULT_BASE_URL, KEY_PREFIX, RankRaft
from .errors import (
    ERROR_CODE_CLASSES,
    APIConnectionError,
    APIError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    ConfigurationError,
    ConflictError,
    InternalServerError,
    InvalidCursorError,
    NotFoundError,
    PaginationError,
    PayloadTooLargeError,
    PermissionDeniedError,
    PlanRequiredError,
    PromptLimitError,
    RankRaftError,
    RateLimitError,
    ValidationError,
)
from .filters import And, F, FilterGrammarError, Leaf, Node, Not, Or, to_filter, validate_filter
from .operations import OPERATIONS, Operation, expand_path
from .pagination import Page, serialize_with_cursor

__version__ = VERSION

__all__ = [
    "DEFAULT_BASE_URL",
    "ERROR_CODE_CLASSES",
    "KEY_PREFIX",
    "OPERATIONS",
    "SPEC_VERSION",
    "VERSION",
    "APIConnectionError",
    "APIError",
    "APITimeoutError",
    "And",
    "AuthenticationError",
    "BadRequestError",
    "ConfigurationError",
    "ConflictError",
    "F",
    "FilterGrammarError",
    "InternalServerError",
    "InvalidCursorError",
    "Leaf",
    "Node",
    "Not",
    "NotFoundError",
    "Operation",
    "Or",
    "Page",
    "PaginationError",
    "PayloadTooLargeError",
    "PermissionDeniedError",
    "PlanRequiredError",
    "PromptLimitError",
    "RankRaft",
    "RankRaftError",
    "RateLimitError",
    "ValidationError",
    "__version__",
    "expand_path",
    "serialize_with_cursor",
    "to_filter",
    "validate_filter",
]
