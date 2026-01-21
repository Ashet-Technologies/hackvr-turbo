"""Byte stream encoder for HackVR commands."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .stream import MAX_LINE_LENGTH, _is_valid_name, _is_valid_param

if TYPE_CHECKING:
    from collections.abc import Sequence


def encode(cmd: str, params: Sequence[str]) -> bytes:
    normalized_cmd = _normalize(cmd)
    normalized_params = [_normalize(param) for param in params]

    if not _is_valid_name(normalized_cmd):
        raise ValueError("Invalid command name")
    if any(not _is_valid_param(param) for param in normalized_params):
        raise ValueError("Invalid parameter")

    line = "\t".join([normalized_cmd, *normalized_params]) + "\r\n"
    data = line.encode("utf-8")
    if len(data) > MAX_LINE_LENGTH:
        raise ValueError("Command exceeds maximum length")
    return data


def _normalize(value: str) -> str:
    return value.replace("\r\n", "\n").replace("\r", "\n")
