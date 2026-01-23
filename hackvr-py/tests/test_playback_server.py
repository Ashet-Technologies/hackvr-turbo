import io
import json
import socket
import threading
import time
from pathlib import Path
from typing import cast
from urllib.parse import urlsplit

import pytest
from OpenSSL import SSL

from hackvr import net
from hackvr.base import ConnectionToken
from hackvr.common import encoding, types
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

    def _accept_stream(self, deadline: net.Deadline) -> tuple[net.NetStream, ConnectionToken] | None:  # noqa: ARG002
        self.accept_calls += 1
        return self._stream, self._token

    def close(self) -> None:
        self.closed = True


class SequenceStream(net.NetStream):
    def __init__(self, chunks: list[bytes | None]) -> None:
        super().__init__()
        self._chunks = list(chunks)
        self.sent: list[bytes] = []

    def recv_unbuffered(self, max_bytes: int, deadline: net.Deadline) -> bytes | None:  # noqa: ARG002
        if not self._chunks:
            return None
        return self._chunks.pop(0)

    def send(self, data: bytes) -> None:
        self.sent.append(data)

    def close(self) -> None:
        return None


class ErrorStream(net.NetStream):
    def recv_unbuffered(self, max_bytes: int, deadline: net.Deadline) -> bytes | None:  # noqa: ARG002
        raise ValueError("bad stream")

    def send(self, data: bytes) -> None:  # noqa: ARG002
        return None

    def close(self) -> None:
        return None


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


def test_load_commands_invalid_payloads(tmp_path: Path) -> None:
    path = _write_json(tmp_path, {})
    with pytest.raises(TypeError, match="Playback file must be a JSON array"):
        playback_server._load_commands(path)

    path = _write_json(tmp_path, ["nope"])
    with pytest.raises(TypeError, match="Entry 0 must be an object"):
        playback_server._load_commands(path)

    path = _write_json(tmp_path, [{"cmd": "nope"}])
    with pytest.raises(TypeError, match="Entry 0 cmd must be a string array"):
        playback_server._load_commands(path)

    path = _write_json(tmp_path, [{"cmd": ["ok"], "delay": "soon"}])
    with pytest.raises(TypeError, match="Entry 0 delay must be a number"):
        playback_server._load_commands(path)


def test_dispatcher_logs_error() -> None:
    logs: list[str] = []

    def log_error(message: str) -> None:
        logs.append(message)

    dispatcher = playback_server._PlaybackDispatcher(log_error=log_error)

    dispatcher.handle_error("chat", "bad input", ["oops"])

    assert logs == ["invalid chat ['oops'] (bad input)"]


def test_dispatcher_noop_commands() -> None:
    dispatcher = playback_server._PlaybackDispatcher(log_error=lambda _message: None)
    dispatcher.chat("hello")
    dispatcher.set_user(types.UserID("user-1"))
    dispatcher.authenticate(types.UserID("user-1"), types.Bytes64(b"x" * 64))
    dispatcher.resume_session(types.SessionToken(b"a" * 32))
    dispatcher.send_input(cast(types.ZString, "hi"))
    dispatcher.tap_object(types.ObjectID("obj-1"), types.TapKind.PRIMARY, types.Tag("tag-1"))
    dispatcher.tell_object(types.ObjectID("obj-1"), cast(types.ZString, "hi"))
    dispatcher.intent(types.IntentID("intent-1"), types.Vec3(0.0, 0.0, 1.0))
    dispatcher.raycast(types.Vec3(0.0, 0.0, 0.0), types.Vec3(0.0, 1.0, 0.0))
    dispatcher.raycast_cancel()


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


def test_send_commands_logs_invalid_entry(monkeypatch: pytest.MonkeyPatch) -> None:
    stream = FakeStream()
    commands = [
        playback_server.PlaybackCommand(cmd=[], delay=0.0),
        playback_server.PlaybackCommand(cmd=["chat", "hello"], delay=1.0),
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

    assert stream.sent == [encoding.encode("chat", ["hello"])]
    assert "send <invalid>" in output.getvalue()


def test_send_commands_breaks_when_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    stream = FakeStream()
    commands = [playback_server.PlaybackCommand(cmd=["chat", "hello"], delay=0.0)]
    output = io.StringIO()
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
    connection._closed.set()

    connection._send_commands()

    assert stream.sent == []


def test_read_loop_handles_valid_command(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = encoding.encode("chat", ["hello"])
    stream = SequenceStream([payload, None, b""])
    output = io.StringIO()
    monkeypatch.setattr(playback_server.time, "monotonic_ns", lambda: 0)
    connection = playback_server._PlaybackConnection(
        stream,
        ConnectionToken(
            source_url=urlsplit("hackvr://example.com/world"),
            session_token=None,
            protocol="hackvr",
            is_secure=False,
        ),
        [],
        output,
        name="client-1",
    )

    connection._read_loop()

    log_output = output.getvalue()
    assert "recv chat hello" in log_output


def test_read_loop_handles_stream_error() -> None:
    output = io.StringIO()
    connection = playback_server._PlaybackConnection(
        ErrorStream(),
        ConnectionToken(
            source_url=urlsplit("hackvr://example.com/world"),
            session_token=None,
            protocol="hackvr",
            is_secure=False,
        ),
        [],
        output,
        name="client-1",
    )

    connection._read_loop()


def test_log_error_writes_details(monkeypatch: pytest.MonkeyPatch) -> None:
    output = io.StringIO()
    monkeypatch.setattr(playback_server.time, "monotonic_ns", lambda: 0)
    connection = playback_server._PlaybackConnection(
        FakeStream(),
        ConnectionToken(
            source_url=urlsplit("hackvr://example.com/world"),
            session_token=None,
            protocol="hackvr",
            is_secure=False,
        ),
        [],
        output,
        name="client-1",
    )

    connection._log_error("invalid chat [] (bad input)")

    assert "recv invalid chat [] (bad input)" in output.getvalue()


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


def test_serve_forever_accepts_single_client() -> None:
    stream = FakeStream()
    token = ConnectionToken(
        source_url=urlsplit("hackvr://example.com/world"),
        session_token=None,
        protocol="hackvr",
        is_secure=False,
    )

    class LoopServer(FakeServer):
        def _accept_stream(self, deadline: net.Deadline) -> tuple[net.NetStream, ConnectionToken] | None:  # noqa: ARG002
            if self.accept_calls >= 1:
                raise StopIteration
            return super()._accept_stream(deadline)

    fake_server = LoopServer(stream, token)
    server = playback_server.PlaybackServer(
        host="127.0.0.1",
        port=1234,
        scheme="hackvr",
        commands=[],
        output=io.StringIO(),
    )
    server._server = fake_server

    with pytest.raises(StopIteration):
        server.serve_forever()

    assert fake_server.accept_calls == 1


def test_create_server_rejects_scheme() -> None:
    with pytest.raises(ValueError, match="Unsupported scheme"):
        playback_server._create_server("127.0.0.1", 0, "nope")


def test_build_tls_listener_requires_cert() -> None:
    with pytest.raises(ValueError, match="TLS schemes require"):
        playback_server._build_tls_listener("127.0.0.1", 0, tls_cert=None)


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


def test_main_requires_both_tls_files(tmp_path: Path) -> None:
    json_path = _write_json(tmp_path, [])
    cert_path = tmp_path / "cert.pem"
    cert_path.write_text("cert", encoding="utf-8")

    with pytest.raises(ValueError, match="must be provided together"):
        playback_server.main(
            [
                str(json_path),
                "--scheme",
                "hackvrs",
                "--tls-cert",
                str(cert_path),
            ]
        )
