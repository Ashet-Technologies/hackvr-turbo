"""Server-side (C→S) protocol commands."""

from __future__ import annotations

import logging
import socket
import time
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Literal, overload, cast

from OpenSSL import SSL

from . import net
from .base import (
    ProtocolBase,
    RemoteBase,
    _serialize_bool,
    _serialize_bytes,
    _serialize_enum,
    _serialize_euler,
    _serialize_float,
    _serialize_optional,
    _serialize_session_token,
    _serialize_tuple_list,
    _serialize_vec2,
    _serialize_vec3,
    command,
)
from .common import stream

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from .common import types


class AbstractServer(ProtocolBase):
    """Server-side protocol handlers for client-to-server commands."""

    @command("chat")
    def chat(self, message: str) -> None:
        raise NotImplementedError

    @command("set-user")
    def set_user(self, user: types.UserID) -> None:
        raise NotImplementedError

    @command("authenticate")
    def authenticate(self, user: types.UserID, signature: types.Bytes64) -> None:
        raise NotImplementedError

    @command("resume-session")
    def resume_session(self, token: types.SessionToken) -> None:
        raise NotImplementedError

    @command("send-input")
    def send_input(self, text: types.ZString) -> None:
        raise NotImplementedError

    @command("tap-object")
    def tap_object(
        self,
        obj: types.ObjectID,
        kind: types.TapKind,
        tag: types.Tag,
    ) -> None:
        raise NotImplementedError

    @command("tell-object")
    def tell_object(self, obj: types.ObjectID, text: types.ZString) -> None:
        raise NotImplementedError

    @command("intent")
    def intent(self, intent_id: types.IntentID, view_dir: types.Vec3) -> None:
        raise NotImplementedError

    @command("raycast")
    def raycast(self, origin: types.Vec3, direction: types.Vec3) -> None:
        raise NotImplementedError

    @command("raycast-cancel")
    def raycast_cancel(self) -> None:
        raise NotImplementedError


class RemoteClient(RemoteBase):
    """Server-side helper for sending server-to-client commands."""

    def chat(self, user: types.UserID, message: str) -> None:
        self.send_cmd("chat", str(user), message)

    def request_user(self, prompt: types.ZString | None) -> None:
        self.send_cmd("request-user", _serialize_optional(prompt, str))

    def request_authentication(
        self,
        user: types.UserID,
        nonce: types.Bytes16,
    ) -> None:
        self.send_cmd(
            "request-authentication",
            str(user),
            _serialize_bytes(nonce),
        )

    def accept_user(self, user: types.UserID) -> None:
        self.send_cmd("accept-user", str(user))

    def reject_user(self, user: types.UserID, reason: types.ZString | None) -> None:
        self.send_cmd("reject-user", str(user), _serialize_optional(reason, str))

    def announce_session(
        self,
        token: types.SessionToken,
        lifetime: int | None,
    ) -> None:
        self.send_cmd(
            "announce-session",
            _serialize_session_token(token),
            _serialize_optional(lifetime, str),
        )

    def revoke_session(self, token: types.SessionToken) -> None:
        self.send_cmd("revoke-session", _serialize_session_token(token))

    def request_input(self, prompt: str, default: str | None) -> None:
        self.send_cmd(
            "request-input",
            prompt,
            _serialize_optional(default, str),
        )

    def cancel_input(self) -> None:
        self.send_cmd("cancel-input")

    def set_banner(self, text: str | None, duration: float | None) -> None:
        self.send_cmd(
            "set-banner",
            _serialize_optional(text, str),
            _serialize_optional(duration, _serialize_float),
        )

    def create_intent(self, intent_id: types.IntentID, label: str) -> None:
        self.send_cmd("create-intent", str(intent_id), label)

    def destroy_intent(self, intent_id: types.IntentID) -> None:
        self.send_cmd("destroy-intent", str(intent_id))

    def raycast_request(self) -> None:
        self.send_cmd("raycast-request")

    def raycast_cancel(self) -> None:
        self.send_cmd("raycast-cancel")

    def create_geometry(self, geom_id: str) -> None:
        self.send_cmd("create-geometry", geom_id)

    def destroy_geometry(self, geom_id: str) -> None:
        self.send_cmd("destroy-geometry", geom_id)

    def add_triangle_list(
        self,
        geom_id: str,
        tag: types.Tag | None,
        triangles: list[tuple[types.Color, types.Vec3, types.Vec3, types.Vec3]],
    ) -> None:
        serializers = cast(
            "Sequence[Callable[[object], str]]",
            [str, _serialize_vec3, _serialize_vec3, _serialize_vec3],
        )
        triangle_params = _serialize_tuple_list(
            triangles,
            serializers,
        )
        self.send_cmd(
            "add-triangle-list",
            geom_id,
            _serialize_optional(tag, str),
            *triangle_params,
        )

    def add_triangle_strip(
        self,
        geom_id: str,
        tag: types.Tag | None,
        color: types.Color,
        p0: types.Vec3,
        p1: types.Vec3,
        p2: types.Vec3,
        positions: list[types.Vec3],
    ) -> None:
        self.send_cmd(
            "add-triangle-strip",
            geom_id,
            _serialize_optional(tag, str),
            str(color),
            _serialize_vec3(p0),
            _serialize_vec3(p1),
            _serialize_vec3(p2),
            *[_serialize_vec3(position) for position in positions],
        )

    def add_triangle_fan(
        self,
        geom_id: str,
        tag: types.Tag | None,
        color: types.Color,
        p0: types.Vec3,
        p1: types.Vec3,
        p2: types.Vec3,
        positions: list[types.Vec3],
    ) -> None:
        self.send_cmd(
            "add-triangle-fan",
            geom_id,
            _serialize_optional(tag, str),
            str(color),
            _serialize_vec3(p0),
            _serialize_vec3(p1),
            _serialize_vec3(p2),
            *[_serialize_vec3(position) for position in positions],
        )

    def remove_triangles(self, geom_id: str, tag: str) -> None:
        self.send_cmd("remove-triangles", geom_id, tag)

    def create_text_geometry(
        self,
        geom_id: str,
        size: types.Vec2,
        uri: types.URI,
        sha256: types.Bytes32,
        text: str,
        anchor: types.Anchor | None,
    ) -> None:
        self.send_cmd(
            "create-text-geometry",
            geom_id,
            _serialize_vec2(size),
            str(uri),
            _serialize_bytes(sha256),
            text,
            _serialize_optional(anchor, _serialize_enum),
        )

    def create_sprite_geometry(
        self,
        geom_id: str,
        size: types.Vec2,
        uri: types.URI,
        sha256: types.Bytes32,
        size_mode: types.SizeMode | None,
        anchor: types.Anchor | None,
    ) -> None:
        self.send_cmd(
            "create-sprite-geometry",
            geom_id,
            _serialize_vec2(size),
            str(uri),
            _serialize_bytes(sha256),
            _serialize_optional(size_mode, _serialize_enum),
            _serialize_optional(anchor, _serialize_enum),
        )

    def set_text_property(
        self,
        geom_id: str,
        property_name: str,
        value: types.AnyValue,
    ) -> None:
        self.send_cmd("set-text-property", geom_id, property_name, str(value))

    def create_object(self, obj_id: str, geom_id: types.GeomID | None) -> None:
        self.send_cmd("create-object", obj_id, _serialize_optional(geom_id, str))

    def destroy_object(self, obj_id: str) -> None:
        self.send_cmd("destroy-object", obj_id)

    def reparent_object(
        self,
        parent: types.ObjectID,
        child: str,
        transform: types.ReparentMode | None,
    ) -> None:
        self.send_cmd(
            "reparent-object",
            str(parent),
            child,
            _serialize_optional(transform, _serialize_enum),
        )

    def set_object_geometry(self, obj_id: str, geom_id: types.GeomID | None) -> None:
        self.send_cmd("set-object-geometry", obj_id, _serialize_optional(geom_id, str))

    def set_object_property(
        self,
        obj_id: str,
        property_name: str,
        value: types.AnyValue,
    ) -> None:
        self.send_cmd("set-object-property", obj_id, property_name, str(value))

    def set_object_transform(
        self,
        obj_id: str,
        pos: types.Vec3 | None,
        rot: types.Euler | None,
        scale: types.Vec3 | None,
        duration: float | None,
    ) -> None:
        self.send_cmd(
            "set-object-transform",
            obj_id,
            _serialize_optional(pos, _serialize_vec3),
            _serialize_optional(rot, _serialize_euler),
            _serialize_optional(scale, _serialize_vec3),
            _serialize_optional(duration, _serialize_float),
        )

    def track_object(
        self,
        obj_id: str,
        target: types.ObjectID | None,
        mode: types.TrackMode | None,
        duration: float | None,
    ) -> None:
        self.send_cmd(
            "track-object",
            obj_id,
            _serialize_optional(target, str),
            _serialize_optional(mode, _serialize_enum),
            _serialize_optional(duration, _serialize_float),
        )

    def enable_free_look(self, enabled: bool) -> None:
        self.send_cmd("enable-free-look", _serialize_bool(enabled))

    def set_background_color(self, color: types.Color) -> None:
        self.send_cmd("set-background-color", str(color))


class _NetworkRemoteClient(RemoteClient):
    """Remote client adapter that sends packets through a net.Peer."""

    def __init__(self, peer: net.Peer) -> None:
        self._peer = peer

    def send_packet(self, data: bytes) -> None:
        self._peer.send(data)


class Connection(AbstractServer):
    """Networked HackVR server connection with polling-driven dispatch."""

    def __init__(self, peer: net.Peer, connection_token: net.ConnectionToken) -> None:
        super().__init__()
        self._peer = peer
        self._parser = stream.Parser()
        self._client = _NetworkRemoteClient(peer)
        self.connection_token = connection_token
        self._connected = True

    @property
    def is_connected(self) -> bool:
        return self._connected

    def poll(self) -> None:
        if not self._connected:
            return
        stream_obj = self._peer._stream
        assert stream_obj is not None
        try:
            data = stream_obj.recv(4096, deadline=net.Deadline.INSTANT)
        except (OSError, SSL.Error, ValueError):
            self._disconnect()
            return
        if data is None:
            return
        if data == b"":
            self._disconnect()
            return
        self._parser.push(data)
        while True:
            parts = self._parser.pull()
            if parts is None:
                break
            cmd, *args = parts
            self.execute_command(cmd, args)

    @property
    def client(self) -> RemoteClient:
        return self._client

    def handle_error(self, cmd: str, message: str, args: list[str]) -> None:
        details = " ".join(args)
        suffix = f" {details}" if details else ""
        logging.getLogger(__name__).warning("Invalid command received: %s%s (%s)", cmd, suffix, message)

    def _disconnect(self) -> None:
        self._peer.close()
        self._connected = False


Connection.__abstractmethods__ = frozenset()


class Server(ABC):
    """Server wrapper for accepting and polling HackVR connections."""

    def __init__(self) -> None:
        self._bindings: list[net.Server] = []
        self._connections: list[Connection] = []
        self._stop_requested = False

    @overload
    def add_binding(
        self,
        protocol: Literal["hackvr", "http+hackvr"],
        hostname: str,
        port: int | None = None,
    ) -> None: ...

    @overload
    def add_binding(
        self,
        protocol: Literal["hackvrs", "https+hackvr"],
        hostname: str,
        port: int | None = None,
        *,
        certificate: net.TlsServerCertificate,
    ) -> None: ...

    def add_binding(
        self,
        protocol: Literal["hackvr", "hackvrs", "http+hackvr", "https+hackvr"],
        hostname: str,
        port: int | None = None,
        *,
        certificate: net.TlsServerCertificate | None = None,
    ) -> None:
        default_port = _default_port(protocol)
        resolved_port = default_port if port is None else port
        if protocol in {"hackvrs", "https+hackvr"} and certificate is None:
            raise ValueError("TLS bindings require a certificate")
        if protocol in {"hackvr", "http+hackvr"} and certificate is not None:
            raise ValueError("Non-TLS bindings do not use certificates")

        addresses = _resolve_addresses(hostname, resolved_port)
        bindings: list[net.Server] = []
        try:
            for address in addresses:
                bindings.append(  # noqa: PERF401
                    _create_net_server(
                        protocol,
                        address,
                        resolved_port,
                        certificate=certificate,
                    )
                )
        except Exception:
            for binding in bindings:
                binding.close()
            raise
        self._bindings.extend(bindings)

    @abstractmethod
    def accept_client(self, peer: net.Peer, connection_token: net.ConnectionToken) -> Connection:
        """Create a Connection instance for an accepted client."""

    def handle_disconnect(self, _connection: Connection) -> None:
        """Handle connection disconnection."""
        logging.getLogger(__name__).debug("Connection disconnected: %s", _connection)

    def stop(self) -> None:
        """Stop the server loop."""
        self._stop_requested = True

    def serve_forever(self) -> None:
        while not self._stop_requested:
            self._accept_new_connections()
            self._poll_connections()
            time.sleep(0.01)

    def _accept_new_connections(self) -> None:
        for binding in list(self._bindings):
            result = binding.accept(net.Deadline.INSTANT)
            if result is None:
                continue
            peer, token = result
            connection = self.accept_client(peer, token)
            self._connections.append(connection)

    def _poll_connections(self) -> None:
        for connection in list(self._connections):
            connection.poll()
            if not connection.is_connected:
                self._connections.remove(connection)
                self.handle_disconnect(connection)


def _default_port(protocol: str) -> int:
    if protocol == "hackvr":
        return net.HACKVR_PORT
    if protocol == "hackvrs":
        return net.HACKVRS_PORT
    if protocol == "http+hackvr":
        return 80
    if protocol == "https+hackvr":
        return 443
    raise ValueError(f"Unsupported protocol: {protocol}")


def _resolve_addresses(hostname: str, port: int) -> list[str]:
    if hostname == "*":
        return ["0.0.0.0", "::"]
    addresses: set[str] = {
        str(entry[4][0])
        for entry in socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    }
    if not addresses:
        raise ValueError(f"No addresses resolved for host {hostname}")
    return sorted(addresses)


def _create_net_server(
    protocol: str,
    hostname: str,
    port: int,
    *,
    certificate: net.TlsServerCertificate | None = None,
) -> net.Server:
    if protocol == "hackvr":
        return net.RawServer(hostname, port)
    if protocol == "hackvrs":
        if certificate is None:
            raise ValueError("TLS bindings require a certificate")
        listener = net.TlsListener(hostname, port, certificate)
        return net.TlsServer(hostname, port, listener=listener)
    if protocol == "http+hackvr":
        return net.HttpServer(hostname, port)
    if protocol == "https+hackvr":
        if certificate is None:
            raise ValueError("TLS bindings require a certificate")
        listener = net.TlsListener(hostname, port, certificate)
        return net.HttpsServer(hostname, port, listener=listener)
    raise ValueError(f"Unsupported protocol: {protocol}")
