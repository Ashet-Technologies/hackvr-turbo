import random

import pytest

from hackvr.common.globbing import (
    expand,
    get_upper_expansion_limit,
    is_valid_pattern,
    is_valid_token,
    select,
)
from hackvr.common.stream import Parser


def test_token_and_pattern_validation():
    assert is_valid_token("foo-01")
    assert is_valid_token("$global")
    assert not is_valid_token("bad!")
    assert is_valid_pattern("foo-*-bar")
    assert is_valid_pattern("foo-{a,b}-bar")
    assert not is_valid_pattern("foo--bar")


def test_expand_list_and_range():
    assert list(expand("foo-{a,b}")) == ["foo-a", "foo-b"]
    assert list(expand("item-{00..02}")) == ["item-00", "item-01", "item-02"]
    assert list(expand("{a,b}-{c,d}-{1..3}")) == [
        "a-c-1",
        "a-c-2",
        "a-c-3",
        "a-d-1",
        "a-d-2",
        "a-d-3",
        "b-c-1",
        "b-c-2",
        "b-c-3",
        "b-d-1",
        "b-d-2",
        "b-d-3",
    ]
    assert list(expand("{1..10}")) == [str(number) for number in range(1, 11)]


def test_expand_rejects_wildcards():
    with pytest.raises(ValueError):
        list(expand("foo-*"))


def test_select_matches_wildcards_and_groups():
    scope = ["foo", "foo-1", "foo-2", "bar-1", "$global"]
    items = [{"id": value} for value in scope]
    result = select("foo-*", items, key=lambda item: item["id"])
    assert [item["id"] for item in result] == ["foo", "foo-1", "foo-2"]
    result = select("{foo,bar}-?", items, key=lambda item: item["id"])
    assert [item["id"] for item in result] == ["foo-1", "foo-2", "bar-1"]


def test_select_match_all_and_single_part():
    scope = ["one", "two", "two-part"]
    items = [{"id": value} for value in scope]
    selected_all = [
        item["id"] for item in select("*", items, key=lambda item: item["id"])
    ]
    assert selected_all == scope
    assert [item["id"] for item in select("?", items, key=lambda item: item["id"])] == [
        "one",
        "two",
    ]


def test_upper_expansion_limit():
    assert get_upper_expansion_limit("foo-{a,b}", 10) == 2
    assert get_upper_expansion_limit("foo-*", 10) == 10
    assert get_upper_expansion_limit("{a,b}-{0..2}-*", 5) == 2 * 3 * 5


def test_parser_fuzz_inputs_from_globbing():
    parser = Parser()
    rng = random.Random(9001)
    for _ in range(25):
        size = rng.randint(0, 128)
        data = bytes(rng.getrandbits(8) for _ in range(size))
        parser.push(data)
        while parser.pull() is not None:
            pass
