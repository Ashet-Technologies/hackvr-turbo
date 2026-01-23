"""Atheris fuzzer for hackvr.common.stream.Parser and encode().

Run manually:
  python tests/fuzzing/fuzz_common_stream.py -max_total_time=10
"""

from __future__ import annotations

import os
import sys

import atheris

from hackvr.common import Parser, encode
from hackvr.common.stream import MAX_LINE_LENGTH

MAX_INPUT = 4096
MAX_FRAMES_PER_PUSH = 32
MAX_CHUNK = 64

SEED_LINES = [
    b"hackvr-hello\tv1\thackvr://example\r\n",
    b"chat\tuser\thello\r\n",
    b"note\tline1\nline2\r\n",
    b"set-background-color\t#FF00FF\r\n",
    b"create-object\tfoo\r\n",
    b"ping\r\n",
]


def _ensure_defaults() -> None:
    max_time = os.environ.get("HACKVR_FUZZ_MAX_TIME")
    if max_time is None:
        max_time = "5"
    if max_time != "0" and not any(
        arg.startswith("-max_total_time") for arg in sys.argv[1:]
    ):
        sys.argv.append(f"-max_total_time={max_time}")
    if not any(arg.startswith("-max_len") for arg in sys.argv[1:]):
        sys.argv.append(f"-max_len={MAX_INPUT}")


def TestOneInput(data: bytes) -> None:
    if len(data) > MAX_INPUT:
        return

    parser = Parser()
    index = 0
    while index < len(data):
        chunk = data[index : index + MAX_CHUNK]
        parser.push(chunk)
        index += MAX_CHUNK

        frames = 0
        while frames < MAX_FRAMES_PER_PUSH:
            frame = parser.pull()
            if frame is None:
                break
            try:
                encoded = encode(frame[0], frame[1:])
            except ValueError:
                encoded = None
            if encoded is not None and len(encoded) <= MAX_LINE_LENGTH:
                parser.push(encoded)
            frames += 1


def main() -> None:
    _ensure_defaults()
    for seed in SEED_LINES:
        TestOneInput(seed)
    atheris.Setup(sys.argv, TestOneInput)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
