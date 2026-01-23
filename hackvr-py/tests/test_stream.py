import random

from hackvr.common import encoding
from hackvr.common.stream import MAX_LINE_LENGTH, Parser


def test_parser_reads_lines_with_tabs():
    parser = Parser()
    parser.push(b"chat\tuser\thello\r\n")
    assert parser.pull() == ["chat", "user", "hello"]
    assert parser.pull() is None


def test_parser_allows_lf_in_param():
    parser = Parser()
    parser.push("note\tline1\nline2\r\n".encode("utf-8"))
    assert parser.pull() == ["note", "line1\nline2"]


def test_parser_discards_invalid_utf8():
    parser = Parser()
    parser.push(b"chat\t\xff\r\n")
    assert parser.pull() is None


def test_parser_discards_stray_cr():
    parser = Parser()
    parser.push(b"chat\tbad\rdata\r\n")
    assert parser.pull() is None


def test_parser_discards_control_chars_in_name():
    parser = Parser()
    parser.push(b"ch\x00at\tmsg\r\n")
    assert parser.pull() is None


def test_parser_discards_overlong_lines():
    parser = Parser()
    payload = b"a" * (MAX_LINE_LENGTH + 5)
    parser.push(payload)
    parser.push(b"\r\nnext\tcmd\r\n")
    assert parser.pull() == ["next", "cmd"]


def test_parser_ignores_overlength_line_with_terminator():
    parser = Parser()
    line = b"a" * (MAX_LINE_LENGTH - 1)
    parser.push(line + b"\r\n")
    assert parser.pull() is None


def test_parser_ignores_overlength_line_then_parses_following():
    parser = Parser()
    line = b"a" * (MAX_LINE_LENGTH - 1)
    parser.push(line + b"\r\n")
    parser.push(b"ok\tvalue\r\n")
    assert parser.pull() == ["ok", "value"]


def test_parser_handles_consecutive_commands():
    parser = Parser()
    parser.push(b"a\tb\r\nc\r\n")
    assert parser.pull() == ["a", "b"]
    assert parser.pull() == ["c"]


def test_parser_handles_large_push():
    parser = Parser()
    parser.push(b"a" * 4096)
    parser.push(b"\r\nping\r\n")
    assert parser.pull() == ["ping"]


def test_parser_ignores_empty_push():
    parser = Parser()
    parser.push(b"")
    assert parser.pull() is None


def test_parser_discards_empty_name_and_invalid_params():
    parser = Parser()
    parser.push(b"\tvalue\r\n")
    parser.push(b"cmd\tbad\x00\r\n")
    assert parser.pull() is None


def test_parser_discards_empty_line():
    parser = Parser()
    parser.push(b"\r\n")
    assert parser.pull() is None


def test_parser_trims_overflowed_buffer_then_recovers():
    parser = Parser()
    parser.push(b"a" * (MAX_LINE_LENGTH + 1))
    parser.push(b"b" * 10)
    parser.push(b"\r\nok\r\n")
    assert parser.pull() == ["ok"]


def test_parser_fuzz_inputs():
    parser = Parser()
    rng = random.Random(1337)
    for _ in range(50):
        size = rng.randint(0, 256)
        data = bytes(rng.getrandbits(8) for _ in range(size))
        parser.push(data)
        while parser.pull() is not None:
            pass


def test_parser_handles_large_valid_block():
    parser = Parser()
    rng = random.Random(4242)
    expected: list[list[str]] = []
    buffer = bytearray()
    while len(buffer) < 10240:
        cmd = f"cmd{rng.randint(0, 9)}"
        param_count = rng.randint(0, 5)
        params = [f"p{param_index}-{cmd}" for param_index in range(param_count)]
        buffer.extend(encoding.encode(cmd, params))
        expected.append([cmd, *params])

    parser.push(bytes(buffer))

    received = []
    while True:
        parts = parser.pull()
        if parts is None:
            break
        received.append(parts)

    assert received == expected
