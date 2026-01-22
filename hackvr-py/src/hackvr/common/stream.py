"""Streaming parser for the HackVR line protocol."""

from __future__ import annotations

import unicodedata
from collections import deque

MAX_LINE_LENGTH = 1024


class Parser:
    """Incremental parser for CRLF-terminated HackVR commands."""

    def __init__(self) -> None:
        self._buffer = bytearray()
        self._queue: deque[list[str]] = deque()
        self._overflowed = False

    def push(self, data: bytes) -> None:
        if not data:
            return
        self._buffer.extend(data)
        self._parse_buffer()

    def pull(self) -> list[str] | None:
        if not self._queue:
            return None
        return self._queue.popleft()

    def _parse_buffer(self) -> None:
        while True:
            if self._overflowed and len(self._buffer) > MAX_LINE_LENGTH:
                del self._buffer[: len(self._buffer) - MAX_LINE_LENGTH]
            if not self._overflowed and len(self._buffer) > MAX_LINE_LENGTH:
                self._overflowed = True
                del self._buffer[: len(self._buffer) - MAX_LINE_LENGTH]

            assert len(self._buffer) <= MAX_LINE_LENGTH
            if self._overflowed:
                terminator = self._buffer.find(b"\r\n")
                if terminator == -1:
                    return
                del self._buffer[: terminator + 2]
                self._overflowed = False
                continue

            terminator = self._buffer.find(b"\r\n")
            if terminator == -1:
                assert len(self._buffer) <= MAX_LINE_LENGTH
                return

            assert terminator + 2 <= MAX_LINE_LENGTH

            line_bytes = bytes(self._buffer[:terminator])
            del self._buffer[: terminator + 2]

            if b"\r" in line_bytes:
                continue

            try:
                line = line_bytes.decode("utf-8")
            except UnicodeDecodeError:
                continue

            if not line:
                continue

            parts = line.split("\t")
            name = parts[0]
            if not _is_valid_name(name):
                continue
            if any(not _is_valid_param(param) for param in parts[1:]):
                continue

            self._queue.append(parts)


def _is_valid_name(value: str) -> bool:
    if not value:
        return False
    return not _contains_control(value)


def _is_valid_param(value: str) -> bool:
    return all(
        not (unicodedata.category(ch) == "Cc" and ch != "\n")
        for ch in value
    )


def _contains_control(value: str) -> bool:
    return any(unicodedata.category(ch) == "Cc" for ch in value)
