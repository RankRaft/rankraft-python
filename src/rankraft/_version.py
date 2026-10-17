"""Kept in step with pyproject.toml by scripts/check_version.py, which the
release workflow runs before it publishes. The same fact in two files is only
safe when something asserts they agree."""

VERSION = "0.1.0"

#: The spec version this client was written against. Sent in the User-Agent.
SPEC_VERSION = "1.0.0"
