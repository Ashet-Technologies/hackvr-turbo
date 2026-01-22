import base64

import pytest

from hackvr.common import types


def test_string_and_zstring():
    assert types.parse_string("hello", False) == "hello"
    with pytest.raises(types.ParseError):
        types.parse_string("", False)
    assert types.parse_string("", True) is None
    assert types.parse_zstring("", False) == ""
    assert types.parse_zstring("", True) == ""


def test_int_float_bool():
    assert types.parse_int("10", False) == 10
    with pytest.raises(types.ParseError):
        types.parse_int("01", False)
    assert types.parse_float("-1.5", False) == -1.5
    with pytest.raises(types.ParseError):
        types.parse_float(".5", False)
    assert types.parse_bool("true", False) is True
    assert types.parse_bool("false", False) is False
    with pytest.raises(types.ParseError):
        types.parse_bool("yes", False)


def test_optional_values_return_none():
    assert types.parse_int("", True) is None
    assert types.parse_float("", True) is None
    assert types.parse_bool("", True) is None
    assert types.parse_color("", True) is None
    assert types.parse_bytes16("", True) is None
    assert types.parse_bytes32("", True) is None
    assert types.parse_bytes64("", True) is None
    assert types.parse_userid("", True) is None
    assert types.parse_object("", True) is None
    assert types.parse_geom("", True) is None
    assert types.parse_intent("", True) is None
    assert types.parse_tapkind("", True) is None
    assert types.parse_sizemode("", True) is None
    assert types.parse_track_mode("", True) is None
    assert types.parse_reparent_mode("", True) is None
    assert types.parse_anchor("", True) is None
    assert types.parse_version("", True) is None
    assert types.parse_euler("", True) is None
    assert types.parse_vec2("", True) is None
    assert types.parse_vec3("", True) is None
    assert types.parse_session_token("", True) is None


def test_vectors_and_color():
    vec2 = types.parse_vec2("(1 2)", False)
    assert vec2 == types.Vec2(1.0, 2.0)
    vec3 = types.parse_vec3("( -1 0 3.5 )", False)
    assert vec3 == types.Vec3(-1.0, 0.0, 3.5)
    assert types.parse_color("#Aa00FF", False) == "#aa00ff"
    with pytest.raises(types.ParseError):
        types.parse_vec2("(1,2)", False)
    with pytest.raises(types.ParseError):
        types.parse_vec3("(1 2)", False)
    with pytest.raises(types.ParseError):
        types.parse_color("123456", False)


def test_bytes_any_uri():
    assert types.parse_bytes("ff" * 4, False, 4) == b"\xff\xff\xff\xff"
    assert types.parse_bytes32("ff" * 32, False) == b"\xff" * 32
    assert types.parse_bytes64("ff" * 64, False) == b"\xff" * 64
    assert types.parse_any("", False) == ""
    assert types.parse_any("", True) == ""
    assert types.parse_any("value", True) == "value"
    assert types.parse_uri("https://example.com", False) == "https://example.com"
    with pytest.raises(types.ParseError):
        types.parse_uri("/relative", False)
    with pytest.raises(types.ParseError):
        types.parse_uri("https://example.com/\x00", False)
    with pytest.raises(types.ParseError):
        types.parse_uri("https://example.com/has space", False)
    assert types.parse_uri("", True) is None

    parser = types.bytes_parser(4)
    assert parser("ff" * 4, False) == b"\xff\xff\xff\xff"
    with pytest.raises(types.ParseError):
        parser("ff", False)
    with pytest.raises(types.ParseError):
        types.parse_bytes("zz", False, 1)


def test_identifiers_and_enums():
    assert types.parse_object("foo-1", False) == "foo-1"
    assert types.parse_geom("$global", False) == "$global"
    with pytest.raises(types.ParseError):
        types.parse_tag("bad!", False)
    assert types.parse_tapkind("primary", False) == types.TapKind.PRIMARY
    assert types.parse_sizemode("cover", False) == types.SizeMode.COVER
    assert types.parse_track_mode("focus", False) == types.TrackMode.FOCUS
    assert types.parse_reparent_mode("local", False) == types.ReparentMode.LOCAL
    assert types.parse_anchor("top-left", False) == types.Anchor.TOP_LEFT
    with pytest.raises(types.ParseError):
        types.parse_tapkind("bad", False)


def test_version_and_euler():
    assert types.parse_version("v12", False) == 12
    euler = types.parse_euler("(0 1 2)", False)
    assert euler == types.Euler(0.0, 1.0, 2.0)
    with pytest.raises(types.ParseError):
        types.parse_version("v0", False)
    with pytest.raises(types.ParseError):
        types.parse_version("1", False)
    with pytest.raises(types.ParseError):
        types.parse_euler("(1 2)", False)


def test_userid_and_session_token():
    assert types.parse_userid("User42", False) == "User42"
    with pytest.raises(types.ParseError):
        types.parse_userid(" bad", False)
    with pytest.raises(types.ParseError):
        types.parse_userid("user\n42", False)
    with pytest.raises(types.ParseError):
        types.parse_userid("user ", False)
    with pytest.raises(types.ParseError):
        types.parse_userid("a" * 128, False)
    token_bytes = bytes(range(32))
    token = base64.urlsafe_b64encode(token_bytes).decode("ascii").rstrip("=")
    assert len(token) == 43
    assert types.parse_session_token(token, False) == token_bytes
    with pytest.raises(types.ParseError):
        types.parse_session_token("short", False)
    with pytest.raises(types.ParseError):
        types.parse_session_token(token[:-1] + "!", False)
