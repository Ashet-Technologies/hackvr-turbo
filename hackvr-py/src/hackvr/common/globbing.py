"""Selector globbing helpers for HackVR identifiers."""

from __future__ import annotations

import re
from collections.abc import Iterable
from itertools import product
from typing import Callable, TypeVar

_T = TypeVar("_T")

_PART_RE = re.compile(r"^[A-Za-z0-9_]+$")
_TOKEN_RE = re.compile(r"^[A-Za-z0-9_]+(-[A-Za-z0-9_]+)*$")
_RESERVED_RE = re.compile(r"^\$[A-Za-z0-9_]+(-[A-Za-z0-9_]+)*$")


def is_valid_token(token: str) -> bool:
    return bool(_TOKEN_RE.fullmatch(token) or _RESERVED_RE.fullmatch(token))


def is_valid_pattern(pattern: str) -> bool:
    try:
        parts = _split_pattern(pattern)
    except ValueError:
        return False

    for index, part in enumerate(parts):
        if part in {"*", "?"}:
            continue
        if _is_group(part):
            if not _is_valid_group(part, allow_reserved=index == 0):
                return False
            continue
        if not _is_valid_literal(part, allow_reserved=index == 0):
            return False
    return True


def get_upper_expansion_limit(pattern: str, match_all_count: int) -> int:
    parts = _split_pattern(pattern)
    count = 1
    for index, part in enumerate(parts):
        if _is_group(part):
            count *= _group_size(part, allow_reserved=index == 0)
    if any(part in {"*", "?"} for part in parts):
        return count * match_all_count
    return count


def expand(pattern: str) -> Iterable[str]:
    parts = _split_pattern(pattern)
    if any(part in {"*", "?"} for part in parts):
        raise ValueError("cannot expand patterns containing wildcards")

    expanded_parts: list[list[str]] = []
    for index, part in enumerate(parts):
        if _is_group(part):
            expanded_parts.append(_expand_group(part, allow_reserved=index == 0))
        else:
            if not _is_valid_literal(part, allow_reserved=index == 0):
                raise ValueError("invalid pattern literal")
            expanded_parts.append([part])

    for combo in product(*expanded_parts):
        yield "-".join(combo)


def select(pattern: str, scope: Iterable[_T], key: Callable[[_T], str]) -> Iterable[_T]:
    if pattern == "*":
        return list(scope)

    patterns = list(_expand_patterns(pattern))
    parsed_patterns = [
        _pattern_parts(expanded) for expanded in patterns
    ]

    result: list[_T] = []
    seen = set()
    for item in scope:
        token = key(item)
        if token in seen:
            continue
        token_parts = token.split("-") if token else [""]
        for pattern_parts in parsed_patterns:
            if _matches(pattern_parts, token_parts):
                result.append(item)
                seen.add(token)
                break
    return result


def _expand_patterns(pattern: str) -> Iterable[str]:
    parts = _split_pattern(pattern)
    expanded_parts: list[list[str]] = []
    for index, part in enumerate(parts):
        if _is_group(part):
            expanded_parts.append(_expand_group(part, allow_reserved=index == 0))
        else:
            expanded_parts.append([part])
    for combo in product(*expanded_parts):
        yield "-".join(combo)


def _split_pattern(pattern: str) -> list[str]:
    if pattern == "":
        raise ValueError("empty pattern")
    parts: list[str] = []
    current: list[str] = []
    depth = 0
    for ch in pattern:
        if ch == "{" and depth == 0:
            depth = 1
            current.append(ch)
            continue
        if ch == "{" and depth > 0:
            raise ValueError("nested group")
        if ch == "}" and depth == 0:
            raise ValueError("unexpected closing brace")
        if ch == "}" and depth == 1:
            depth = 0
            current.append(ch)
            continue
        if ch == "-" and depth == 0:
            if not current:
                raise ValueError("empty part")
            parts.append("".join(current))
            current = []
            continue
        current.append(ch)
    if depth != 0:
        raise ValueError("unterminated group")
    if not current:
        raise ValueError("empty part")
    parts.append("".join(current))
    return parts


def _pattern_parts(pattern: str) -> list[str]:
    return pattern.split("-")


def _matches(pattern_parts: list[str], token_parts: list[str]) -> bool:
    pi = 0
    ti = 0
    star_index = None
    match_index = 0

    while ti < len(token_parts):
        if pi < len(pattern_parts) and pattern_parts[pi] == "*":
            star_index = pi
            match_index = ti
            pi += 1
            continue
        if pi < len(pattern_parts) and (
            pattern_parts[pi] == "?" or pattern_parts[pi] == token_parts[ti]
        ):
            pi += 1
            ti += 1
            continue
        if star_index is not None:
            pi = star_index + 1
            match_index += 1
            ti = match_index
            continue
        return False

    while pi < len(pattern_parts) and pattern_parts[pi] == "*":
        pi += 1

    return pi == len(pattern_parts)


def _is_group(part: str) -> bool:
    return part.startswith("{") and part.endswith("}")


def _is_valid_literal(part: str, allow_reserved: bool) -> bool:
    if part in {"*", "?"}:
        return True
    if allow_reserved and part.startswith("$"):
        return bool(_RESERVED_RE.fullmatch(part))
    return bool(_TOKEN_RE.fullmatch(part))


def _is_valid_group(part: str, allow_reserved: bool) -> bool:
    body = part[1:-1]
    if ".." in body:
        return _is_valid_range(body)
    items = body.split(",")
    if any(item == "" for item in items):
        return False
    for item in items:
        if not _is_valid_part(item, allow_reserved=allow_reserved):
            return False
    return True


def _is_valid_part(part: str, allow_reserved: bool) -> bool:
    if allow_reserved and part.startswith("$"):
        return bool(_RESERVED_RE.fullmatch(part))
    return bool(_PART_RE.fullmatch(part))


def _is_valid_range(body: str) -> bool:
    start, sep, end = body.partition("..")
    if sep == "":
        return False
    if not start.isdigit() or not end.isdigit():
        return False
    return True


def _expand_group(part: str, allow_reserved: bool) -> list[str]:
    body = part[1:-1]
    if ".." in body:
        return _expand_range(body)
    items = body.split(",")
    if any(item == "" for item in items):
        raise ValueError("empty group item")
    for item in items:
        if not _is_valid_part(item, allow_reserved=allow_reserved):
            raise ValueError("invalid group item")
    return items


def _expand_range(body: str) -> list[str]:
    start_str, _, end_str = body.partition("..")
    if not start_str.isdigit() or not end_str.isdigit():
        raise ValueError("invalid range")
    start = int(start_str)
    end = int(end_str)
    if start > end:
        raise ValueError("invalid range order")
    width = 0
    if (
        _has_leading_zero(start_str) or _has_leading_zero(end_str)
    ) and max(len(start_str), len(end_str)) > 1:
        width = max(len(start_str), len(end_str))
    if width:
        return [str(number).zfill(width) for number in range(start, end + 1)]
    return [str(number) for number in range(start, end + 1)]


def _group_size(part: str, allow_reserved: bool) -> int:
    body = part[1:-1]
    if ".." in body:
        start_str, _, end_str = body.partition("..")
        if not start_str.isdigit() or not end_str.isdigit():
            raise ValueError("invalid range")
        start = int(start_str)
        end = int(end_str)
        if start > end:
            raise ValueError("invalid range order")
        return end - start + 1
    items = body.split(",")
    if any(item == "" for item in items):
        raise ValueError("empty group item")
    for item in items:
        if not _is_valid_part(item, allow_reserved=allow_reserved):
            raise ValueError("invalid group item")
    return len(items)


def _has_leading_zero(value: str) -> bool:
    return len(value) > 1 and value.startswith("0")
