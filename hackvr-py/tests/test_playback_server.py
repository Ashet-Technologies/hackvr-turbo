import io
import json
import socket
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from OpenSSL import SSL

from hackvr import net
from hackvr.base import ConnectionToken
from hackvr.common import encoding
from hackvr.tools import keygen, playback_server


class FakeStream(net.NetStream):
    def __init__(self) -> None:
        super().__init__()
        self.sent: list[bytes] = []
        self.closed = False

    def recv_unbuffered(self, max_bytes: int, deadline: net.Deadline) -> bytes | None:  # noqa: ARG002
        return None

    def send(self, data: bytes) -> None:
        self.sent.append(data)

    def close(self) -> None:
        self.closed = True


class FakeServer:
    def __init__(self, stream: net.NetStream, token: ConnectionToken) -> None:
        self._stream = stream
        self._token = token
        self.accept_calls = 0
        self.closed = False

    def _accept_stream(self) -> tuple[net.NetStream, ConnectionToken]:
        self.accept_calls += 1
        return self._stream, self._token

    def close(self) -> None:
        self.closed = True


class InsecureConnector(net.DefaultConnector):
    def __init__(self, context: SSL.Context) -> None:
        super().__init__()
        self._context = context

    def connect_tls(self, host: str, port: int, context: object | None = None) -> net.NetStream:
        return super().connect_tls(host, port, context=self._context)


def _free_port() -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def _connect_with_retry(url: str, connector: net.DefaultConnector, timeout_s: float = 2.0) -> net.Client:
    client = net.Client(connector=connector, hello_timeout=1.0)
    deadline = time.monotonic() + timeout_s
    while True:
        try:
            client.connect(url)
            return client
        except (OSError, net.HandshakeError, TimeoutError, SSL.Error):
            if time.monotonic() >= deadline:
                raise
            time.sleep(0.01)


def _write_json(tmp_path: Path, payload: object) -> Path:
    path = tmp_path / "playback.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_load_commands_valid(tmp_path: Path) -> None:
    path = _write_json(
        tmp_path,
        [
            {"cmd": ["create-geometry", "foo"], "delay": 1.0},
            {"cmd": ["destroy-geometry", "foo"], "delay": 0},
        ],
    )

    commands = playback_server._load_commands(path)

    assert len(commands) == 2
    assert commands[0] == playback_server.PlaybackCommand(cmd=["create-geometry", "foo"], delay=1.0)
    assert commands[1] == playback_server.PlaybackCommand(cmd=["destroy-geometry", "foo"], delay=0.0)


def test_load_commands_negative_delay(tmp_path: Path) -> None:
    path = _write_json(tmp_path, [{"cmd": ["create-geometry", "foo"], "delay": -1}])

    with pytest.raises(ValueError, match="delay must be non-negative"):
        playback_server._load_commands(path)


def test_dispatcher_logs_error() -> None:
    logs: list[str] = []

    def log_error(message: str) -> None:
        logs.append(message)

    dispatcher = playback_server._PlaybackDispatcher(log_error=log_error)

    dispatcher.handle_error("chat", "bad input", ["oops"])

    assert logs == ["invalid chat ['oops'] (bad input)"]


def test_send_commands_writes_encoded(monkeypatch: pytest.MonkeyPatch) -> None:
    stream = FakeStream()
    commands = [
        playback_server.PlaybackCommand(cmd=["create-geometry", "foo"], delay=0.0),
        playback_server.PlaybackCommand(cmd=["destroy-geometry", "foo"], delay=0.0),
    ]
    output = io.StringIO()

    monkeypatch.setattr(playback_server.time, "sleep", lambda _delay: None)
    monkeypatch.setattr(playback_server.time, "monotonic_ns", lambda: 0)

    connection = playback_server._PlaybackConnection(
        stream,
        ConnectionToken(
            source_url=urlsplit("hackvr://example.com/world"),
            session_token=None,
            protocol="hackvr",
            is_secure=False,
        ),
        commands,
        output,
        name="client-1",
    )

    connection._send_commands()

    assert stream.sent == [
        encoding.encode("create-geometry", ["foo"]),
        encoding.encode("destroy-geometry", ["foo"]),
    ]


def test_oneshot_server_stops_after_disconnect(monkeypatch: pytest.MonkeyPatch) -> None:
    stream = FakeStream()
    token = ConnectionToken(
        source_url=urlsplit("hackvr://example.com/world"),
        session_token=None,
        protocol="hackvr",
        is_secure=False,
    )
    fake_server = FakeServer(stream, token)

    monkeypatch.setattr(playback_server, "_create_server", lambda *_args, **_kwargs: fake_server)
    monkeypatch.setattr(playback_server.time, "monotonic_ns", lambda: 0)

    output = io.StringIO()
    server = playback_server.PlaybackServer(
        host="127.0.0.1",
        port=1234,
        scheme="hackvr",
        commands=[],
        output=output,
        oneshot=True,
    )

    server.serve_forever()

    assert fake_server.accept_calls == 1
    assert fake_server.closed is True
    assert stream.closed is True


def test_main_runs_oneshot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    json_path = _write_json(tmp_path, [])
    monkeypatch.setattr(playback_server.sys, "stdout", io.StringIO())

    schemes = [
        ("hackvr", False),
        ("hackvrs", True),
        ("http+hackvr", False),
        ("https+hackvr", True),
    ]

    for scheme, uses_tls in schemes:
        port = _free_port()
        args = [
            str(json_path),
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--scheme",
            scheme,
            "--oneshot",
        ]
        if uses_tls:
            certificate = keygen.generate_self_signed_certificate(common_name="localhost", valid_days=1)
            cert_path = tmp_path / f"{scheme}-cert.pem"
            key_path = tmp_path / f"{scheme}-key.pem"
            certificate.save(cert_path, key_path)
            args.extend(["--tls-cert", str(cert_path), "--tls-key", str(key_path)])

        errors: list[BaseException] = []

        def _run_server() -> None:
            try:
                playback_server.main(args)
            except BaseException as exc:
                errors.append(exc)

        thread = threading.Thread(target=_run_server, daemon=True)
        thread.start()

        url = f"{scheme}://127.0.0.1:{port}/world"
        if uses_tls:
            context = SSL.Context(SSL.TLS_METHOD)
            context.set_verify(SSL.VERIFY_NONE, lambda *_args: True)
            connector: net.DefaultConnector = InsecureConnector(context)
        else:
            connector = net.DefaultConnector()
        client = _connect_with_retry(url, connector)
        client.close()

        thread.join(timeout=5.0)
        assert not thread.is_alive()
        assert not errors
