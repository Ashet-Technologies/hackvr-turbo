from __future__ import annotations

import base64
import string

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from hackvr.common import (
    Anchor,
    AnyValue,
    Bytes16,
    Bytes32,
    Bytes64,
    Color,
    Euler,
    GeomID,
    IntentID,
    ObjectID,
    Parser,
    ReparentMode,
    SessionToken,
    SizeMode,
    Tag,
    TapKind,
    TrackMode,
    URI,
    UserID,
    Vec2,
    Vec3,
    Version,
    ZString,
    bytes_parser,
    encode,
    expand,
    get_upper_expansion_limit,
    is_valid_pattern,
    is_valid_token,
    is_zstring_annotation,
    parse_anchor,
    parse_any,
    parse_bool,
    parse_bytes,
    parse_bytes16,
    parse_bytes32,
    parse_bytes64,
    parse_color,
    parse_euler,
    parse_float,
    parse_geom,
    parse_int,
    parse_intent,
    parse_object,
    parse_reparent_mode,
    parse_session_token,
    parse_sizemode,
    parse_string,
    parse_tag,
    parse_tapkind,
    parse_track_mode,
    parse_uri,
    parse_userid,
    parse_vec2,
    parse_vec3,
    parse_version,
    parse_zstring,
    select,
)
from hackvr.common.stream import MAX_LINE_LENGTH
from hackvr.common.types import ParseError

_IDENTIFIER_ALPHABET = string.ascii_letters + string.digits + "_"
_NAME_ALPHABET = string.ascii_letters + string.digits + "-_"
_PARAM_ALPHABET = string.ascii_letters + string.digits + " -_./"
_PARAM_ALPHABET_WITH_LF = _PARAM_ALPHABET + "\n"


def _identifier_parts() -> st.SearchStrategy[list[str]]:
    return st.lists(
        st.text(_IDENTIFIER_ALPHABET, min_size=1, max_size=8),
        min_size=1,
        max_size=4,
    )


@st.composite
def valid_identifier(draw: st.DrawFn) -> str:
    parts = draw(_identifier_parts())
    return "-".join(parts)


@st.composite
def reserved_identifier(draw: st.DrawFn) -> str:
    parts = draw(_identifier_parts())
    return "$" + "-".join(parts)


@st.composite
def valid_token(draw: st.DrawFn) -> str:
    return draw(st.one_of(valid_identifier(), reserved_identifier()))


@st.composite
def valid_pattern(draw: st.DrawFn) -> str:
    def group_items(allow_reserved: bool) -> st.SearchStrategy[str]:
        base = st.text(_IDENTIFIER_ALPHABET, min_size=1, max_size=4)
        parts = st.lists(base, min_size=1, max_size=3)
        if allow_reserved:
            parts = st.lists(
                st.one_of(base, base.map(lambda item: f"${item}")),
                min_size=1,
                max_size=3,
            )
        return parts.map(lambda items: "{" + ",".join(items) + "}")

    def range_group() -> st.SearchStrategy[str]:
        return st.tuples(
            st.integers(min_value=0, max_value=5),
            st.integers(min_value=0, max_value=5),
            st.booleans(),
        ).map(
            lambda data: "{" + _format_range(*_sorted_range(*data)) + "}"
        )

    count = draw(st.integers(min_value=1, max_value=3))
    parts: list[str] = []
    for index in range(count):
        allow_reserved = index == 0
        part = draw(
            st.one_of(
                valid_identifier(),
                reserved_identifier() if allow_reserved else valid_identifier(),
                st.sampled_from(["*", "?"]),
                group_items(allow_reserved=allow_reserved),
                range_group(),
            )
        )
        parts.append(part)
    return "-".join(parts)


@st.composite
def pattern_without_wildcards(draw: st.DrawFn) -> str:
    def group_items(allow_reserved: bool) -> st.SearchStrategy[str]:
        base = st.text(_IDENTIFIER_ALPHABET, min_size=1, max_size=4)
        parts = st.lists(base, min_size=1, max_size=3)
        if allow_reserved:
            parts = st.lists(
                st.one_of(base, base.map(lambda item: f"${item}")),
                min_size=1,
                max_size=3,
            )
        return parts.map(lambda items: "{" + ",".join(items) + "}")

    def range_group() -> st.SearchStrategy[str]:
        return st.tuples(
            st.integers(min_value=0, max_value=5),
            st.integers(min_value=0, max_value=5),
            st.booleans(),
        ).map(
            lambda data: "{" + _format_range(*_sorted_range(*data)) + "}"
        )

    count = draw(st.integers(min_value=1, max_value=3))
    parts: list[str] = []
    for index in range(count):
        allow_reserved = index == 0
        part = draw(
            st.one_of(
                reserved_identifier() if allow_reserved else valid_identifier(),
                valid_identifier(),
                group_items(allow_reserved=allow_reserved),
                range_group(),
            )
        )
        parts.append(part)
    return "-".join(parts)


def _format_range(start: int, end: int, padded: bool) -> str:
    if padded:
        width = max(len(str(start)), len(str(end)), 2)
        return f"{start:0{width}d}..{end:0{width}d}"
    return f"{start}..{end}"


def _sorted_range(start: int, end: int, padded: bool) -> tuple[int, int, bool]:
    if start <= end:
        return start, end, padded
    return end, start, padded


def _float_string(value: float, decimals: int | None) -> str:
    if decimals is None:
        return str(int(value))
    return f"{value:.{decimals}f}"


@st.composite
def float_string(draw: st.DrawFn) -> str:
    base = draw(st.integers(min_value=-1000, max_value=1000))
    if draw(st.booleans()):
        return str(base)
    decimals = draw(st.integers(min_value=1, max_value=5))
    return _float_string(base + draw(st.integers(0, 99)) / (10**decimals), decimals)


@st.composite
def vec_string(draw: st.DrawFn, count: int) -> str:
    components = [draw(float_string()) for _ in range(count)]
    inner = (" " * draw(st.integers(1, 3))).join(components)
    prefix = " " * draw(st.integers(0, 2))
    suffix = " " * draw(st.integers(0, 2))
    return f"({prefix}{inner}{suffix})"


@st.composite
def userid_string(draw: st.DrawFn) -> str:
    alphabet = string.ascii_letters + string.digits + " "
    value = draw(st.text(alphabet, min_size=1, max_size=20))
    if value != value.strip():
        value = value.strip() or "User"
    return value


@st.composite
def uri_string(draw: st.DrawFn) -> str:
    scheme = draw(st.text(string.ascii_lowercase, min_size=1, max_size=6))
    host = draw(st.text(string.ascii_lowercase + string.digits, min_size=1, max_size=10))
    path = draw(st.text(string.ascii_lowercase + string.digits + "-/_", max_size=10))
    return f"{scheme}://{host}{path}"


@settings(max_examples=200)
@given(st.text(min_size=1))
def test_string_parsing_round_trip(value: str) -> None:
    assert parse_string(value, False) == value


@settings(max_examples=200)
@given(st.booleans())
def test_zstring_allows_empty(optional: bool) -> None:
    assert parse_zstring("", optional) == ""


@settings(max_examples=200)
@given(st.integers(min_value=0, max_value=10**6))
def test_parse_int_round_trip(value: int) -> None:
    text = "0" if value == 0 else str(value)
    assert parse_int(text, False) == value


@settings(max_examples=200)
@given(st.integers(min_value=0, max_value=10**6).filter(lambda v: v != 0))
def test_parse_int_rejects_leading_zero(value: int) -> None:
    text = f"0{value}"
    with pytest.raises(ParseError):
        parse_int(text, False)


@settings(max_examples=200)
@given(float_string())
def test_parse_float_round_trip(text: str) -> None:
    assert parse_float(text, False) == float(text)


@settings(max_examples=100)
@given(st.sampled_from([".5", "1.", "+1", "1e3"]))
def test_parse_float_rejects_non_spec(value: str) -> None:
    with pytest.raises(ParseError):
        parse_float(value, False)


@settings(max_examples=50)
@given(st.sampled_from(["true", "false"]))
def test_parse_bool_round_trip(value: str) -> None:
    parsed = parse_bool(value, False)
    assert parsed is (value == "true")


@settings(max_examples=200)
@given(vec_string(count=2))
def test_parse_vec2_round_trip(value: str) -> None:
    parsed = parse_vec2(value, False)
    assert isinstance(parsed, Vec2)


@settings(max_examples=200)
@given(vec_string(count=3))
def test_parse_vec3_round_trip(value: str) -> None:
    parsed = parse_vec3(value, False)
    assert isinstance(parsed, Vec3)


@settings(max_examples=200)
@given(st.text("0123456789abcdefABCDEF", min_size=6, max_size=6))
def test_parse_color_normalizes(value: str) -> None:
    parsed = parse_color(f"#{value}", False)
    assert parsed == f"#{value.lower()}"


@settings(max_examples=200)
@given(st.binary(min_size=16, max_size=16))
def test_parse_bytes16_round_trip(value: bytes) -> None:
    encoded = value.hex()
    assert parse_bytes16(encoded, False) == Bytes16(value)


@settings(max_examples=200)
@given(st.binary(min_size=32, max_size=32))
def test_parse_bytes32_round_trip(value: bytes) -> None:
    encoded = value.hex()
    assert parse_bytes32(encoded, False) == Bytes32(value)


@settings(max_examples=200)
@given(st.binary(min_size=64, max_size=64))
def test_parse_bytes64_round_trip(value: bytes) -> None:
    encoded = value.hex()
    assert parse_bytes64(encoded, False) == Bytes64(value)


@settings(max_examples=200)
@given(st.binary(min_size=8, max_size=8))
def test_parse_bytes_round_trip(value: bytes) -> None:
    encoded = value.hex()
    assert parse_bytes(encoded, False, 8) == value


@settings(max_examples=200)
@given(st.text(min_size=0, max_size=32))
def test_parse_any_round_trip(value: str) -> None:
    assert parse_any(value, False) == AnyValue(value)


@settings(max_examples=200)
@given(uri_string())
def test_parse_uri_round_trip(value: str) -> None:
    assert parse_uri(value, False) == URI(value)


@settings(max_examples=200)
@given(userid_string())
def test_parse_userid_round_trip(value: str) -> None:
    assert parse_userid(value, False) == UserID(value)


@settings(max_examples=200)
@given(valid_identifier())
def test_parse_object_round_trip(value: str) -> None:
    assert parse_object(value, False) == ObjectID(value)


@settings(max_examples=200)
@given(reserved_identifier())
def test_parse_geom_reserved_round_trip(value: str) -> None:
    assert parse_geom(value, False) == GeomID(value)


@settings(max_examples=200)
@given(valid_identifier())
def test_parse_intent_round_trip(value: str) -> None:
    assert parse_intent(value, False) == IntentID(value)


@settings(max_examples=200)
@given(valid_identifier())
def test_parse_tag_round_trip(value: str) -> None:
    assert parse_tag(value, False) == Tag(value)


@settings(max_examples=50)
@given(st.sampled_from([member.value for member in TapKind]))
def test_parse_tapkind_round_trip(value: str) -> None:
    assert parse_tapkind(value, False) == TapKind(value)


@settings(max_examples=50)
@given(st.sampled_from([member.value for member in SizeMode]))
def test_parse_sizemode_round_trip(value: str) -> None:
    assert parse_sizemode(value, False) == SizeMode(value)


@settings(max_examples=50)
@given(st.sampled_from([member.value for member in TrackMode]))
def test_parse_track_mode_round_trip(value: str) -> None:
    assert parse_track_mode(value, False) == TrackMode(value)


@settings(max_examples=50)
@given(st.sampled_from([member.value for member in ReparentMode]))
def test_parse_reparent_mode_round_trip(value: str) -> None:
    assert parse_reparent_mode(value, False) == ReparentMode(value)


@settings(max_examples=50)
@given(st.sampled_from([member.value for member in Anchor]))
def test_parse_anchor_round_trip(value: str) -> None:
    assert parse_anchor(value, False) == Anchor(value)


@settings(max_examples=200)
@given(st.integers(min_value=1, max_value=10**6))
def test_parse_version_round_trip(value: int) -> None:
    text = f"v{value}"
    assert parse_version(text, False) == Version(value)


@settings(max_examples=200)
@given(vec_string(count=3))
def test_parse_euler_round_trip(value: str) -> None:
    parsed = parse_euler(value, False)
    assert isinstance(parsed, Euler)


@settings(max_examples=200)
@given(st.binary(min_size=32, max_size=32))
def test_parse_session_token_round_trip(value: bytes) -> None:
    token = base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")
    assert len(token) == 43
    assert parse_session_token(token, False) == SessionToken(value)


@settings(max_examples=200)
@given(st.binary(min_size=8, max_size=8))
def test_bytes_parser_round_trip(value: bytes) -> None:
    parser = bytes_parser(8)
    assert parser(value.hex(), False) == value


@settings(max_examples=50)
@given(st.text(min_size=1, max_size=10))
def test_newtypes_identity(value: str) -> None:
    assert URI(value) == value
    assert AnyValue(value) == value


@settings(max_examples=200)
@given(st.text("0123456789abcdef", min_size=6, max_size=6))
def test_color_newtype_identity(value: str) -> None:
    assert Color(f"#{value}") == f"#{value}"


@settings(max_examples=200)
@given(st.text(min_size=1, max_size=10))
def test_is_zstring_annotation(value: str) -> None:
    assert is_zstring_annotation(ZString)
    assert not is_zstring_annotation(str)
    assert parse_zstring(value, False) == value


@settings(max_examples=200)
@given(valid_token())
def test_is_valid_token_accepts_valid(value: str) -> None:
    assert is_valid_token(value)


@settings(max_examples=50)
@given(st.sampled_from(["", "bad!", "a--b", "-start", "end-"]))
def test_is_valid_token_rejects_invalid(value: str) -> None:
    assert not is_valid_token(value)


@settings(max_examples=200)
@given(valid_pattern())
def test_is_valid_pattern_accepts_valid(value: str) -> None:
    assert is_valid_pattern(value)


@settings(max_examples=50)
@given(st.sampled_from(["", "{", "a--b", "{a,{b}}", "a-}"]))
def test_is_valid_pattern_rejects_invalid(value: str) -> None:
    assert not is_valid_pattern(value)


@settings(max_examples=200)
@given(pattern_without_wildcards())
def test_expand_round_trip(value: str) -> None:
    assert is_valid_pattern(value)
    expanded = list(expand(value))
    for token in expanded:
        assert is_valid_token(token)


@settings(max_examples=50)
@given(pattern_without_wildcards(), st.integers(min_value=1, max_value=5))
def test_get_upper_expansion_limit_matches_expand(value: str, multiplier: int) -> None:
    expanded = list(expand(value))
    assert get_upper_expansion_limit(value, multiplier) == len(expanded)


@settings(max_examples=50)
@given(st.integers(min_value=1, max_value=5))
def test_get_upper_expansion_limit_handles_wildcards(multiplier: int) -> None:
    pattern = "{a,b}-*"
    assert get_upper_expansion_limit(pattern, multiplier) == 2 * multiplier


@settings(max_examples=200)
@given(st.lists(valid_identifier(), min_size=1, max_size=5))
def test_select_star_returns_scope(scope: list[str]) -> None:
    assert select("*", scope, key=lambda value: value) == scope


@settings(max_examples=200)
@given(pattern_without_wildcards())
def test_select_matches_expanded_patterns(pattern: str) -> None:
    expanded = list(expand(pattern))
    scope = expanded + ["extra"]
    selected = select(pattern, scope, key=lambda value: value)
    assert set(selected).issuperset(expanded)


@settings(max_examples=200)
@given(
    st.text(_NAME_ALPHABET, min_size=1, max_size=16),
    st.lists(st.text(_PARAM_ALPHABET_WITH_LF, max_size=16), max_size=5),
)
def test_encode_parser_round_trip(command: str, params: list[str]) -> None:
    line = "\t".join([command, *params]) + "\r\n"
    assume(len(line.encode("utf-8")) <= MAX_LINE_LENGTH)
    data = encode(command, params)
    parser = Parser()
    parser.push(data)
    assert parser.pull() == [command, *params]


@settings(max_examples=50)
@given(st.text(_NAME_ALPHABET, min_size=1, max_size=10))
def test_encode_rejects_control_characters(command: str) -> None:
    with pytest.raises(ValueError):
        encode(command + "\t", [])


@settings(max_examples=50)
@given(st.integers(min_value=MAX_LINE_LENGTH + 1, max_value=MAX_LINE_LENGTH + 20))
def test_parser_skips_overlong_line(length: int) -> None:
    parser = Parser()
    parser.push(b"a" * length + b"\r\n")
    parser.push(encode("ping", []))
    assert parser.pull() == ["ping"]
