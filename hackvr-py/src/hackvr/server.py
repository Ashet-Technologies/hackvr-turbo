"""Server-side (C→S) protocol commands."""

from __future__ import annotations

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
from .common import types


class Server(ProtocolBase):
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
        triangle_params = _serialize_tuple_list(
            triangles,
            [str, _serialize_vec3, _serialize_vec3, _serialize_vec3],
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
