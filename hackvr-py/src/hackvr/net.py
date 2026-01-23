"""Network helpers for HackVR connections."""

from __future__ import annotations

import base64
import ipaddress
import select
import socket
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar, Protocol
from urllib.parse import SplitResult, urlsplit, urlunsplit

from OpenSSL import SSL
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import dsa, ec, ed25519, ed448, rsa

from .base import ConnectionToken
from .common import encoding, types
from .common.stream import MAX_LINE_LENGTH, _is_valid_name, _is_valid_param

if TYPE_CHECKING:
    from pathlib import Path

HACKVR_PORT = 1913
HACKVRS_PORT = 19133
DEFAULT_HELLO_TIMEOUT_S = 0.5
_DEFAULT_MAX_BYTES = 4096
_HTTP_HEADER_TERMINATOR = b"\r\n\r\n"
_SERVER_HELLO_PARTS = 2
_CLIENT_HELLO_MIN_PARTS = 3
_CLIENT_HELLO_MAX_PARTS = 4
_HTTP_REQUEST_MIN_PARTS = 3
_HTTP_RESPONSE_MIN_PARTS = 2
_DEADLINE_NEVER_NS = 2**63 - 1
_IPV6_VERSION = 6


class HandshakeError(RuntimeError):
    """Raised when a connection handshake fails."""


@dataclass(frozen=True)
class Deadline:
    """Monotonic deadline helper."""

    deadline_ns: int
    INSTANT: ClassVar[Deadline]
    NEVER: ClassVar[Deadline]

    @classmethod
    def from_now(
        cls,
        *,
        h: float = 0.0,
        m: float = 0.0,
        s: float = 0.0,
        ms: float = 0.0,
        us: float = 0.0,
        ns: float = 0.0,
    ) -> Deadline:
        total_ns = int(
            (h * 3600.0 + m * 60.0 + s) * 1_000_000_000
            + ms * 1_000_000
            + us * 1_000
            + ns
        )
        if total_ns <= 0:
            raise ValueError("Deadline must be greater than zero")
        return cls(time.monotonic_ns() + total_ns)

    def get_remaining_ns(self) -> int:
        return max(self.deadline_ns - time.monotonic_ns(), 0)

    def get_remaining_us(self) -> float:
        return self.get_remaining_ns() / 1_000.0

    def get_remaining_ms(self) -> float:
        return self.get_remaining_ns() / 1_000_000.0

    def get_remaining_s(self) -> float:
        return self.get_remaining_ns() / 1_000_000_000.0

    def is_reached(self) -> bool:
        if self.is_infinite():
            return False
        if self.is_empty():
            return True
        return time.monotonic_ns() >= self.deadline_ns

    def is_empty(self) -> bool:
        return self.deadline_ns == 0

    def is_infinite(self) -> bool:
        return self.deadline_ns >= _DEADLINE_NEVER_NS

    def check(self) -> None:
        if self.is_reached():
            raise TimeoutError


Deadline.NEVER = Deadline(_DEADLINE_NEVER_NS)
Deadline.INSTANT = Deadline(0)


class NetStream(ABC):
    """Transport-agnostic stream for HackVR traffic."""

    def __init__(self) -> None:
        self._buffer = bytearray()

    def recv(self, max_bytes: int, deadline: Deadline) -> bytes | None:
        """
        Receive data from the stream.

        Returns None when no data is available before the deadline.
        """
        if max_bytes <= 0:
            return b""
        if len(self._buffer) >= max_bytes:
            return self._drain_buffer(max_bytes)
        if deadline.is_reached() and not deadline.is_empty():
            return None

        desired = _DEFAULT_MAX_BYTES
        while len(self._buffer) < desired and len(self._buffer) < max_bytes:
            needed = desired - len(self._buffer)
            data = self.recv_unbuffered(needed, deadline=deadline)
            if data is None:
                break
            if data == b"":
                if self._buffer:
                    break
                return b""
            self._buffer.extend(data)
            if len(self._buffer) >= max_bytes:
                break

        if not self._buffer:
            return None
        return self._drain_buffer(min(max_bytes, len(self._buffer)))

    @abstractmethod
    def recv_unbuffered(self, max_bytes: int, deadline: Deadline) -> bytes | None:
        """Receive data from the underlying stream without buffering."""

    @abstractmethod
    def send(self, data: bytes) -> None:
        """Send data on the stream."""

    @abstractmethod
    def close(self) -> None:
        """Close the stream."""

    def _drain_buffer(self, size: int) -> bytes:
        chunk = bytes(self._buffer[:size])
        del self._buffer[:size]
        return chunk


class RawNetStream(NetStream):
    """Plain TCP stream."""

    def __init__(self, sock: socket.socket) -> None:
        super().__init__()
        self._sock = sock

    def recv_unbuffered(self, max_bytes: int, deadline: Deadline) -> bytes | None:
        ready = _wait_for_read(self._sock, deadline)
        if not ready:
            return None
        return self._sock.recv(max_bytes)

    def send(self, data: bytes) -> None:
        self._sock.sendall(data)

    def close(self) -> None:
        self._sock.close()


class TlsNetStream(NetStream):
    """TLS-wrapped TCP stream."""

    def __init__(self, sock: SSL.Connection) -> None:
        super().__init__()
        self._sock = sock

    def recv_unbuffered(self, max_bytes: int, deadline: Deadline) -> bytes | None:
        ready = _wait_for_read(self._sock, deadline)
        if not ready:
            return None
        return self._sock.recv(max_bytes)

    def send(self, data: bytes) -> None:
        self._sock.sendall(data)

    def close(self) -> None:
        self._sock.close()


class Peer:
    """Baseline network peer for sending/receiving bytes."""

    def __init__(self, stream: NetStream) -> None:
        self._stream = stream

    def receive(self, max_bytes: int = _DEFAULT_MAX_BYTES) -> bytes:
        data = self._stream.recv(max_bytes, deadline=Deadline.INSTANT)
        return b"" if data is None else data

    def send(self, data: bytes) -> None:
        self._stream.send(data)

    def close(self) -> None:
        self._stream.close()


class StreamConnector(Protocol):
    """Protocol for creating network streams."""

    def connect_raw(self, host: str, port: int) -> NetStream:
        """Create a raw TCP stream."""

    def connect_tls(
        self,
        host: str,
        port: int,
        context: SSL.Context | None = None,
    ) -> NetStream:
        """Create a TLS stream."""


class DefaultConnector:
    """Default socket-based connector implementation."""

    def connect_raw(self, host: str, port: int) -> NetStream:
        sock = socket.create_connection((host, port))
        return RawNetStream(sock)

    def connect_tls(
        self,
        host: str,
        port: int,
        context: SSL.Context | None = None,
    ) -> NetStream:
        sock = socket.create_connection((host, port))
        ssl_context = context or _default_tls_context()
        tls_sock = SSL.Connection(ssl_context, sock)
        tls_sock.set_tlsext_host_name(host.encode("utf-8"))
        tls_sock.set_connect_state()
        tls_sock.do_handshake()
        return TlsNetStream(tls_sock)


class Listener(Protocol):
    """Protocol for accepting network streams."""

    def accept(self, deadline: Deadline) -> tuple[NetStream, tuple[str, int]] | None:
        """Accept an inbound connection when ready."""

    def close(self) -> None:
        """Close the listener."""


class RawListener:
    """TCP listener for plain connections."""

    def __init__(self, host: str, port: int) -> None:
        family = _socket_family(host)
        self._sock = socket.socket(family, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if family == socket.AF_INET6:
            self._sock.bind((host, port, 0, 0))
        else:
            self._sock.bind((host, port))
        self._sock.listen()

    def accept(self, deadline: Deadline) -> tuple[NetStream, tuple[str, int]] | None:
        if not _wait_for_read(self._sock, deadline):
            return None
        conn, addr = self._sock.accept()
        return RawNetStream(conn), addr

    def close(self) -> None:
        self._sock.close()


@dataclass(frozen=True)
class TlsServerCertificate:
    """PEM-encoded TLS certificate and private key for servers."""

    cert_pem: bytes
    key_pem: bytes

    @classmethod
    def from_files(cls, cert_file: Path, key_file: Path) -> TlsServerCertificate:
        return cls(cert_pem=cert_file.read_bytes(), key_pem=key_file.read_bytes())

    def save(self, cert_file: Path, key_file: Path) -> None:
        cert_file.write_bytes(self.cert_pem)
        key_file.write_bytes(self.key_pem)


class TlsListener:
    """TCP listener for TLS connections."""

    def __init__(self, host: str, port: int, certificate: TlsServerCertificate) -> None:
        family = _socket_family(host)
        self._sock = socket.socket(family, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if family == socket.AF_INET6:
            self._sock.bind((host, port, 0, 0))
        else:
            self._sock.bind((host, port))
        self._sock.listen()
        self._context = _build_tls_context(certificate)

    def accept(self, deadline: Deadline) -> tuple[NetStream, tuple[str, int]] | None:
        if not _wait_for_read(self._sock, deadline):
            return None
        conn, addr = self._sock.accept()
        tls_conn = SSL.Connection(self._context, conn)
        tls_conn.set_accept_state()
        tls_conn.do_handshake()
        return TlsNetStream(tls_conn), addr

    def close(self) -> None:
        self._sock.close()


class Client(Peer):
    """HackVR network client supporting multiple URL schemes."""

    def __init__(
        self,
        connector: StreamConnector | None = None,
        hello_timeout: float = DEFAULT_HELLO_TIMEOUT_S,
    ) -> None:
        self._connector = connector or DefaultConnector()
        self._hello_timeout = hello_timeout
        self._stream: NetStream | None = None

    def connect(self, url: str, session_token: types.SessionToken | None = None) -> ConnectionToken:
        parsed = urlsplit(url)
        scheme = parsed.scheme
        if scheme == "http+hackvr":
            stream, token = self._connect_http(parsed, session_token)
        elif scheme == "https+hackvr":
            stream, token = self._connect_https(parsed, session_token)
        elif scheme == "hackvr":
            stream, token = self._connect_hackvr(parsed, session_token)
        elif scheme == "hackvrs":
            stream, token = self._connect_hackvrs(parsed, session_token)
        else:
            raise ValueError(f"Unsupported URL scheme: {scheme}")
        self._stream = stream
        return token

    def receive(self, max_bytes: int = _DEFAULT_MAX_BYTES) -> bytes:
        if self._stream is None:
            raise RuntimeError("Client is not connected")
        data = self._stream.recv(max_bytes, deadline=Deadline.INSTANT)
        return b"" if data is None else data

    def send(self, data: bytes) -> None:
        if self._stream is None:
            raise RuntimeError("Client is not connected")
        self._stream.send(data)

    def close(self) -> None:
        if self._stream is not None:
            self._stream.close()
            self._stream = None

    def _connect_http(
        self,
        parsed: SplitResult,
        session_token: types.SessionToken | None,
    ) -> tuple[NetStream, ConnectionToken]:
        host, port = _resolve_host_port(parsed, default_port=80)
        token = _resolve_session_token(parsed, session_token)
        stream = self._connector.connect_raw(host, port)
        _send_http_upgrade(
            stream,
            host=host,
            port=port,
            path=_build_path(parsed),
            session_token=token,
        )
        _receive_http_upgrade(stream, Deadline.from_now(s=self._hello_timeout))
        source_url = _strip_fragment(parsed)
        return stream, ConnectionToken(
            source_url=source_url,
            session_token=token,
            protocol="http+hackvr",
            is_secure=False,
        )

    def _connect_https(
        self,
        parsed: SplitResult,
        session_token: types.SessionToken | None,
    ) -> tuple[NetStream, ConnectionToken]:
        host, port = _resolve_host_port(parsed, default_port=443)
        token = _resolve_session_token(parsed, session_token)
        stream = self._connector.connect_tls(host, port, context=None)
        _send_http_upgrade(
            stream,
            host=host,
            port=port,
            path=_build_path(parsed),
            session_token=token,
        )
        _receive_http_upgrade(stream, Deadline.from_now(s=self._hello_timeout))
        source_url = _strip_fragment(parsed)
        return stream, ConnectionToken(
            source_url=source_url,
            session_token=token,
            protocol="https+hackvr",
            is_secure=True,
        )

    def _connect_hackvr(
        self,
        parsed: SplitResult,
        session_token: types.SessionToken | None,
    ) -> tuple[NetStream, ConnectionToken]:
        host, port = _resolve_host_port(parsed, default_port=HACKVR_PORT)
        token = _resolve_session_token(parsed, session_token)
        stream = self._connector.connect_raw(host, port)
        _send_hello(stream, uri=_strip_fragment_url(parsed), session_token=token)
        _receive_server_hello(stream, Deadline.from_now(s=self._hello_timeout))
        return stream, ConnectionToken(
            source_url=_strip_fragment(parsed),
            session_token=token,
            protocol="hackvr",
            is_secure=False,
        )

    def _connect_hackvrs(
        self,
        parsed: SplitResult,
        session_token: types.SessionToken | None,
    ) -> tuple[NetStream, ConnectionToken]:
        host, port = _resolve_host_port(parsed, default_port=HACKVRS_PORT)
        token = _resolve_session_token(parsed, session_token)
        stream = self._connector.connect_tls(host, port, context=None)
        _send_hello(stream, uri=_strip_fragment_url(parsed), session_token=token)
        _receive_server_hello(stream, Deadline.from_now(s=self._hello_timeout))
        return stream, ConnectionToken(
            source_url=_strip_fragment(parsed),
            session_token=token,
            protocol="hackvrs",
            is_secure=True,
        )


class Server(ABC):
    """Base class for HackVR servers."""

    def __init__(
        self,
        host: str,
        port: int,
        listener: Listener | None = None,
        hello_timeout: float = DEFAULT_HELLO_TIMEOUT_S,
    ) -> None:
        self._host = host
        self._port = port
        self._hello_timeout = hello_timeout
        self._listener = listener

    def accept(self, deadline: Deadline = Deadline.NEVER) -> tuple[Peer, ConnectionToken] | None:
        result = self._accept_stream(deadline)
        if result is None:
            return None
        stream, token = result
        return Peer(stream), token

    def close(self) -> None:
        if self._listener is not None:
            self._listener.close()

    @abstractmethod
    def _accept_stream(self, deadline: Deadline) -> tuple[NetStream, ConnectionToken] | None:
        """Accept a connection and perform handshake."""


class RawServer(Server):
    """Server for hackvr:// connections."""

    def __init__(
        self,
        host: str,
        port: int = HACKVR_PORT,
        listener: Listener | None = None,
        hello_timeout: float = DEFAULT_HELLO_TIMEOUT_S,
    ) -> None:
        super().__init__(host, port, listener=listener, hello_timeout=hello_timeout)
        if self._listener is None:
            self._listener = RawListener(host, port)

    def _accept_stream(self, deadline: Deadline) -> tuple[NetStream, ConnectionToken] | None:
        assert self._listener is not None
        result = self._listener.accept(deadline)
        if result is None:
            return None
        stream, _addr = result
        _send_hello(stream)
        hello = _receive_client_hello(stream, Deadline.from_now(s=self._hello_timeout))
        return stream, ConnectionToken(
            source_url=hello.source_url,
            session_token=hello.session_token,
            protocol="hackvr",
            is_secure=False,
        )


class TlsServer(Server):
    """Server for hackvrs:// connections."""

    def __init__(
        self,
        host: str,
        port: int = HACKVRS_PORT,
        listener: Listener | None = None,
        hello_timeout: float = DEFAULT_HELLO_TIMEOUT_S,
    ) -> None:
        super().__init__(host, port, listener=listener, hello_timeout=hello_timeout)
        if self._listener is None:
            raise ValueError("TlsServer requires a TLS listener")

    def _accept_stream(self, deadline: Deadline) -> tuple[NetStream, ConnectionToken] | None:
        assert self._listener is not None
        result = self._listener.accept(deadline)
        if result is None:
            return None
        stream, _addr = result
        _send_hello(stream)
        hello = _receive_client_hello(stream, Deadline.from_now(s=self._hello_timeout))
        return stream, ConnectionToken(
            source_url=hello.source_url,
            session_token=hello.session_token,
            protocol="hackvrs",
            is_secure=True,
        )


class HttpServer(Server):
    """Server for http+hackvr:// connections."""

    def __init__(
        self,
        host: str,
        port: int = 80,
        listener: Listener | None = None,
    ) -> None:
        super().__init__(host, port, listener=listener)
        if self._listener is None:
            self._listener = RawListener(host, port)

    def _accept_stream(self, deadline: Deadline) -> tuple[NetStream, ConnectionToken] | None:
        assert self._listener is not None
        result = self._listener.accept(deadline)
        if result is None:
            return None
        stream, _addr = result
        request = _receive_http_request(stream, Deadline.from_now(s=self._hello_timeout))
        _send_http_upgrade_response(stream)
        source_url = urlsplit(f"http+hackvr://{request.host}{request.path}")
        return stream, ConnectionToken(
            source_url=source_url,
            session_token=request.session_token,
            protocol="http+hackvr",
            is_secure=False,
        )


class HttpsServer(Server):
    """Server for https+hackvr:// connections."""

    def __init__(
        self,
        host: str,
        port: int = 443,
        listener: Listener | None = None,
    ) -> None:
        super().__init__(host, port, listener=listener)
        if self._listener is None:
            raise ValueError("HttpsServer requires a TLS listener")

    def _accept_stream(self, deadline: Deadline) -> tuple[NetStream, ConnectionToken] | None:
        assert self._listener is not None
        result = self._listener.accept(deadline)
        if result is None:
            return None
        stream, _addr = result
        request = _receive_http_request(stream, Deadline.from_now(s=self._hello_timeout))
        _send_http_upgrade_response(stream)
        source_url = urlsplit(f"https+hackvr://{request.host}{request.path}")
        return stream, ConnectionToken(
            source_url=source_url,
            session_token=request.session_token,
            protocol="https+hackvr",
            is_secure=True,
        )


@dataclass(frozen=True)
class _HelloInfo:
    source_url: SplitResult
    session_token: types.SessionToken | None


@dataclass(frozen=True)
class _HttpRequest:
    host: str
    path: str
    session_token: types.SessionToken | None


def _resolve_session_token(
    parsed: SplitResult,
    explicit: types.SessionToken | None,
) -> types.SessionToken | None:
    if not parsed.fragment:
        return explicit
    fragment_token = types.parse_session_token(parsed.fragment, optional=False)
    if explicit is not None and explicit != fragment_token:
        raise ValueError("Session token mismatch between fragment and parameter")
    return explicit or fragment_token


def _resolve_host_port(parsed: SplitResult, default_port: int) -> tuple[str, int]:
    if not parsed.hostname:
        raise ValueError("URL must include hostname")
    port = parsed.port or default_port
    return parsed.hostname, port


def _strip_fragment(parsed: SplitResult) -> SplitResult:
    return parsed._replace(fragment="")


def _strip_fragment_url(parsed: SplitResult) -> str:
    return urlunsplit(_strip_fragment(parsed))


def _build_path(parsed: SplitResult) -> str:
    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"
    return path


def _format_version(version: types.Version | None = None) -> str:
    value = int(version or types.Version(1))
    return f"v{value}"


def _format_session_token(token: types.SessionToken) -> str:
    encoded = base64.urlsafe_b64encode(bytes(token)).decode("ascii")
    return encoded.rstrip("=")


def _send_hello(
    stream: NetStream,
    uri: str | None = None,
    session_token: types.SessionToken | None = None,
) -> None:
    params = [_format_version()]
    if uri is not None:
        params.append(uri)
    if session_token is not None:
        params.append(_format_session_token(session_token))
    stream.send(encoding.encode("hackvr-hello", params))


def _receive_server_hello(stream: NetStream, deadline: Deadline) -> types.Version:
    parts = _receive_command(stream, deadline)
    if parts[0] != "hackvr-hello":
        raise HandshakeError("Expected hackvr-hello from server")
    if len(parts) != _SERVER_HELLO_PARTS:
        raise HandshakeError("Server hello must include version")
    version = types.parse_version(parts[1], optional=False)
    assert version is not None
    return version


def _receive_client_hello(stream: NetStream, deadline: Deadline) -> _HelloInfo:
    parts = _receive_command(stream, deadline)
    if parts[0] != "hackvr-hello":
        raise HandshakeError("Expected hackvr-hello from client")
    if len(parts) not in (_CLIENT_HELLO_MIN_PARTS, _CLIENT_HELLO_MAX_PARTS):
        raise HandshakeError("Client hello must include version and uri")
    types.parse_version(parts[1], optional=False)
    uri = types.parse_uri(parts[2], optional=False)
    session_token = None
    if len(parts) == _CLIENT_HELLO_MAX_PARTS:
        session_token = types.parse_session_token(parts[3], optional=False)
    return _HelloInfo(source_url=urlsplit(str(uri)), session_token=session_token)


def _receive_command(stream: NetStream, deadline: Deadline) -> list[str]:
    line = _receive_line(stream, deadline)
    parts = line.split("\t")
    if not parts or not _is_valid_name(parts[0]):
        raise HandshakeError("Invalid command name")
    if any(not _is_valid_param(param) for param in parts[1:]):
        raise HandshakeError("Invalid command parameter")
    return parts


def _receive_line(stream: NetStream, deadline: Deadline) -> str:
    buffer = bytearray()
    while True:
        deadline.check()
        chunk = stream.recv(1, deadline=deadline)
        if chunk is None:
            continue
        if chunk == b"":
            raise HandshakeError("Connection closed during handshake")
        buffer.extend(chunk)
        if len(buffer) > MAX_LINE_LENGTH:
            raise HandshakeError("Handshake line exceeds maximum length")
        if buffer[-2:] == b"\r\n":
            line_bytes = bytes(buffer[:-2])
            if b"\r" in line_bytes:
                raise HandshakeError("Invalid CR in handshake line")
            try:
                line = line_bytes.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise HandshakeError("Invalid UTF-8 in handshake line") from exc
            if not line:
                raise HandshakeError("Empty handshake line")
            return line


def _receive_http_request(stream: NetStream, deadline: Deadline) -> _HttpRequest:
    data = _read_until(stream, _HTTP_HEADER_TERMINATOR, deadline)
    headers = data.decode("iso-8859-1").split("\r\n")
    if not headers or len(headers[0].split()) < _HTTP_REQUEST_MIN_PARTS:
        raise HandshakeError("Malformed HTTP request")
    method, path, _version = headers[0].split(" ", 2)
    if method.upper() != "GET":
        raise HandshakeError("Expected GET request")
    header_map = _parse_headers(headers[1:])
    if "upgrade" not in header_map or header_map["upgrade"].lower() != "hackvr":
        raise HandshakeError("Missing Upgrade: hackvr header")
    if "connection" not in header_map or "upgrade" not in header_map["connection"].lower():
        raise HandshakeError("Missing Connection: upgrade header")
    if "host" not in header_map:
        raise HandshakeError("Missing Host header")
    token = None
    if "hackvr-session" in header_map:
        token = types.parse_session_token(header_map["hackvr-session"], optional=False)
    return _HttpRequest(host=header_map["host"], path=path, session_token=token)


def _receive_http_upgrade(stream: NetStream, deadline: Deadline) -> None:
    data = _read_until(stream, _HTTP_HEADER_TERMINATOR, deadline)
    headers = data.decode("iso-8859-1").split("\r\n")
    if not headers or len(headers[0].split()) < _HTTP_RESPONSE_MIN_PARTS:
        raise HandshakeError("Malformed HTTP response")
    _version, status, _reason = headers[0].split(" ", 2)
    if status != "101":
        raise HandshakeError(f"Unexpected HTTP status {status}")
    header_map = _parse_headers(headers[1:])
    if "upgrade" not in header_map or header_map["upgrade"].lower() != "hackvr":
        raise HandshakeError("Missing Upgrade: hackvr response")
    if "connection" not in header_map or "upgrade" not in header_map["connection"].lower():
        raise HandshakeError("Missing Connection: upgrade response")


def _send_http_upgrade(
    stream: NetStream,
    host: str,
    port: int,
    path: str,
    session_token: types.SessionToken | None,
) -> None:
    host_header = host if port in (80, 443) else f"{host}:{port}"
    headers = [
        f"GET {path} HTTP/1.1",
        f"Host: {host_header}",
        "Connection: upgrade",
        "Upgrade: hackvr",
        "HackVr-Version: v1",
    ]
    if session_token is not None:
        headers.append(f"HackVr-Session: {_format_session_token(session_token)}")
    request = "\r\n".join(headers) + "\r\n\r\n"
    stream.send(request.encode("iso-8859-1"))


def _send_http_upgrade_response(stream: NetStream) -> None:
    response = "\r\n".join(
        [
            "HTTP/1.1 101 Switching Protocols",
            "Connection: upgrade",
            "Upgrade: hackvr",
            "HackVr-Version: v1",
            "",
            "",
        ]
    )
    stream.send(response.encode("iso-8859-1"))


def _read_until(stream: NetStream, terminator: bytes, deadline: Deadline) -> bytes:
    buffer = bytearray()
    while True:
        deadline.check()
        chunk = stream.recv(1, deadline=deadline)
        if chunk is None:
            continue
        if chunk == b"":
            raise HandshakeError("Connection closed during HTTP handshake")
        buffer.extend(chunk)
        if terminator in buffer:
            index = buffer.index(terminator) + len(terminator)
            return bytes(buffer[:index])
        if len(buffer) > MAX_LINE_LENGTH * 8:
            raise HandshakeError("HTTP headers too large")


def _parse_headers(lines: list[str]) -> dict[str, str]:
    headers: dict[str, str] = {}
    for line in lines:
        if not line:
            continue
        if ":" not in line:
            continue
        name, value = line.split(":", 1)
        headers[name.strip().lower()] = value.strip()
    return headers


def _wait_for_read(sock: socket.socket | SSL.Connection, deadline: Deadline) -> bool:
    if deadline.is_infinite():
        return True
    ready, _w, _x = select.select([sock], [], [], deadline.get_remaining_s())
    return bool(ready)


def _socket_family(host: str) -> socket.AddressFamily:
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return socket.AF_INET
    return socket.AF_INET6 if ip.version == _IPV6_VERSION else socket.AF_INET


def _default_tls_context() -> SSL.Context:
    context = SSL.Context(SSL.TLS_METHOD)
    context.set_default_verify_paths()
    context.set_verify(SSL.VERIFY_PEER, None)
    return context


def _build_tls_context(certificate: TlsServerCertificate) -> SSL.Context:
    context = SSL.Context(SSL.TLS_METHOD)
    cert = x509.load_pem_x509_certificate(certificate.cert_pem)
    key = serialization.load_pem_private_key(certificate.key_pem, password=None)
    if not isinstance(
        key,
        (
            dsa.DSAPrivateKey,
            ec.EllipticCurvePrivateKey,
            ed25519.Ed25519PrivateKey,
            ed448.Ed448PrivateKey,
            rsa.RSAPrivateKey,
        ),
    ):
        raise TypeError("Unsupported private key type for TLS context")
    context.use_certificate(cert)
    context.use_privatekey(key)
    context.check_privatekey()
    return context
