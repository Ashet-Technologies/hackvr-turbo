import base64
import random
import ssl
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, cast

import pytest
import requests
from OpenSSL import SSL

from hackvr import net
from hackvr.common import encoding, types
from hackvr.tools import keygen


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


class InsecureConnector(net.DefaultConnector):
    def __init__(self, context: SSL.Context) -> None:
        super().__init__()
        self._context = context

    def connect_tls(self, host: str, port: int, context: object | None = None) -> net.NetStream:
        return super().connect_tls(host, port, context=self._context)


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


def test_tls_certificate_generation_roundtrip_and_server(tmp_path):
    cert_path = tmp_path / "cert.pem"
    key_path = tmp_path / "key.pem"
    certificate = keygen.generate_self_signed_certificate(common_name="localhost", valid_days=1)
    certificate.save(cert_path, key_path)
    loaded = net.TlsServerCertificate.from_files(cert_path, key_path)
    assert loaded == certificate

    saved_cert_path = tmp_path / "saved-cert.pem"
    saved_key_path = tmp_path / "saved-key.pem"
    loaded.save(saved_cert_path, saved_key_path)
    reloaded = net.TlsServerCertificate.from_files(saved_cert_path, saved_key_path)
    assert reloaded == loaded

    listener = net.TlsListener("127.0.0.1", 0, reloaded)
    port = listener._sock.getsockname()[1]
    server = net.TlsServer("127.0.0.1", port, listener=listener)

    context = SSL.Context(SSL.TLS_METHOD)
    context.set_verify(SSL.VERIFY_NONE, lambda *_args: True)
    client = net.Client(connector=InsecureConnector(context), hello_timeout=1.0)

    server_peer = {}

    def _accept() -> None:
        peer, token = server.accept()
        server_peer["token"] = token
        peer.close()

    thread = threading.Thread(target=_accept, daemon=True)
    thread.start()
    token = client.connect(f"hackvrs://127.0.0.1:{port}/world")
    client.close()
    thread.join(timeout=1.0)
    server.close()

    assert token.protocol == "hackvrs"
    assert server_peer["token"].protocol == "hackvrs"


def test_client_http_hackvr_connects():
    server = net.HttpServer("127.0.0.1", 0)
    listener = cast(net.RawListener, server._listener)
    assert listener is not None
    port = listener._sock.getsockname()[1]
    client = net.Client(hello_timeout=1.0)
    received: dict[str, net.ConnectionToken] = {}

    def _accept() -> None:
        peer, token = server.accept()
        received["token"] = token
        peer.close()

    thread = threading.Thread(target=_accept, daemon=True)
    thread.start()
    token = client.connect(f"http+hackvr://127.0.0.1:{port}/world")
    client.close()
    thread.join(timeout=1.0)
    server.close()

    assert token.protocol == "http+hackvr"
    assert received["token"].protocol == "http+hackvr"


def test_client_https_hackvr_connects(tmp_path):
    certificate = keygen.generate_self_signed_certificate(common_name="localhost", valid_days=1)
    listener = net.TlsListener("127.0.0.1", 0, certificate)
    port = listener._sock.getsockname()[1]
    server = net.HttpsServer("127.0.0.1", port, listener=listener)
    context = SSL.Context(SSL.TLS_METHOD)
    context.set_verify(SSL.VERIFY_NONE, lambda *_args: True)
    client = net.Client(connector=InsecureConnector(context), hello_timeout=1.0)
    received: dict[str, net.ConnectionToken] = {}

    def _accept() -> None:
        peer, token = server.accept()
        received["token"] = token
        peer.close()

    thread = threading.Thread(target=_accept, daemon=True)
    thread.start()
    token = client.connect(f"https+hackvr://127.0.0.1:{port}/world")
    client.close()
    thread.join(timeout=1.0)
    server.close()

    assert token.protocol == "https+hackvr"
    assert received["token"].protocol == "https+hackvr"


def _start_http_server() -> tuple[HTTPServer, int, dict[str, str]]:
    captured: dict[str, str] = {}

    class _Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            captured.update({key.lower(): value for key, value in self.headers.items()})
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")

        def log_message(self, format: str, *args: Any) -> None:
            return None

    server = HTTPServer(("127.0.0.1", 0), _Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, port, captured


def _start_https_server(tmp_path) -> tuple[HTTPServer, int, dict[str, str]]:
    captured: dict[str, str] = {}
    cert_path = tmp_path / "server-cert.pem"
    key_path = tmp_path / "server-key.pem"
    certificate = keygen.generate_self_signed_certificate(common_name="localhost", valid_days=1)
    certificate.save(cert_path, key_path)

    class _Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            captured.update({key.lower(): value for key, value in self.headers.items()})
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")

        def log_message(self, format: str, *args: Any) -> None:
            return None

    server = HTTPServer(("127.0.0.1", 0), _Handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(certfile=cert_path, keyfile=key_path)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, port, captured


def test_requests_to_http_hackvr_server_fails_upgrade():
    server = net.HttpServer("127.0.0.1", 0)
    listener = cast(net.RawListener, server._listener)
    assert listener is not None
    port = listener._sock.getsockname()[1]
    results: dict[str, Exception] = {}

    def _accept() -> None:
        try:
            server.accept()
        except Exception as exc:
            results["error"] = exc

    thread = threading.Thread(target=_accept, daemon=True)
    thread.start()
    with pytest.raises(requests.RequestException):
        requests.get(f"http://127.0.0.1:{port}/world", timeout=1)
    thread.join(timeout=1.0)
    server.close()

    assert isinstance(results.get("error"), net.HandshakeError)


def test_requests_to_https_hackvr_server_fails_upgrade(tmp_path):
    certificate = keygen.generate_self_signed_certificate(common_name="localhost", valid_days=1)
    listener = net.TlsListener("127.0.0.1", 0, certificate)
    port = listener._sock.getsockname()[1]
    server = net.HttpsServer("127.0.0.1", port, listener=listener)
    results: dict[str, Exception] = {}

    def _accept() -> None:
        try:
            server.accept()
        except Exception as exc:
            results["error"] = exc

    thread = threading.Thread(target=_accept, daemon=True)
    thread.start()
    with pytest.raises(requests.RequestException):
        requests.get(f"https://127.0.0.1:{port}/world", timeout=1, verify=False)
    thread.join(timeout=1.0)
    server.close()

    assert isinstance(results.get("error"), net.HandshakeError)


def test_client_http_hackvr_rejected_by_standard_http_server():
    server, port, captured = _start_http_server()
    client = net.Client(hello_timeout=1.0)
    with pytest.raises(net.HandshakeError):
        client.connect(f"http+hackvr://127.0.0.1:{port}/world")
    client.close()
    server.shutdown()
    server.server_close()

    assert captured.get("upgrade") == "hackvr"
    assert "upgrade" in (captured.get("connection") or "").lower()


def test_client_https_hackvr_rejected_by_standard_https_server(tmp_path):
    server, port, captured = _start_https_server(tmp_path)
    context = SSL.Context(SSL.TLS_METHOD)
    context.set_verify(SSL.VERIFY_NONE, lambda *_args: True)
    client = net.Client(connector=InsecureConnector(context), hello_timeout=1.0)
    with pytest.raises(net.HandshakeError):
        client.connect(f"https+hackvr://127.0.0.1:{port}/world")
    client.close()
    server.shutdown()
    server.server_close()

    assert captured.get("upgrade") == "hackvr"
    assert "upgrade" in (captured.get("connection") or "").lower()
