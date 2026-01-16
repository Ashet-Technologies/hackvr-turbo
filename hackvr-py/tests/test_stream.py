import random

from hackvr.common.stream import Parser, MAX_LINE_LENGTH


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


def test_parser_fuzz_inputs():
    parser = Parser()
    rng = random.Random(1337)
    for _ in range(50):
        size = rng.randint(0, 256)
        data = bytes(rng.getrandbits(8) for _ in range(size))
        parser.push(data)
        while parser.pull() is not None:
            pass
