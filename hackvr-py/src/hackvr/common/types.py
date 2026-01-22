"""Type validators and parsers for HackVR protocol values."""

from __future__ import annotations

import base64
import re
import unicodedata
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Annotated, Literal, NewType, cast, get_args, get_origin
from urllib.parse import urlsplit

if TYPE_CHECKING:
    from collections.abc import Callable

_FLOAT_BODY = r"-?\d+(?:\.\d+)?"
_FLOAT_RE = re.compile(rf"^{_FLOAT_BODY}$")
_INT_RE = re.compile(r"^(0|[1-9][0-9]*)$")
_VERSION_RE = re.compile(r"^v([1-9][0-9]*)$")
_HEX_RE = re.compile(r"^[0-9a-fA-F]+$")
_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9_]+(-[A-Za-z0-9_]+)*$")
_RESERVED_RE = re.compile(r"^\$[A-Za-z0-9_]+(-[A-Za-z0-9_]+)*$")
_USER_ID_MAX_LENGTH = 128
_SESSION_TOKEN_LENGTH = 43
_SESSION_TOKEN_BYTES_LENGTH = 32
_VECTOR2_COMPONENTS = 2
_VECTOR3_COMPONENTS = 3

String = str
ZString = Annotated[str, "zstring"]
Color = NewType("Color", str)
AnyValue = NewType("AnyValue", str)
URI = NewType("URI", str)
UserID = NewType("UserID", str)
ObjectID = NewType("ObjectID", str)
GeomID = NewType("GeomID", str)
IntentID = NewType("IntentID", str)
Tag = NewType("Tag", str)
Version = NewType("Version", int)
Bytes16 = NewType("Bytes16", bytes)
Bytes32 = NewType("Bytes32", bytes)
Bytes64 = NewType("Bytes64", bytes)
SessionToken = NewType("SessionToken", bytes)


class TapKind(Enum):
    """Tap input kinds."""

    PRIMARY = "primary"
    SECONDARY = "secondary"


class SizeMode(Enum):
    """Sprite sizing modes."""

    STRETCH = "stretch"
    COVER = "cover"
    CONTAIN = "contain"
    FIXED_WIDTH = "fixed-width"
    FIXED_HEIGHT = "fixed-height"


class TrackMode(Enum):
    """Object tracking modes."""

    PLANE = "plane"
    FOCUS = "focus"


class ReparentMode(Enum):
    """Object reparenting modes."""

    WORLD = "world"
    LOCAL = "local"


class Anchor(Enum):
    """Anchor positions for UI elements."""

    TOP_LEFT = "top-left"
    TOP_CENTER = "top-center"
    TOP_RIGHT = "top-right"
    CENTER_LEFT = "center-left"
    CENTER_CENTER = "center-center"
    CENTER_RIGHT = "center-right"
    BOTTOM_LEFT = "bottom-left"
    BOTTOM_CENTER = "bottom-center"
    BOTTOM_RIGHT = "bottom-right"


@dataclass(frozen=True)
class Vec2:
    """2D vector."""

    x: float
    y: float


@dataclass(frozen=True)
class Vec3:
    """3D vector."""

    x: float
    y: float
    z: float


@dataclass(frozen=True)
class Euler:
    """Euler rotation in degrees."""

    pan: float
    tilt: float
    roll: float


class ParseError(ValueError):
    """Raised when a HackVR type fails validation."""


def parse_string(value: str, optional: bool) -> str | None:
    assert value is not None
    raw = _optional_empty(value, optional)
    if raw is None:
        return None
    if raw == "":
        raise ParseError("string must be non-empty")
    return raw


def parse_zstring(value: str, optional: bool) -> str:
    assert value is not None
    _ = optional
    return value


def parse_int(value: str, optional: bool) -> int | None:
    assert value is not None
    raw = _optional_empty(value, optional)
    if raw is None:
        return None
    if not _INT_RE.fullmatch(raw):
        raise ParseError("invalid int")
    return int(raw)


def parse_float(value: str, optional: bool) -> float | None:
    assert value is not None
    raw = _optional_empty(value, optional)
    if raw is None:
        return None
    if not _FLOAT_RE.fullmatch(raw):
        raise ParseError("invalid float")
    return float(raw)


def parse_bool(value: str, optional: bool) -> bool | None:
    assert value is not None
    raw = _optional_empty(value, optional)
    if raw is None:
        return None
    if raw == "true":
        return True
    if raw == "false":
        return False
    raise ParseError("invalid bool")


def parse_vec2(value: str, optional: bool) -> Vec2 | None:
    return cast("Vec2 | None", _parse_vec(value, optional, count=_VECTOR2_COMPONENTS))


def parse_vec3(value: str, optional: bool) -> Vec3 | None:
    return cast("Vec3 | None", _parse_vec(value, optional, count=_VECTOR3_COMPONENTS))


def parse_color(value: str, optional: bool) -> Color | None:
    assert value is not None
    raw = _optional_empty(value, optional)
    if raw is None:
        return None
    if not _COLOR_RE.fullmatch(raw):
        raise ParseError("invalid color")
    return Color(raw.lower())


def parse_bytes(value: str, optional: bool, length: int) -> bytes | None:
    assert value is not None
    raw = _optional_empty(value, optional)
    if raw is None:
        return None
    expected_length = length * 2
    if len(raw) != expected_length or not _HEX_RE.fullmatch(raw):
        raise ParseError("invalid bytes")
    return bytes.fromhex(raw)


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
    _ = optional
    return AnyValue(value)


def parse_uri(value: str, optional: bool) -> URI | None:
    assert value is not None
    raw = _optional_empty(value, optional)
    if raw is None:
        return None
    if _contains_control(raw) or any(ch.isspace() for ch in raw):
        raise ParseError("invalid uri")
    parsed = urlsplit(raw)
    if not parsed.scheme:
        raise ParseError("uri must be absolute")
    return URI(raw)


def parse_userid(value: str, optional: bool) -> UserID | None:
    assert value is not None
    raw = _optional_empty(value, optional)
    if raw is None:
        return None
    if "\n" in raw:
        raise ParseError("userid contains LF")
    if raw != raw.strip():
        raise ParseError("userid has leading/trailing whitespace")
    if len(raw) >= _USER_ID_MAX_LENGTH:
        raise ParseError("userid too long")
    return UserID(raw)


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
    parsed = _parse_enum(value, optional, {member.value for member in TapKind})
    if parsed is None:
        return None
    return TapKind(parsed)


def parse_sizemode(value: str, optional: bool) -> SizeMode | None:
    parsed = _parse_enum(value, optional, {member.value for member in SizeMode})
    if parsed is None:
        return None
    return SizeMode(parsed)


def parse_track_mode(value: str, optional: bool) -> TrackMode | None:
    parsed = _parse_enum(value, optional, {member.value for member in TrackMode})
    if parsed is None:
        return None
    return TrackMode(parsed)


def parse_reparent_mode(value: str, optional: bool) -> ReparentMode | None:
    parsed = _parse_enum(value, optional, {member.value for member in ReparentMode})
    if parsed is None:
        return None
    return ReparentMode(parsed)


def parse_anchor(value: str, optional: bool) -> Anchor | None:
    parsed = _parse_enum(value, optional, {member.value for member in Anchor})
    if parsed is None:
        return None
    return Anchor(parsed)


def parse_version(value: str, optional: bool) -> Version | None:
    assert value is not None
    raw = _optional_empty(value, optional)
    if raw is None:
        return None
    match = _VERSION_RE.fullmatch(raw)
    if not match:
        raise ParseError("invalid version")
    return Version(int(match.group(1)))


def parse_euler(value: str, optional: bool) -> Euler | None:
    vector = cast("Vec3 | None", _parse_vec(value, optional, count=_VECTOR3_COMPONENTS))
    if vector is None:
        return None
    return Euler(vector.x, vector.y, vector.z)


def parse_session_token(value: str, optional: bool) -> SessionToken | None:
    assert value is not None
    raw = _optional_empty(value, optional)
    if raw is None:
        return None
    if len(raw) != _SESSION_TOKEN_LENGTH:
        raise ParseError("invalid session token length")
    if not re.fullmatch(r"[A-Za-z0-9_-]+", raw):
        raise ParseError("invalid session token characters")
    padded = raw + "=="
    decoded = base64.urlsafe_b64decode(padded)
    assert len(decoded) == _SESSION_TOKEN_BYTES_LENGTH
    return SessionToken(decoded)


def _optional_empty(value: str, optional: bool) -> str | None:
    if optional and value == "":
        return None
    return value


def _parse_identifier(value: str, optional: bool) -> str | None:
    raw = _optional_empty(value, optional)
    if raw is None:
        return None
    if _IDENTIFIER_RE.fullmatch(raw) or _RESERVED_RE.fullmatch(raw):
        return raw
    raise ParseError("invalid identifier")


def _parse_enum(value: str, optional: bool, allowed: set[str]) -> str | None:
    raw = _optional_empty(value, optional)
    if raw is None:
        return None
    if raw not in allowed:
        raise ParseError("invalid enum")
    return raw


def _parse_vec(
    value: str,
    optional: bool,
    count: Literal[2, 3],
) -> Vec2 | Vec3 | None:
    assert value is not None
    raw = _optional_empty(value, optional)
    if raw is None:
        return None
    if count == _VECTOR2_COMPONENTS:
        pattern = rf"^\(\s*({_FLOAT_BODY})\s+({_FLOAT_BODY})\s*\)$"
    else:
        pattern = rf"^\(\s*({_FLOAT_BODY})\s+({_FLOAT_BODY})\s+({_FLOAT_BODY})\s*\)$"
    match = re.fullmatch(pattern, raw)
    if not match:
        raise ParseError("invalid vector")
    numbers = [float(group) for group in match.groups()]
    if count == _VECTOR2_COMPONENTS:
        return Vec2(numbers[0], numbers[1])
    return Vec3(numbers[0], numbers[1], numbers[2])


def is_zstring_annotation(annotation: object) -> bool:
    origin = get_origin(annotation)
    if origin is Annotated:
        args = get_args(annotation)
        return bool(args) and args[0] is str and "zstring" in args[1:]
    return False


def _contains_control(value: str) -> bool:
    return any(unicodedata.category(ch) == "Cc" for ch in value)
