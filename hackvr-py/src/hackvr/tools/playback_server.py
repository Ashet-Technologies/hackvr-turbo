"""Playback server tool for scripted HackVR sessions."""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, TextIO

from OpenSSL import SSL

from hackvr import net
from hackvr.common import encoding, stream, types
from hackvr.server import Server as ProtocolServer

if TYPE_CHECKING:
    from collections.abc import Callable
    from hackvr.base import ConnectionToken

_DEFAULT_HOST = "127.0.0.1"
_DEFAULT_PORTS: dict[str, int] = {
    "hackvr": net.HACKVR_PORT,
    "hackvrs": net.HACKVRS_PORT,
    "http+hackvr": 80,
    "https+hackvr": 443,
}


@dataclass(frozen=True)
class PlaybackCommand:
    """Command entry for playback sessions."""

    cmd: list[str]
    delay: float


class _PlaybackDispatcher(ProtocolServer):
    def __init__(self, *, log_error: Callable[[str], None]) -> None:
        self._log_error = log_error
        super().__init__()

    def handle_error(self, cmd: str, message: str, args: list[str]) -> None:
        details = f"invalid {cmd} {args} ({message})"
        self._log_error(details)

    def chat(self, _message: str) -> None:
        return None

    def set_user(self, _user: types.UserID) -> None:
        return None

    def authenticate(self, _user: types.UserID, _signature: types.Bytes64) -> None:
        return None

    def resume_session(self, _token: types.SessionToken) -> None:
        return None

    def send_input(self, _text: types.ZString) -> None:
        return None

    def tap_object(
        self,
        _obj: types.ObjectID,
        _kind: types.TapKind,
        _tag: types.Tag,
    ) -> None:
        return None

    def tell_object(self, _obj: types.ObjectID, _text: types.ZString) -> None:
        return None

    def intent(self, _intent_id: types.IntentID, _view_dir: types.Vec3) -> None:
        return None

    def raycast(self, _origin: types.Vec3, _direction: types.Vec3) -> None:
        return None

    def raycast_cancel(self) -> None:
        return None


class _PlaybackConnection:
    def __init__(
        self,
        stream: net.NetStream,
        token: ConnectionToken,
        commands: list[PlaybackCommand],
        output: TextIO,
        *,
        name: str,
    ) -> None:
        self._stream = stream
        self._token = token
        self._commands = commands
        self._output = output
        self._start_ns = time.monotonic_ns()
        self._closed = threading.Event()
        self._name = name
        self._dispatcher = _PlaybackDispatcher(log_error=self._log_error)

    def run(self) -> None:
        self._output.write(f"[{self._name}] connected {self._token.source_url.geturl()}\n")
        self._output.flush()
        reader = threading.Thread(target=self._read_loop, daemon=True)
        reader.start()
        try:
            self._send_commands()
        finally:
            self._closed.set()
            self._stream.close()
            self._output.write(f"[{self._name}] disconnected\n")
            self._output.flush()

    def _read_loop(self) -> None:
        parser = stream.Parser()
        while not self._closed.is_set():
            try:
                data = self._stream.recv(4096, deadline=net.Deadline.from_now(ms=50))
            except (OSError, SSL.Error, ValueError):
                self._closed.set()
                return
            if data is None:
                continue
            if data == b"":
                self._closed.set()
                return
            parser.push(data)
            while True:
                parts = parser.pull()
                if parts is None:
                    break
                cmd = parts[0]
                args = parts[1:]
                self._log("recv", cmd, args)
                self._dispatcher.execute_command(cmd, args)

    def _send_commands(self) -> None:
        for _index, entry in enumerate(self._commands):
            if entry.delay > 0:
                time.sleep(entry.delay)
            if self._closed.is_set():
                break
            cmd = entry.cmd[0] if entry.cmd else ""
            args = entry.cmd[1:]
            if not cmd:
                self._log("send", "<invalid>", args)
                continue
            data = encoding.encode(cmd, args)
            self._stream.send(data)
            self._log("send", cmd, args)

    def _log(self, direction: str, cmd: str, args: list[str]) -> None:
        delta = (time.monotonic_ns() - self._start_ns) / 1_000_000_000
        args_text = " ".join(args)
        suffix = f" {args_text}" if args_text else ""
        self._output.write(f"[{self._name}] {delta:.3f}s {direction} {cmd}{suffix}\n")
        self._output.flush()

    def _log_error(self, details: str) -> None:
        delta = (time.monotonic_ns() - self._start_ns) / 1_000_000_000
        self._output.write(f"[{self._name}] {delta:.3f}s recv {details}\n")
        self._output.flush()


class PlaybackServer:
    """Accept HackVR connections and replay scripted commands."""

    def __init__(
        self,
        *,
        host: str,
        port: int,
        scheme: str,
        commands: list[PlaybackCommand],
        output: TextIO,
        oneshot: bool = False,
        tls_cert: net.TlsServerCertificate | None = None,
    ) -> None:
        self._host = host
        self._port = port
        self._scheme = scheme
        self._commands = commands
        self._output = output
        self._oneshot = oneshot
        self._server = _create_server(host, port, scheme, tls_cert=tls_cert)

    def serve_forever(self) -> None:
        self._output.write(f"Listening on {self._scheme}://{self._host}:{self._port}\n")
        self._output.flush()
        if self._oneshot:
            stream, token = self._server._accept_stream()
            handler = _PlaybackConnection(stream, token, self._commands, self._output, name="client-1")
            handler.run()
            self._server.close()
            return
        index = 0
        while True:
            stream, token = self._server._accept_stream()
            index += 1
            name = f"client-{index}"
            handler = _PlaybackConnection(stream, token, self._commands, self._output, name=name)
            thread = threading.Thread(target=handler.run, daemon=True)
            thread.start()


def _create_server(
    host: str,
    port: int,
    scheme: str,
    *,
    tls_cert: net.TlsServerCertificate | None = None,
) -> net.Server:
    if scheme == "hackvr":
        return net.RawServer(host, port)
    if scheme == "hackvrs":
        listener = _build_tls_listener(host, port, tls_cert=tls_cert)
        return net.TlsServer(host, port, listener=listener)
    if scheme == "http+hackvr":
        return net.HttpServer(host, port)
    if scheme == "https+hackvr":
        listener = _build_tls_listener(host, port, tls_cert=tls_cert)
        return net.HttpsServer(host, port, listener=listener)
    raise ValueError(f"Unsupported scheme: {scheme}")


def _build_tls_listener(
    host: str,
    port: int,
    *,
    tls_cert: net.TlsServerCertificate | None,
) -> net.TlsListener:
    if tls_cert is None:
        raise ValueError("TLS schemes require --tls-cert and --tls-key")
    return net.TlsListener(host, port, tls_cert)


def _load_commands(path: Path) -> list[PlaybackCommand]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise TypeError("Playback file must be a JSON array")
    commands: list[PlaybackCommand] = []
    for index, entry in enumerate(payload):
        if not isinstance(entry, dict):
            raise TypeError(f"Entry {index} must be an object")
        cmd = entry.get("cmd")
        delay = entry.get("delay", 0.0)
        if not isinstance(cmd, list) or not all(isinstance(item, str) for item in cmd):
            raise TypeError(f"Entry {index} cmd must be a string array")
        if not isinstance(delay, int | float):
            raise TypeError(f"Entry {index} delay must be a number")
        if delay < 0:
            raise ValueError(f"Entry {index} delay must be non-negative")
        commands.append(PlaybackCommand(cmd=cmd, delay=float(delay)))
    return commands


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="HackVR playback server")
    parser.add_argument(
        "json",
        type=Path,
        help="JSON file with playback commands",
    )
    parser.add_argument(
        "--host",
        default=_DEFAULT_HOST,
        help=f"Host to bind (default: {_DEFAULT_HOST})",
    )
    parser.add_argument(
        "--port",
        type=int,
        help="Port to bind (defaults to scheme default)",
    )
    parser.add_argument(
        "--scheme",
        choices=sorted(_DEFAULT_PORTS.keys()),
        default="hackvr",
        help="Transport scheme",
    )
    parser.add_argument(
        "--tls-cert",
        type=Path,
        help="Path to TLS certificate (required for hackvrs/https+hackvr)",
    )
    parser.add_argument(
        "--tls-key",
        type=Path,
        help="Path to TLS private key (required for hackvrs/https+hackvr)",
    )
    parser.add_argument(
        "--oneshot",
        action="store_true",
        help="Stop the server after the first client disconnects",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    commands = _load_commands(args.json)
    port = args.port or _DEFAULT_PORTS[args.scheme]
    tls_cert = None
    if args.tls_cert is not None or args.tls_key is not None:
        if args.tls_cert is None or args.tls_key is None:
            raise ValueError("--tls-cert and --tls-key must be provided together")
        tls_cert = net.TlsServerCertificate.from_files(args.tls_cert, args.tls_key)
    server = PlaybackServer(
        host=args.host,
        port=port,
        scheme=args.scheme,
        commands=commands,
        output=sys.stdout,
        oneshot=args.oneshot,
        tls_cert=tls_cert,
    )
    server.serve_forever()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
