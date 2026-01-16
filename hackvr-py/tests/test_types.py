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


def test_vectors_and_color():
    vec2 = types.parse_vec2("(1 2)", False)
    assert vec2 == types.Vec2(1.0, 2.0)
    vec3 = types.parse_vec3("( -1 0 3.5 )", False)
    assert vec3 == types.Vec3(-1.0, 0.0, 3.5)
    assert types.parse_color("#Aa00FF", False) == "#aa00ff"
    with pytest.raises(types.ParseError):
        types.parse_vec2("(1,2)", False)


def test_bytes_any_uri():
    assert types.parse_bytes("ff" * 4, False, 4) == b"\xff\xff\xff\xff"
    assert types.parse_bytes32("ff" * 32, False) == b"\xff" * 32
    assert types.parse_any("", False) == ""
    assert types.parse_uri("https://example.com", False) == "https://example.com"
    with pytest.raises(types.ParseError):
        types.parse_uri("/relative", False)


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


def test_version_and_euler():
    assert types.parse_version("v12", False) == 12
    euler = types.parse_euler("(0 1 2)", False)
    assert euler == types.Euler(0.0, 1.0, 2.0)
    with pytest.raises(types.ParseError):
        types.parse_version("v0", False)


def test_userid_and_session_token():
    assert types.parse_userid("User42", False) == "User42"
    with pytest.raises(types.ParseError):
        types.parse_userid(" bad", False)
    token_bytes = bytes(range(32))
    token = base64.urlsafe_b64encode(token_bytes).decode("ascii").rstrip("=")
    assert len(token) == 43
    assert types.parse_session_token(token, False) == token_bytes
