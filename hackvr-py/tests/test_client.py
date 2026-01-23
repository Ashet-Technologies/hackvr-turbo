from __future__ import annotations

import logging

import pytest

from hackvr import net
from hackvr.client import Client
from hackvr.common import encoding, types


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


class FakeConnector:
    def __init__(self, stream: FakeNetStream) -> None:
        self.stream = stream

    def connect_raw(self, host: str, port: int) -> net.NetStream:  # noqa: ARG002
        return self.stream

    def connect_tls(self, host: str, port: int, context: object | None = None) -> net.NetStream:  # noqa: ARG002
        return self.stream


class RecordingClient(Client):
    def __init__(self, net_client: net.Client) -> None:
        super().__init__(net_client=net_client)
        self.calls: list[tuple[types.UserID, str]] = []

    def chat(self, user: types.UserID, message: str) -> None:
        self.calls.append((user, message))


def _hello_bytes() -> bytes:
    return encoding.encode("hackvr-hello", ["v1"])


def _connect_client(stream: FakeNetStream) -> RecordingClient:
    connector = FakeConnector(stream)
    net_client = net.Client(connector=connector)
    client = RecordingClient(net_client)
    client.connect("hackvr://example.com/world")
    return client


def test_client_connects_polls_and_sends() -> None:
    chat_cmd = encoding.encode("chat", ["user-1", "hello"])
    stream = FakeNetStream(_hello_bytes() + chat_cmd)
    client = _connect_client(stream)

    assert client.is_connected is True
    assert bytes(stream.sent) == encoding.encode("hackvr-hello", ["v1", "hackvr://example.com/world"])

    client.poll()

    assert client.calls == [(types.UserID("user-1"), "hello")]

    client.server.set_user(types.UserID("user-1"))
    assert bytes(stream.sent).endswith(encoding.encode("set-user", ["user-1"]))


def test_client_poll_no_data_keeps_connection() -> None:
    stream = FakeNetStream(_hello_bytes())
    client = _connect_client(stream)

    client.poll()

    assert client.is_connected is True


def test_client_poll_disconnects_on_close() -> None:
    stream = FakeNetStream(_hello_bytes(), close_on_empty=True)
    client = _connect_client(stream)

    client.poll()

    assert client.is_connected is False
    assert stream.closed is True


def test_client_poll_disconnects_on_exception() -> None:
    stream = FakeNetStream(_hello_bytes())
    client = _connect_client(stream)
    stream._raise_on_recv = True

    client.poll()

    assert client.is_connected is False
    assert stream.closed is True


def test_client_poll_before_connect_is_noop() -> None:
    client = RecordingClient(net.Client(connector=FakeConnector(FakeNetStream(b""))))

    client.poll()

    assert client.is_connected is False


def test_client_handle_error_logs_warning(caplog: pytest.LogCaptureFixture) -> None:
    stream = FakeNetStream(_hello_bytes())
    client = _connect_client(stream)

    caplog.set_level(logging.WARNING)
    client.execute_command("unknown", ["command"])
    client.handle_error("oops", "bad", [])

    warnings = [record for record in caplog.records if record.levelname == "WARNING"]
    assert len(warnings) == 2
    assert "unknown command" in warnings[0].message
    assert "oops" in warnings[1].message
