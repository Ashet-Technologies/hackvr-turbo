"""Atheris fuzzer for hackvr.common.globbing helpers.

Run manually:
  python tests/fuzzing/fuzz_common_globbing.py -max_total_time=10
"""

from __future__ import annotations

import os
import sys

import atheris

from hackvr.common import (
    expand,
    get_upper_expansion_limit,
    is_valid_pattern,
    is_valid_token,
    select,
)

MAX_INPUT = 4096
MAX_SCOPE = 25
MAX_TOKEN_LENGTH = 64

SEED_PATTERNS = [
    "*",
    "foo-*",
    "foo-?",
    "{a,b}-{0..2}",
    "{00..03}",
    "$global-*",
]

SEED_SCOPE = [
    "foo-1",
    "foo-2",
    "foo-3",
    "bar",
    "$global",
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

    fdp = atheris.FuzzedDataProvider(data)
    pattern = fdp.ConsumeUnicodeNoSurrogates(MAX_TOKEN_LENGTH)
    if not pattern:
        pattern = "*"

    scope_size = fdp.ConsumeIntInRange(0, MAX_SCOPE)
    scope = [
        fdp.ConsumeUnicodeNoSurrogates(MAX_TOKEN_LENGTH)
        for _ in range(scope_size)
    ]
    scope.extend(SEED_SCOPE)

    _ = is_valid_pattern(pattern)
    _ = is_valid_token(pattern)
    try:
        expansions = list(expand(pattern))
    except ValueError:
        expansions = []

    try:
        _ = get_upper_expansion_limit(pattern, match_all_count=5)
    except ValueError:
        pass

    _ = list(select(pattern, scope, key=lambda value: value))
    for token in expansions:
        _ = is_valid_token(token)


def main() -> None:
    _ensure_defaults()
    for pattern in SEED_PATTERNS:
        TestOneInput(pattern.encode("utf-8"))
    atheris.Setup(sys.argv, TestOneInput)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
