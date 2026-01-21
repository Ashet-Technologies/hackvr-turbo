import base64
import random
import time

import pytest

from hackvr import net
from hackvr.common import encoding, types


class FakeNetStream(net.NetStream):
    def __init__(
        self,
        incoming: bytes,
        chunk_sizes: list[int] | None = None,
        sleep_s: float = 0.0,
    ) -> None:
        super().__init__()
        self._incoming = bytearray(incoming)
        self._chunk_sizes = list(chunk_sizes or [])
        self._sleep_s = sleep_s
        self.sent = bytearray()
        self.closed = False
        self.recv_unbuffered_calls = 0

    def recv_unbuffered(self, max_bytes: int, deadline: net.Deadline) -> bytes | None:
        if self._sleep_s > 0:
            time.sleep(self._sleep_s)
        self.recv_unbuffered_calls += 1
        if not self._incoming:
            return None
        if self._chunk_sizes:
            next_size = self._chunk_sizes.pop(0)
            if next_size == 0:
                return None
            size = min(next_size, max_bytes, len(self._incoming))
        else:
            size = min(max_bytes, len(self._incoming))
        chunk = bytes(self._incoming[:size])
        del self._incoming[:size]
        return chunk

    def send(self, data: bytes) -> None:
        self.sent.extend(data)

    def close(self) -> None:
        self.closed = True


class FakeConnector:
    def __init__(self, stream: FakeNetStream) -> None:
        self.stream = stream
        self.calls: list[tuple[str, str, int]] = []

    def connect_raw(self, host: str, port: int) -> net.NetStream:
        self.calls.append(("raw", host, port))
        return self.stream

    def connect_tls(self, host: str, port: int, context: object | None = None) -> net.NetStream:
        self.calls.append(("tls", host, port))
        return self.stream


class FakeListener:
    def __init__(self, stream: FakeNetStream) -> None:
        self.stream = stream

    def accept(self) -> tuple[net.NetStream, tuple[str, int]]:
        return self.stream, ("127.0.0.1", 12345)

    def close(self) -> None:
        return None


def _make_session_token() -> tuple[types.SessionToken, str]:
    raw = b"\x01" * 32
    token = types.SessionToken(raw)
    encoded = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
    return token, encoded


def test_client_hackvr_sends_hello_and_parses_response():
    token, encoded = _make_session_token()
    server_hello = encoding.encode("hackvr-hello", ["v1"])
    stream = FakeNetStream(server_hello)
    connector = FakeConnector(stream)
    client = net.Client(connector=connector)

    token_info = client.connect(f"hackvr://example.com/world#{encoded}")

    assert token_info.session_token == token
    assert token_info.source_url.geturl() == "hackvr://example.com/world"
    assert token_info.protocol == "hackvr"
    assert token_info.is_secure is False
    assert connector.calls == [("raw", "example.com", net.HACKVR_PORT)]
    expected = encoding.encode("hackvr-hello", ["v1", "hackvr://example.com/world", encoded])
    assert bytes(stream.sent) == expected


def test_raw_server_accepts_client_hello_and_responds():
    token, encoded = _make_session_token()
    client_hello = encoding.encode(
        "hackvr-hello",
        ["v1", "hackvr://example.com/world", encoded],
    )
    stream = FakeNetStream(client_hello)
    listener = FakeListener(stream)
    server = net.RawServer("127.0.0.1", listener=listener)

    peer, token_info = server.accept()

    assert isinstance(peer, net.Peer)
    assert token_info.source_url.geturl() == "hackvr://example.com/world"
    assert token_info.session_token == token
    assert token_info.protocol == "hackvr"
    assert token_info.is_secure is False
    expected = encoding.encode("hackvr-hello", ["v1"])
    assert bytes(stream.sent) == expected


def test_receive_line_timeout_when_no_data():
    stream = FakeNetStream(b"")
    with pytest.raises(TimeoutError):
        net._receive_line(stream, net.Deadline.from_now(s=0.01))


def test_receive_line_invalid_command_name():
    stream = FakeNetStream(b"bad\x00name\r\n")
    with pytest.raises(net.HandshakeError):
        net._receive_command(stream, net.Deadline.from_now(s=0.1))


def test_receive_line_unterminated_then_closed():
    stream = FakeNetStream(b"hackvr-hello", chunk_sizes=[5, 5, 0])
    with pytest.raises(TimeoutError):
        net._receive_line(stream, net.Deadline.from_now(s=0.01))


def test_http_header_trailing_spaces_are_accepted():
    request = (
        "GET /world HTTP/1.1\r\n"
        "Host: example.com\r\n"
        "Connection: upgrade  \r\n"
        "Upgrade: hackvr  \r\n"
        "HackVr-Version: v1\r\n"
        "\r\n"
    ).encode("iso-8859-1")
    stream = FakeNetStream(request)
    parsed = net._receive_http_request(stream, net.Deadline.from_now(s=0.1))
    assert parsed.host == "example.com"
    assert parsed.path == "/world"


def test_http_read_until_keeps_remainder():
    payload = (
        "GET /world HTTP/1.1\r\n"
        "Host: example.com\r\n"
        "Connection: upgrade\r\n"
        "Upgrade: hackvr\r\n"
        "HackVr-Version: v1\r\n"
        "\r\n"
        "extra-bytes"
    ).encode("iso-8859-1")
    stream = FakeNetStream(payload)
    net._receive_http_request(stream, net.Deadline.from_now(s=0.1))
    remainder = stream.recv(32, deadline=net.Deadline.INSTANT)
    assert remainder == b"extra-bytes"


def test_handshake_keeps_remainder_after_hello():
    payload = encoding.encode("hackvr-hello", ["v1"]) + b"tail"
    stream = FakeNetStream(payload)
    net._receive_server_hello(stream, net.Deadline.from_now(s=0.1))
    remainder = stream.recv(8, deadline=net.Deadline.INSTANT)
    assert remainder == b"tail"


def test_fragmented_reads_randomized_for_http_and_hello():
    rng = random.Random(1337)
    hello = encoding.encode("hackvr-hello", ["v1"])
    http_request = (
        "GET /world HTTP/1.1\r\n"
        "Host: example.com\r\n"
        "Connection: upgrade\r\n"
        "Upgrade: hackvr\r\n"
        "HackVr-Version: v1\r\n"
        "\r\n"
    ).encode("iso-8859-1")
    combined = hello + http_request
    sizes = [rng.randint(1, 4) for _ in range(len(combined))]
    stream = FakeNetStream(combined, chunk_sizes=sizes)
    net._receive_server_hello(stream, net.Deadline.from_now(s=0.5))
    request = net._receive_http_request(stream, net.Deadline.from_now(s=0.5))
    assert request.host == "example.com"


def test_recv_buffer_avoids_extra_unbuffered_calls():
    payload = b"abcdefghij"
    stream = FakeNetStream(payload)
    first = stream.recv(5, deadline=net.Deadline.INSTANT)
    assert first == b"abcde"
    calls_after_first = stream.recv_unbuffered_calls
    second = stream.recv(5, deadline=net.Deadline.INSTANT)
    assert second == b"fghij"
    assert stream.recv_unbuffered_calls == calls_after_first


def test_recv_instant_deadline_reads_available_data():
    stream = FakeNetStream(b"hello")
    data = stream.recv(5, deadline=net.Deadline.INSTANT)
    assert data == b"hello"


def test_http_read_until_times_out_with_slow_reads():
    payload = b"GET /world HTTP/1.1\r\nHost: example.com\r\n"
    stream = FakeNetStream(payload, chunk_sizes=[4, 4, 4, 4], sleep_s=0.02)
    with pytest.raises(TimeoutError):
        net._receive_http_request(stream, net.Deadline.from_now(s=0.01))
