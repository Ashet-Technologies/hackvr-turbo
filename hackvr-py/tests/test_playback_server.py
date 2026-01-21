import io
import json
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from hackvr import net
from hackvr.base import ConnectionToken
from hackvr.common import encoding
from hackvr.tools import playback_server


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
