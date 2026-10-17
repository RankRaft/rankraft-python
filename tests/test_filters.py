from __future__ import annotations

import json

import pytest

from rankraft import F, FilterGrammarError, to_filter, validate_filter


def test_emits_field_op_value_in_that_order():
    # Key order may be load-bearing for the server's body-hash cursor.
    assert json.dumps(F("platform").is_("chatgpt").to_dict()) == '{"field": "platform", "op": "is", "value": "chatgpt"}'


def test_builds_the_documented_tree_shape():
    node = F("platform").in_(["chatgpt"]) & ~F("category").is_("Brand")
    assert node.to_dict() == {
        "and": [
            {"field": "platform", "op": "in", "value": ["chatgpt"]},
            {"not": {"field": "category", "op": "is", "value": "Brand"}},
        ]
    }


def test_chained_and_flattens_instead_of_nesting():
    # `a & b & c` nesting three deep would hit the server's depth limit for no
    # reason; and/or are associative, so flattening changes nothing but shape.
    node = F("a").is_(1) & F("b").is_(2) & F("c").is_(3)
    assert len(node.to_dict()["and"]) == 3


@pytest.mark.parametrize(
    "bad",
    [
        {},
        {"and": []},
        {"and": [{"field": "x", "op": "is", "value": "y"}], "not": {}},
        {"field": "x", "op": "nope", "value": "y"},
        {"field": "x", "op": "in", "value": "not a list"},
        {"field": "x", "op": "is", "value": ["a list"]},
    ],
)
def test_rejects_malformed_grammar(bad):
    with pytest.raises(FilterGrammarError):
        validate_filter(bad)


def test_an_empty_in_list_is_rejected_at_build_time():
    with pytest.raises(FilterGrammarError):
        F("platform").in_([])


def test_says_nothing_about_depth_or_list_length():
    # Those are server limits. A copy here would be the one that goes stale;
    # the 422 carries the real figure.
    deep = ~~~~F("platform").is_("chatgpt")
    validate_filter(deep.to_dict())
    F("platform").in_([f"p{i}" for i in range(500)])


def test_a_raw_dict_goes_anywhere_a_built_node_goes():
    assert to_filter({"or": [{"field": "path", "op": "contains", "value": "/blog"}]}) == {
        "or": [{"field": "path", "op": "contains", "value": "/blog"}]
    }


def test_stringifies_numbers_and_booleans_because_the_wire_type_is_string():
    # `verified` is a boolean column; people will write F("verified").is_(True).
    assert F("verified").is_(True).to_dict() == {"field": "verified", "op": "is", "value": "true"}
    assert F("rank").in_([1, 2]).to_dict()["value"] == ["1", "2"]
    # A raw dict gets no such help: it must already be what the server accepts.
    with pytest.raises(FilterGrammarError):
        validate_filter({"field": "verified", "op": "is", "value": True})
