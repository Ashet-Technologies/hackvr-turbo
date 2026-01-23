"""Atheris fuzzer for hackvr.common.types parsing helpers.

Run manually:
  python tests/fuzzing/fuzz_common_types.py -max_total_time=10
"""

from __future__ import annotations

import base64
import os
import sys

import atheris

from hackvr.common import (
    bytes_parser,
    is_zstring_annotation,
    parse_anchor,
    parse_any,
    parse_bool,
    parse_bytes,
    parse_bytes16,
    parse_bytes32,
    parse_bytes64,
    parse_color,
    parse_euler,
    parse_float,
    parse_geom,
    parse_int,
    parse_intent,
    parse_object,
    parse_reparent_mode,
    parse_session_token,
    parse_sizemode,
    parse_string,
    parse_tag,
    parse_tapkind,
    parse_track_mode,
    parse_uri,
    parse_userid,
    parse_vec2,
    parse_vec3,
    parse_version,
    parse_zstring,
)
from hackvr.common.types import ParseError, ZString

MAX_INPUT = 4096
MAX_TEXT = 64
MAX_CASES = 25

SEED_VALUES = [
    "0",
    "-1.5",
    "true",
    "(1 2)",
    "(1 2 3)",
    "#FF00FF",
    "ff" * 16,
    "ff" * 32,
    "ff" * 64,
    "https://example.com",
    "User42",
    "foo-bar",
    "$global",
    "primary",
    "cover",
    "focus",
    "local",
    "top-left",
    "v1",
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


def _consume_text(fdp: atheris.FuzzedDataProvider, max_len: int = MAX_TEXT) -> str:
    text = fdp.ConsumeUnicodeNoSurrogates(max_len)
    return text


def TestOneInput(data: bytes) -> None:
    if len(data) > MAX_INPUT:
        return

    fdp = atheris.FuzzedDataProvider(data)
    for _ in range(MAX_CASES):
        choice = fdp.ConsumeIntInRange(0, 20)
        optional = fdp.ConsumeBool()
        value = _consume_text(fdp)

        try:
            if choice == 0:
                parse_string(value, optional)
            elif choice == 1:
                parse_zstring(value, optional)
            elif choice == 2:
                parse_int(value, optional)
            elif choice == 3:
                parse_float(value, optional)
            elif choice == 4:
                parse_bool(value, optional)
            elif choice == 5:
                parse_vec2(value, optional)
            elif choice == 6:
                parse_vec3(value, optional)
            elif choice == 7:
                parse_color(value, optional)
            elif choice == 8:
                parse_any(value, optional)
            elif choice == 9:
                parse_uri(value, optional)
            elif choice == 10:
                parse_userid(value, optional)
            elif choice == 11:
                parse_object(value, optional)
            elif choice == 12:
                parse_geom(value, optional)
            elif choice == 13:
                parse_intent(value, optional)
            elif choice == 14:
                parse_tag(value, optional)
            elif choice == 15:
                parse_tapkind(value, optional)
            elif choice == 16:
                parse_sizemode(value, optional)
            elif choice == 17:
                parse_track_mode(value, optional)
            elif choice == 18:
                parse_reparent_mode(value, optional)
            elif choice == 19:
                parse_anchor(value, optional)
            else:
                parse_version(value, optional)
        except ParseError:
            pass

        hex_bytes = fdp.ConsumeBytes(32)
        if hex_bytes:
            hex_value = hex_bytes.hex()
            try:
                parse_bytes(hex_value, optional, min(16, len(hex_bytes)))
            except ParseError:
                pass

        token_bytes = fdp.ConsumeBytes(32)
        if len(token_bytes) == 32:
            token = base64.urlsafe_b64encode(token_bytes).decode("ascii").rstrip("=")
            try:
                parse_session_token(token, optional)
            except ParseError:
                pass

        parser = bytes_parser(16)
        try:
            parser(fdp.ConsumeBytes(16).hex(), optional)
        except ParseError:
            pass

        _ = is_zstring_annotation(ZString)


def main() -> None:
    _ensure_defaults()
    for seed in SEED_VALUES:
        TestOneInput(seed.encode("utf-8"))
    atheris.Setup(sys.argv, TestOneInput)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
