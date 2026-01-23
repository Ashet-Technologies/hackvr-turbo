from __future__ import annotations

import logging
import socket
from typing import Literal

import pytest

from hackvr import net
from hackvr.common import encoding
from hackvr import server as server_mod
from hackvr.server import Connection, Server
from hackvr.tools import keygen


class FakeNetStream(net.NetStream):
    def __init__(
        self,
        incoming: bytes,
        *,
        close_on_empty: bool = False,
    ) -> None:
        super().__init__()
        self._incoming = bytearray(incoming)
        self._close_on_empty = close_on_empty
        self._raise_on_recv = False
        self.sent = bytearray()
        self.closed = False

    def recv_unbuffered(self, max_bytes: int, deadline: net.Deadline) -> bytes | None:  # noqa: ARG002
        if self._raise_on_recv:
            raise ValueError("boom")
        if not self._incoming:
            return b"" if self._close_on_empty else None
        size = min(max_bytes, len(self._incoming))
        chunk = bytes(self._incoming[:size])
        del self._incoming[:size]
        return chunk

    def send(self, data: bytes) -> None:
        self.sent.extend(data)

    def close(self) -> None:
        self.closed = True


class RecordingConnection(Connection):
    def __init__(self, peer: net.Peer, token: net.ConnectionToken) -> None:
        super().__init__(peer, token)
        self.calls: list[str] = []

    def chat(self, message: str) -> None:
        self.calls.append(message)


def _make_token() -> net.ConnectionToken:
    return net.ConnectionToken(
        source_url=net.urlsplit("hackvr://example.com/world"),
        session_token=None,
        protocol="hackvr",
        is_secure=False,
    )


def _make_connection(stream: FakeNetStream) -> RecordingConnection:
    peer = net.Peer(stream)
    return RecordingConnection(peer, _make_token())


def test_server_polls_and_sends() -> None:
    chat_cmd = encoding.encode("chat", ["hello"])
    stream = FakeNetStream(chat_cmd)
    connection = _make_connection(stream)

    connection.poll()

    assert connection.calls == ["hello"]

    connection.client.request_user("prompt")
    assert bytes(stream.sent).endswith(encoding.encode("request-user", ["prompt"]))


def test_server_poll_no_data_keeps_connection() -> None:
    stream = FakeNetStream(b"")
    connection = _make_connection(stream)

    connection.poll()

    assert connection.is_connected is True


def test_server_poll_disconnects_on_close() -> None:
    stream = FakeNetStream(b"", close_on_empty=True)
    connection = _make_connection(stream)

    connection.poll()

    assert connection.is_connected is False
    assert stream.closed is True


def test_server_poll_disconnects_on_exception() -> None:
    stream = FakeNetStream(b"")
    connection = _make_connection(stream)
    stream._raise_on_recv = True

    connection.poll()

    assert connection.is_connected is False
    assert stream.closed is True


def test_server_poll_when_disconnected_is_noop() -> None:
    stream = FakeNetStream(b"")
    connection = _make_connection(stream)
    connection._connected = False

    connection.poll()

    assert connection.is_connected is False


def test_server_handle_error_logs_warning(caplog: pytest.LogCaptureFixture) -> None:
    stream = FakeNetStream(b"")
    connection = _make_connection(stream)

    caplog.set_level(logging.WARNING)
    connection.execute_command("unknown", ["command"])
    connection.handle_error("oops", "bad", [])

    warnings = [record for record in caplog.records if record.levelname == "WARNING"]
    assert len(warnings) == 2
    assert "unknown command" in warnings[0].message
    assert "oops" in warnings[1].message


class FakeNetServer(net.Server):
    def __init__(self, results: list[tuple[net.NetStream, net.ConnectionToken]]) -> None:
        super().__init__("127.0.0.1", 0, listener=None)
        self._results = list(results)
        self.closed = False

    def _accept_stream(self, deadline: net.Deadline) -> tuple[net.NetStream, net.ConnectionToken] | None:  # noqa: ARG002
        if not self._results:
            return None
        return self._results.pop(0)

    def close(self) -> None:
        self.closed = True


class DummyConnection(Connection):
    def poll(self) -> None:
        self._connected = False


class DummyServer(Server):
    def __init__(self, bindings: list[net.Server]) -> None:
        super().__init__()
        self._bindings = bindings
        self.accepted: list[Connection] = []
        self.disconnected: list[Connection] = []

    def accept_client(self, peer: net.Peer, connection_token: net.ConnectionToken) -> Connection:
        connection = DummyConnection(peer, connection_token)
        self.accepted.append(connection)
        return connection

    def handle_disconnect(self, _connection: Connection) -> None:
        self.disconnected.append(_connection)
        self.stop()


def test_server_serve_forever_accepts_and_disconnects() -> None:
    stream = FakeNetStream(b"")
    token = _make_token()
    binding = FakeNetServer([(stream, token)])
    server = DummyServer([binding])

    server.serve_forever()

    assert server.accepted
    assert server.disconnected


def test_add_binding_rolls_back_on_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    addresses = [
        (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("127.0.0.1", 9999)),
        (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("127.0.0.2", 9999)),
    ]
    monkeypatch.setattr(socket, "getaddrinfo", lambda *_args, **_kwargs: addresses)

    created: list[FakeNetServer] = []

    def _fake_create(
        _protocol: str,
        hostname: str,
        port: int,
        *,
        certificate: net.TlsServerCertificate | None = None,  # noqa: ARG001
    ) -> net.Server:
        if hostname == "127.0.0.2":
            raise OSError("boom")
        server = FakeNetServer([])
        created.append(server)
        return server

    monkeypatch.setattr(server_mod, "_create_net_server", _fake_create)

    class RollbackServer(Server):
        def accept_client(self, peer: net.Peer, connection_token: net.ConnectionToken) -> Connection:  # noqa: ARG002
            return DummyConnection(peer, connection_token)

    server = RollbackServer()
    with pytest.raises(OSError):
        server.add_binding("hackvr", "example.com", port=9999)

    assert created
    assert created[0].closed is True
    assert server._bindings == []


def test_add_binding_success_adds_bindings(monkeypatch: pytest.MonkeyPatch) -> None:
    addresses = [
        (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("127.0.0.1", 9999)),
    ]
    monkeypatch.setattr(socket, "getaddrinfo", lambda *_args, **_kwargs: addresses)

    def _fake_create(
        _protocol: str,
        _hostname: str,
        _port: int,
        *,
        certificate: net.TlsServerCertificate | None = None,  # noqa: ARG001
    ) -> net.Server:
        return FakeNetServer([])

    monkeypatch.setattr(server_mod, "_create_net_server", _fake_create)

    class BindingServer(Server):
        def accept_client(self, peer: net.Peer, connection_token: net.ConnectionToken) -> Connection:  # noqa: ARG002
            return DummyConnection(peer, connection_token)

    server = BindingServer()
    server.add_binding("hackvr", "example.com", port=9999)

    assert len(server._bindings) == 1


def test_handle_disconnect_default_noop() -> None:
    class BaseServer(Server):
        def accept_client(self, peer: net.Peer, connection_token: net.ConnectionToken) -> Connection:  # noqa: ARG002
            return DummyConnection(peer, connection_token)

    server = BaseServer()
    server.handle_disconnect(DummyConnection(net.Peer(FakeNetStream(b"")), _make_token()))


def test_accept_new_connections_skips_idle_binding() -> None:
    class IdleServer(Server):
        def accept_client(self, peer: net.Peer, connection_token: net.ConnectionToken) -> Connection:  # noqa: ARG002
            return DummyConnection(peer, connection_token)

    server = IdleServer()
    server._bindings = [FakeNetServer([])]

    server._accept_new_connections()

    assert server._connections == []


@pytest.mark.parametrize(
    ("protocol", "port"),
    [
        ("hackvr", net.HACKVR_PORT),
        ("hackvrs", net.HACKVRS_PORT),
        ("http+hackvr", 80),
        ("https+hackvr", 443),
    ],
)
def test_default_port_resolution(protocol: Literal["hackvr", "hackvrs", "http+hackvr", "https+hackvr"], port: int) -> None:
    assert server_mod._default_port(protocol) == port


def test_default_port_rejects_unknown_protocol() -> None:
    with pytest.raises(ValueError):
        server_mod._default_port("other")


def test_resolve_addresses_for_wildcard() -> None:
    assert server_mod._resolve_addresses("*", 1913) == ["0.0.0.0", "::"]


def test_resolve_addresses_for_host(monkeypatch: pytest.MonkeyPatch) -> None:
    addresses = [
        (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("127.0.0.1", 1234)),
        (socket.AF_INET6, socket.SOCK_STREAM, 0, "", ("::1", 1234, 0, 0)),
    ]
    monkeypatch.setattr(socket, "getaddrinfo", lambda *_args, **_kwargs: addresses)
    assert server_mod._resolve_addresses("localhost", 1234) == ["127.0.0.1", "::1"]


def test_resolve_addresses_raises_on_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", lambda *_args, **_kwargs: [])
    with pytest.raises(ValueError):
        server_mod._resolve_addresses("missing", 1234)


def test_create_net_server_variants() -> None:
    raw = server_mod._create_net_server("hackvr", "127.0.0.1", 0)
    http = server_mod._create_net_server("http+hackvr", "127.0.0.1", 0)
    certificate = keygen.generate_self_signed_certificate(common_name="localhost", valid_days=1)
    tls = server_mod._create_net_server("hackvrs", "127.0.0.1", 0, certificate=certificate)
    https = server_mod._create_net_server("https+hackvr", "127.0.0.1", 0, certificate=certificate)

    raw.close()
    http.close()
    tls.close()
    https.close()


def test_create_net_server_requires_certificate() -> None:
    with pytest.raises(ValueError):
        server_mod._create_net_server("hackvrs", "127.0.0.1", 0)
    with pytest.raises(ValueError):
        server_mod._create_net_server("https+hackvr", "127.0.0.1", 0)


def test_create_net_server_rejects_unknown_protocol() -> None:
    with pytest.raises(ValueError):
        server_mod._create_net_server("other", "127.0.0.1", 0)


def test_add_binding_certificate_requirements() -> None:
    class BindingServer(Server):
        def accept_client(self, peer: net.Peer, connection_token: net.ConnectionToken) -> Connection:  # noqa: ARG002
            return DummyConnection(peer, connection_token)

    server = BindingServer()
    with pytest.raises(ValueError):
        server.add_binding("hackvrs", "127.0.0.1")  # type: ignore[call-arg]
    with pytest.raises(ValueError):
        server.add_binding("https+hackvr", "127.0.0.1")  # type: ignore[call-arg]
    certificate = keygen.generate_self_signed_certificate(common_name="localhost", valid_days=1)
    with pytest.raises(ValueError):
        server.add_binding("hackvr", "127.0.0.1", certificate=certificate)  # type: ignore[call-arg]
