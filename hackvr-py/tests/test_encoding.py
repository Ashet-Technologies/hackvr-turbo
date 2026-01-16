import pytest

from hackvr.common.encoding import encode


def test_encode_normalizes_crlf_in_params():
    data = encode("chat", ["line1\r\nline2"])
    assert data == b"chat\tline1\nline2\r\n"


def test_encode_rejects_invalid_name():
    with pytest.raises(ValueError):
        encode("bad\tname", [])


def test_encode_rejects_control_chars_in_param():
    with pytest.raises(ValueError):
        encode("chat", ["bad\x00param"])


def test_encode_rejects_too_long_line():
    with pytest.raises(ValueError):
        encode("a", ["b" * 2000])
