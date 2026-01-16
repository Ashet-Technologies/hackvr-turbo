"""Type validators and parsers for HackVR protocol values."""

from __future__ import annotations

import base64
import re
import unicodedata
from dataclasses import dataclass
from typing import Callable, NewType
from urllib.parse import urlsplit

_FLOAT_BODY = r"-?\d+(?:\.\d+)?"
_FLOAT_RE = re.compile(rf"^{_FLOAT_BODY}$")
_INT_RE = re.compile(r"^(0|[1-9][0-9]*)$")
_VERSION_RE = re.compile(r"^v([1-9][0-9]*)$")
_HEX_RE = re.compile(r"^[0-9a-fA-F]+$")
_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9_]+(-[A-Za-z0-9_]+)*$")
_RESERVED_RE = re.compile(r"^\$[A-Za-z0-9_]+(-[A-Za-z0-9_]+)*$")

String = NewType("String", str)
ZString = NewType("ZString", str)
Int = NewType("Int", int)
Float = NewType("Float", float)
Bool = NewType("Bool", bool)
Color = NewType("Color", str)
AnyValue = NewType("AnyValue", str)
URI = NewType("URI", str)
UserID = NewType("UserID", str)
ObjectID = NewType("ObjectID", str)
GeomID = NewType("GeomID", str)
IntentID = NewType("IntentID", str)
Tag = NewType("Tag", str)
TapKind = NewType("TapKind", str)
SizeMode = NewType("SizeMode", str)
TrackMode = NewType("TrackMode", str)
ReparentMode = NewType("ReparentMode", str)
Anchor = NewType("Anchor", str)
Version = NewType("Version", int)
Bytes16 = NewType("Bytes16", bytes)
Bytes32 = NewType("Bytes32", bytes)
Bytes64 = NewType("Bytes64", bytes)
SessionToken = NewType("SessionToken", bytes)


@dataclass(frozen=True)
class Vec2:
    x: Float
    y: Float


@dataclass(frozen=True)
class Vec3:
    x: Float
    y: Float
    z: Float


@dataclass(frozen=True)
class Euler:
    pan: Float
    tilt: Float
    roll: Float


class ParseError(ValueError):
    """Raised when a HackVR type fails validation."""


def parse_string(value: str, optional: bool) -> String | None:
    assert value is not None
    value = _optional_empty(value, optional, allow_empty=False)
    if value is None:
        return None
    if value == "":
        raise ParseError("string must be non-empty")
    return String(value)


def parse_zstring(value: str, optional: bool) -> ZString | None:
    assert value is not None
    if optional:
        raise ParseError("zstring cannot be optional")
    value = _optional_empty(value, optional, allow_empty=True)
    if value is None:
        return None
    return ZString(value)


def parse_int(value: str, optional: bool) -> Int | None:
    assert value is not None
    value = _optional_empty(value, optional, allow_empty=False)
    if value is None:
        return None
    if not _INT_RE.fullmatch(value):
        raise ParseError("invalid int")
    return Int(int(value))


def parse_float(value: str, optional: bool) -> Float | None:
    assert value is not None
    value = _optional_empty(value, optional, allow_empty=False)
    if value is None:
        return None
    if not _FLOAT_RE.fullmatch(value):
        raise ParseError("invalid float")
    return Float(float(value))


def parse_bool(value: str, optional: bool) -> Bool | None:
    assert value is not None
    value = _optional_empty(value, optional, allow_empty=False)
    if value is None:
        return None
    if value == "true":
        return Bool(True)
    if value == "false":
        return Bool(False)
    raise ParseError("invalid bool")


def parse_vec2(value: str, optional: bool) -> Vec2 | None:
    return _parse_vec(value, optional, count=2)


def parse_vec3(value: str, optional: bool) -> Vec3 | None:
    return _parse_vec(value, optional, count=3)


def parse_color(value: str, optional: bool) -> Color | None:
    assert value is not None
    value = _optional_empty(value, optional, allow_empty=False)
    if value is None:
        return None
    if not _COLOR_RE.fullmatch(value):
        raise ParseError("invalid color")
    return Color(value.lower())


def parse_bytes(value: str, optional: bool, length: int) -> bytes | None:
    assert value is not None
    value = _optional_empty(value, optional, allow_empty=False)
    if value is None:
        return None
    expected_length = length * 2
    if len(value) != expected_length or not _HEX_RE.fullmatch(value):
        raise ParseError("invalid bytes")
    return bytes.fromhex(value)


def parse_bytes16(value: str, optional: bool) -> Bytes16 | None:
    parsed = parse_bytes(value, optional, 16)
    if parsed is None:
        return None
    return Bytes16(parsed)


def parse_bytes32(value: str, optional: bool) -> Bytes32 | None:
    parsed = parse_bytes(value, optional, 32)
    if parsed is None:
        return None
    return Bytes32(parsed)


def parse_bytes64(value: str, optional: bool) -> Bytes64 | None:
    parsed = parse_bytes(value, optional, 64)
    if parsed is None:
        return None
    return Bytes64(parsed)


def bytes_parser(length: int) -> Callable[[str, bool], bytes | None]:
    def _parser(value: str, optional: bool) -> bytes | None:
        return parse_bytes(value, optional, length)

    return _parser


def parse_any(value: str, optional: bool) -> AnyValue | None:
    assert value is not None
    value = _optional_empty(value, optional, allow_empty=True)
    if value is None:
        return None
    return AnyValue(value)


def parse_uri(value: str, optional: bool) -> URI | None:
    assert value is not None
    value = _optional_empty(value, optional, allow_empty=False)
    if value is None:
        return None
    if _contains_control(value) or any(ch.isspace() for ch in value):
        raise ParseError("invalid uri")
    parsed = urlsplit(value)
    if not parsed.scheme:
        raise ParseError("uri must be absolute")
    return URI(value)


def parse_userid(value: str, optional: bool) -> UserID | None:
    assert value is not None
    value = _optional_empty(value, optional, allow_empty=False)
    if value is None:
        return None
    if "\n" in value:
        raise ParseError("userid contains LF")
    if value != value.strip():
        raise ParseError("userid has leading/trailing whitespace")
    if len(value) >= 128:
        raise ParseError("userid too long")
    return UserID(value)


def parse_object(value: str, optional: bool) -> ObjectID | None:
    parsed = _parse_identifier(value, optional)
    if parsed is None:
        return None
    return ObjectID(parsed)


def parse_geom(value: str, optional: bool) -> GeomID | None:
    parsed = _parse_identifier(value, optional)
    if parsed is None:
        return None
    return GeomID(parsed)


def parse_intent(value: str, optional: bool) -> IntentID | None:
    parsed = _parse_identifier(value, optional)
    if parsed is None:
        return None
    return IntentID(parsed)


def parse_tag(value: str, optional: bool) -> Tag | None:
    parsed = _parse_identifier(value, optional)
    if parsed is None:
        return None
    return Tag(parsed)


def parse_tapkind(value: str, optional: bool) -> TapKind | None:
    parsed = _parse_enum(value, optional, {"primary", "secondary"})
    if parsed is None:
        return None
    return TapKind(parsed)


def parse_sizemode(value: str, optional: bool) -> SizeMode | None:
    parsed = _parse_enum(value, optional, {"stretch", "cover", "contain", "fixed-width", "fixed-height"})
    if parsed is None:
        return None
    return SizeMode(parsed)


def parse_track_mode(value: str, optional: bool) -> TrackMode | None:
    parsed = _parse_enum(value, optional, {"plane", "focus"})
    if parsed is None:
        return None
    return TrackMode(parsed)


def parse_reparent_mode(value: str, optional: bool) -> ReparentMode | None:
    parsed = _parse_enum(value, optional, {"world", "local"})
    if parsed is None:
        return None
    return ReparentMode(parsed)


def parse_anchor(value: str, optional: bool) -> Anchor | None:
    parsed = _parse_enum(
        value,
        optional,
        {
            "top-left",
            "top-center",
            "top-right",
            "center-left",
            "center-center",
            "center-right",
            "bottom-left",
            "bottom-center",
            "bottom-right",
        },
    )
    if parsed is None:
        return None
    return Anchor(parsed)


def parse_version(value: str, optional: bool) -> Version | None:
    assert value is not None
    value = _optional_empty(value, optional, allow_empty=False)
    if value is None:
        return None
    match = _VERSION_RE.fullmatch(value)
    if not match:
        raise ParseError("invalid version")
    return Version(int(match.group(1)))


def parse_euler(value: str, optional: bool) -> Euler | None:
    vector = _parse_vec(value, optional, count=3)
    if vector is None:
        return None
    return Euler(vector.x, vector.y, vector.z)


def parse_session_token(value: str, optional: bool) -> SessionToken | None:
    assert value is not None
    value = _optional_empty(value, optional, allow_empty=False)
    if value is None:
        return None
    if len(value) != 43:
        raise ParseError("invalid session token length")
    if not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        raise ParseError("invalid session token characters")
    padded = value + "=="
    try:
        decoded = base64.urlsafe_b64decode(padded)
    except (ValueError, base64.binascii.Error) as exc:
        raise ParseError("invalid session token") from exc
    if len(decoded) != 32:
        raise ParseError("invalid session token bytes")
    return SessionToken(decoded)


def _optional_empty(value: str, optional: bool, allow_empty: bool) -> str | None:
    if optional and value == "":
        return "" if allow_empty else None
    return value


def _parse_identifier(value: str, optional: bool) -> str | None:
    value = _optional_empty(value, optional, allow_empty=False)
    if value is None:
        return None
    if _IDENTIFIER_RE.fullmatch(value) or _RESERVED_RE.fullmatch(value):
        return value
    raise ParseError("invalid identifier")


def _parse_enum(value: str, optional: bool, allowed: set[str]) -> str | None:
    value = _optional_empty(value, optional, allow_empty=False)
    if value is None:
        return None
    if value not in allowed:
        raise ParseError("invalid enum")
    return value


def _parse_vec(value: str, optional: bool, count: int):
    assert value is not None
    value = _optional_empty(value, optional, allow_empty=False)
    if value is None:
        return None
    if count == 2:
        pattern = rf"^\(\s*({_FLOAT_BODY})\s+({_FLOAT_BODY})\s*\)$"
    elif count == 3:
        pattern = rf"^\(\s*({_FLOAT_BODY})\s+({_FLOAT_BODY})\s+({_FLOAT_BODY})\s*\)$"
    else:
        raise ValueError("unsupported vector length")
    match = re.fullmatch(pattern, value)
    if not match:
        raise ParseError("invalid vector")
    numbers = [Float(float(group)) for group in match.groups()]
    if count == 2:
        return Vec2(numbers[0], numbers[1])
    return Vec3(numbers[0], numbers[1], numbers[2])


def _contains_control(value: str) -> bool:
    return any(unicodedata.category(ch) == "Cc" for ch in value)
