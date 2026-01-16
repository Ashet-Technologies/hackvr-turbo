"""Type validators and parsers for HackVR protocol values."""

from __future__ import annotations

import base64
import re
import unicodedata
from typing import Callable
from urllib.parse import urlsplit

_FLOAT_BODY = r"-?\d+(?:\.\d+)?"
_FLOAT_RE = re.compile(rf"^{_FLOAT_BODY}$")
_INT_RE = re.compile(r"^(0|[1-9][0-9]*)$")
_VERSION_RE = re.compile(r"^v([1-9][0-9]*)$")
_HEX_RE = re.compile(r"^[0-9a-fA-F]+$")
_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9_]+(-[A-Za-z0-9_]+)*$")
_RESERVED_RE = re.compile(r"^\$[A-Za-z0-9_]+(-[A-Za-z0-9_]+)*$")


class ParseError(ValueError):
    """Raised when a HackVR type fails validation."""


def parse_string(value: str, optional: bool) -> str | None:
    value = _optional_empty(value, optional, allow_empty=False)
    if value is None:
        return None
    if value == "":
        raise ParseError("string must be non-empty")
    return value


def parse_zstring(value: str, optional: bool) -> str | None:
    value = _optional_empty(value, optional, allow_empty=True)
    if value is None:
        return None
    return value


def parse_int(value: str, optional: bool) -> int | None:
    value = _optional_empty(value, optional, allow_empty=False)
    if value is None:
        return None
    if not _INT_RE.fullmatch(value):
        raise ParseError("invalid int")
    return int(value)


def parse_float(value: str, optional: bool) -> float | None:
    value = _optional_empty(value, optional, allow_empty=False)
    if value is None:
        return None
    if not _FLOAT_RE.fullmatch(value):
        raise ParseError("invalid float")
    return float(value)


def parse_bool(value: str, optional: bool) -> bool | None:
    value = _optional_empty(value, optional, allow_empty=False)
    if value is None:
        return None
    if value == "true":
        return True
    if value == "false":
        return False
    raise ParseError("invalid bool")


def parse_vec2(value: str, optional: bool) -> tuple[float, float] | None:
    return _parse_vec(value, optional, count=2)


def parse_vec3(value: str, optional: bool) -> tuple[float, float, float] | None:
    return _parse_vec(value, optional, count=3)


def parse_color(value: str, optional: bool) -> str | None:
    value = _optional_empty(value, optional, allow_empty=False)
    if value is None:
        return None
    if not _COLOR_RE.fullmatch(value):
        raise ParseError("invalid color")
    return value.lower()


def parse_bytes(value: str, optional: bool, length: int) -> bytes | None:
    value = _optional_empty(value, optional, allow_empty=False)
    if value is None:
        return None
    expected_length = length * 2
    if len(value) != expected_length or not _HEX_RE.fullmatch(value):
        raise ParseError("invalid bytes")
    return bytes.fromhex(value)


def bytes_parser(length: int) -> Callable[[str, bool], bytes | None]:
    def _parser(value: str, optional: bool) -> bytes | None:
        return parse_bytes(value, optional, length)

    return _parser


def parse_any(value: str, optional: bool) -> str | None:
    value = _optional_empty(value, optional, allow_empty=True)
    if value is None:
        return None
    return value


def parse_uri(value: str, optional: bool) -> str | None:
    value = _optional_empty(value, optional, allow_empty=False)
    if value is None:
        return None
    if _contains_control(value) or any(ch.isspace() for ch in value):
        raise ParseError("invalid uri")
    parsed = urlsplit(value)
    if not parsed.scheme:
        raise ParseError("uri must be absolute")
    return value


def parse_userid(value: str, optional: bool) -> str | None:
    value = _optional_empty(value, optional, allow_empty=False)
    if value is None:
        return None
    if "\n" in value:
        raise ParseError("userid contains LF")
    if value != value.strip():
        raise ParseError("userid has leading/trailing whitespace")
    if len(value) >= 128:
        raise ParseError("userid too long")
    return value


def parse_object(value: str, optional: bool) -> str | None:
    return _parse_identifier(value, optional)


def parse_geom(value: str, optional: bool) -> str | None:
    return _parse_identifier(value, optional)


def parse_intent(value: str, optional: bool) -> str | None:
    return _parse_identifier(value, optional)


def parse_tag(value: str, optional: bool) -> str | None:
    return _parse_identifier(value, optional)


def parse_tapkind(value: str, optional: bool) -> str | None:
    return _parse_enum(value, optional, {"primary", "secondary"})


def parse_sizemode(value: str, optional: bool) -> str | None:
    return _parse_enum(value, optional, {"stretch", "cover", "contain", "fixed-width", "fixed-height"})


def parse_track_mode(value: str, optional: bool) -> str | None:
    return _parse_enum(value, optional, {"plane", "focus"})


def parse_reparent_mode(value: str, optional: bool) -> str | None:
    return _parse_enum(value, optional, {"world", "local"})


def parse_anchor(value: str, optional: bool) -> str | None:
    return _parse_enum(
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


def parse_version(value: str, optional: bool) -> int | None:
    value = _optional_empty(value, optional, allow_empty=False)
    if value is None:
        return None
    match = _VERSION_RE.fullmatch(value)
    if not match:
        raise ParseError("invalid version")
    return int(match.group(1))


def parse_euler(value: str, optional: bool) -> tuple[float, float, float] | None:
    return parse_vec3(value, optional)


def parse_session_token(value: str, optional: bool) -> bytes | None:
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
    return decoded


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
    numbers = tuple(float(group) for group in match.groups())
    return numbers


def _contains_control(value: str) -> bool:
    return any(unicodedata.category(ch) == "Cc" for ch in value)
