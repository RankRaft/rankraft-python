"""The filter tree, and a small builder for it.

Raw dicts are accepted everywhere a filter is - that is the escape hatch when
the API grows an operator before this client does, and it is what an LLM
driving an MCP server will produce. The builder exists for everyone else, and
uses ``&``, ``|`` and ``~`` because data teams already read that fluently from
pandas and SQLAlchemy.

It validates *grammar* and never *magnitude*. Depth, list length, limits and
date spans are the server's rules; duplicating them here would put the same
number in two places, and this copy is the one that would go stale. A caller
who exceeds one gets a 422 carrying the real figure.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

#: On the wire a value is a string or a list of strings, nothing else. The
#: builder also takes numbers and booleans and stringifies them (True →
#: "true"), because ``verified`` is a boolean column and ``F("verified").is_(True)``
#: is what people will write. A raw dict gets no such help: it must already be
#: what the server accepts.
FilterInput = str | int | float | bool
FilterScalar = str


def _wire(value: FilterInput) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)

_SCALAR_OPS = frozenset({"is", "not_is", "contains", "not_contains"})
_LIST_OPS = frozenset({"in", "not_in"})


class FilterGrammarError(ValueError):
    def __init__(self, message: str) -> None:
        super().__init__(f"rankraft: {message}")


class Node:
    """Base for every filter node. Combine with ``&``, ``|`` and ``~``."""

    def to_dict(self) -> dict[str, Any]:  # pragma: no cover - overridden
        raise NotImplementedError

    def __and__(self, other: Node) -> And:
        return And(self, other)

    def __or__(self, other: Node) -> Or:
        return Or(self, other)

    def __invert__(self) -> Not:
        return Not(self)

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.to_dict()!r})"


class Leaf(Node):
    def __init__(self, field: str, op: str, value: str | list[str]) -> None:
        self.field = field
        self.op = op
        self.value = value

    def to_dict(self) -> dict[str, Any]:
        # Fixed {field, op, value} order, never re-sorted: key order may be
        # load-bearing for the server's body-hash cursor.
        return {"field": self.field, "op": self.op, "value": self.value}


class _Group(Node):
    key = ""
    nodes: list[Node]

    def __init__(self, *nodes: Node) -> None:
        if not nodes:
            raise FilterGrammarError(f"{self.key}() needs at least one node")
        # Flatten same-kind children. `a & b & c` would otherwise nest three
        # deep and hit the server's depth limit for no reason - and/or are
        # associative, so flattening changes nothing but the shape.
        flat: list[Node] = []
        for node in nodes:
            if isinstance(node, type(self)):
                flat.extend(node.nodes)
            else:
                flat.append(node)
        self.nodes = flat

    def to_dict(self) -> dict[str, Any]:
        return {self.key: [n.to_dict() for n in self.nodes]}


class And(_Group):
    key = "and"


class Or(_Group):
    key = "or"


class Not(Node):
    def __init__(self, node: Node) -> None:
        self.node = node

    def to_dict(self) -> dict[str, Any]:
        return {"not": self.node.to_dict()}


class F:
    """A field, waiting for an operator.

    >>> F("platform").in_(["chatgpt", "ai_mode"]) & ~F("category").is_("Brand")
    """

    __slots__ = ("field",)

    def __init__(self, field: str) -> None:
        self.field = field

    def is_(self, value: FilterInput) -> Leaf:
        return Leaf(self.field, "is", _wire(value))

    def not_is(self, value: FilterInput) -> Leaf:
        return Leaf(self.field, "not_is", _wire(value))

    def in_(self, values: Iterable[FilterInput]) -> Leaf:
        items = [_wire(v) for v in values]
        if not items:
            raise FilterGrammarError(f'"in" on {self.field} needs at least one value')
        return Leaf(self.field, "in", items)

    def not_in(self, values: Iterable[FilterInput]) -> Leaf:
        items = [_wire(v) for v in values]
        if not items:
            raise FilterGrammarError(f'"not_in" on {self.field} needs at least one value')
        return Leaf(self.field, "not_in", items)

    def contains(self, value: str) -> Leaf:
        return Leaf(self.field, "contains", value)

    def not_contains(self, value: str) -> Leaf:
        return Leaf(self.field, "not_contains", value)


def validate_filter(node: Any, path: str = "filter") -> None:
    """Grammar only. Raises on a malformed node; says nothing about size."""
    if not isinstance(node, dict):
        raise FilterGrammarError(f"{path} must be an object")
    keys = set(node)

    for group in ("and", "or"):
        if group in keys:
            if keys != {group}:
                raise FilterGrammarError(f'{path} must contain only "{group}"')
            children = node[group]
            if not isinstance(children, list) or not children:
                raise FilterGrammarError(f"{path}.{group} must be a non-empty array")
            for i, child in enumerate(children):
                validate_filter(child, f"{path}.{group}[{i}]")
            return

    if "not" in keys:
        if keys != {"not"}:
            raise FilterGrammarError(f'{path} must contain only "not"')
        validate_filter(node["not"], f"{path}.not")
        return

    field, op, value = node.get("field"), node.get("op"), node.get("value")
    if not isinstance(field, str) or not field:
        raise FilterGrammarError(f"{path}.field must be a non-empty string")
    if op not in _SCALAR_OPS and op not in _LIST_OPS:
        raise FilterGrammarError(f"{path}.op must be one of is, not_is, in, not_in, contains, not_contains")
    if op in _LIST_OPS:
        if not isinstance(value, list) or not value or not all(isinstance(v, str) and v for v in value):
            raise FilterGrammarError(f'{path}.value must be a non-empty list of strings for "{op}"')
    elif not isinstance(value, str) or not value:
        raise FilterGrammarError(f'{path}.value must be a non-empty string for "{op}"')


def to_filter(value: Node | dict[str, Any]) -> dict[str, Any]:
    """Accept a built node or a raw dict; validate the grammar of either."""
    as_dict = value.to_dict() if isinstance(value, Node) else value
    validate_filter(as_dict)
    return as_dict
