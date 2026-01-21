"""Client-side (S→C) protocol commands."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .base import (
    ProtocolBase,
    RemoteBase,
    _serialize_bytes,
    _serialize_enum,
    _serialize_session_token,
    _serialize_vec3,
    command,
)

if TYPE_CHECKING:
    from .common import types


class Client(ProtocolBase):
    """Client-side protocol handlers for server-to-client commands."""

    @command("chat")
    def chat(self, user: types.UserID, message: str) -> None:
        raise NotImplementedError

    @command("request-user")
    def request_user(self, prompt: types.ZString | None) -> None:
        raise NotImplementedError

    @command("request-authentication")
    def request_authentication(self, user: types.UserID, nonce: types.Bytes16) -> None:
        raise NotImplementedError

    @command("accept-user")
    def accept_user(self, user: types.UserID) -> None:
        raise NotImplementedError

    @command("reject-user")
    def reject_user(self, user: types.UserID, reason: types.ZString | None) -> None:
        raise NotImplementedError

    @command("announce-session")
    def announce_session(self, token: types.SessionToken, lifetime: int | None) -> None:
        raise NotImplementedError

    @command("revoke-session")
    def revoke_session(self, token: types.SessionToken) -> None:
        raise NotImplementedError

    @command("request-input")
    def request_input(self, prompt: str, default: str | None) -> None:
        raise NotImplementedError

    @command("cancel-input")
    def cancel_input(self) -> None:
        raise NotImplementedError

    @command("set-banner")
    def set_banner(self, text: str | None, duration: float | None) -> None:
        raise NotImplementedError

    @command("create-intent")
    def create_intent(self, intent_id: types.IntentID, label: str) -> None:
        raise NotImplementedError

    @command("destroy-intent")
    def destroy_intent(self, intent_id: types.IntentID) -> None:
        raise NotImplementedError

    @command("raycast-request")
    def raycast_request(self) -> None:
        raise NotImplementedError

    @command("raycast-cancel")
    def raycast_cancel(self) -> None:
        raise NotImplementedError

    @command("create-geometry")
    def create_geometry(self, geom_id: str) -> None:
        raise NotImplementedError

    @command("destroy-geometry")
    def destroy_geometry(self, geom_id: str) -> None:
        raise NotImplementedError

    @command("add-triangle-list")
    def add_triangle_list(
        self,
        geom_id: str,
        tag: types.Tag | None,
        triangles: list[tuple[types.Color, types.Vec3, types.Vec3, types.Vec3]],
    ) -> None:
        raise NotImplementedError

    @command("add-triangle-strip")
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
        raise NotImplementedError

    @command("add-triangle-fan")
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
        raise NotImplementedError

    @command("remove-triangles")
    def remove_triangles(self, geom_id: str, tag: str) -> None:
        raise NotImplementedError

    @command("create-text-geometry")
    def create_text_geometry(
        self,
        geom_id: str,
        size: types.Vec2,
        uri: types.URI,
        sha256: types.Bytes32,
        text: str,
        anchor: types.Anchor | None,
    ) -> None:
        raise NotImplementedError

    @command("create-sprite-geometry")
    def create_sprite_geometry(
        self,
        geom_id: str,
        size: types.Vec2,
        uri: types.URI,
        sha256: types.Bytes32,
        size_mode: types.SizeMode | None,
        anchor: types.Anchor | None,
    ) -> None:
        raise NotImplementedError

    @command("set-text-property")
    def set_text_property(
        self,
        geom_id: str,
        property_name: str,
        value: types.AnyValue,
    ) -> None:
        raise NotImplementedError

    @command("create-object")
    def create_object(self, obj_id: str, geom_id: types.GeomID | None) -> None:
        raise NotImplementedError

    @command("destroy-object")
    def destroy_object(self, obj_id: str) -> None:
        raise NotImplementedError

    @command("reparent-object")
    def reparent_object(
        self,
        parent: types.ObjectID,
        child: str,
        transform: types.ReparentMode | None,
    ) -> None:
        raise NotImplementedError

    @command("set-object-geometry")
    def set_object_geometry(self, obj_id: str, geom_id: types.GeomID | None) -> None:
        raise NotImplementedError

    @command("set-object-property")
    def set_object_property(
        self,
        obj_id: str,
        property_name: str,
        value: types.AnyValue,
    ) -> None:
        raise NotImplementedError

    @command("set-object-transform")
    def set_object_transform(
        self,
        obj_id: str,
        pos: types.Vec3 | None,
        rot: types.Euler | None,
        scale: types.Vec3 | None,
        duration: float | None,
    ) -> None:
        raise NotImplementedError

    @command("track-object")
    def track_object(
        self,
        obj_id: str,
        target: types.ObjectID | None,
        mode: types.TrackMode | None,
        duration: float | None,
    ) -> None:
        raise NotImplementedError

    @command("enable-free-look")
    def enable_free_look(self, enabled: bool) -> None:
        raise NotImplementedError

    @command("set-background-color")
    def set_background_color(self, color: types.Color) -> None:
        raise NotImplementedError


class RemoteServer(RemoteBase):
    """Client-side helper for sending client-to-server commands."""

    def chat(self, message: str) -> None:
        self.send_cmd("chat", message)

    def set_user(self, user: types.UserID) -> None:
        self.send_cmd("set-user", str(user))

    def authenticate(self, user: types.UserID, signature: types.Bytes64) -> None:
        self.send_cmd("authenticate", str(user), _serialize_bytes(signature))

    def resume_session(self, token: types.SessionToken) -> None:
        self.send_cmd("resume-session", _serialize_session_token(token))

    def send_input(self, text: types.ZString) -> None:
        self.send_cmd("send-input", text)

    def tap_object(
        self,
        obj: types.ObjectID,
        kind: types.TapKind,
        tag: types.Tag,
    ) -> None:
        self.send_cmd(
            "tap-object",
            str(obj),
            _serialize_enum(kind),
            str(tag),
        )

    def tell_object(self, obj: types.ObjectID, text: types.ZString) -> None:
        self.send_cmd("tell-object", str(obj), text)

    def intent(self, intent_id: types.IntentID, view_dir: types.Vec3) -> None:
        self.send_cmd("intent", str(intent_id), _serialize_vec3(view_dir))

    def raycast(self, origin: types.Vec3, direction: types.Vec3) -> None:
        self.send_cmd(
            "raycast",
            _serialize_vec3(origin),
            _serialize_vec3(direction),
        )

    def raycast_cancel(self) -> None:
        self.send_cmd("raycast-cancel")
