from __future__ import annotations

import base64

import pytest
from typing import cast

from hackvr import RemoteClient, RemoteServer
from hackvr.common import types


class _TestRemoteServer(RemoteServer):
    def __init__(self, expected: list[bytes]) -> None:
        self.expected = expected

    def send_packet(self, data: bytes) -> None:
        assert data == self.expected.pop(0)


class _TestRemoteClient(RemoteClient):
    def __init__(self, expected: list[bytes]) -> None:
        self.expected = expected

    def send_packet(self, data: bytes) -> None:
        assert data == self.expected.pop(0)


class _CollectRemoteClient(RemoteClient):
    def __init__(self) -> None:
        self.packets: list[bytes] = []

    def send_packet(self, data: bytes) -> None:
        self.packets.append(data)


class _CollectRemoteServer(RemoteServer):
    def __init__(self) -> None:
        self.packets: list[bytes] = []

    def send_packet(self, data: bytes) -> None:
        self.packets.append(data)


def _packet_command(packet: bytes) -> str:
    return packet.decode("utf-8").split("\t", 1)[0].strip()


def test_remote_server_serialization() -> None:
    signature = types.Bytes64(bytes(range(64)))
    token_bytes = bytes(range(32))
    token = types.SessionToken(token_bytes)
    token_text = base64.urlsafe_b64encode(token_bytes).decode("ascii").rstrip("=")

    expected = [
        b"chat\thello\r\n",
        b"set-user\tuser-1\r\n",
        f"authenticate\tuser-1\t{bytes(range(64)).hex()}\r\n".encode("utf-8"),
        f"resume-session\t{token_text}\r\n".encode("utf-8"),
        b"tap-object\tobj-1\tprimary\ttag-1\r\n",
        b"intent\tintent-1\t(1 2 -3.5)\r\n",
        b"raycast\t(0 1 0)\t(0 0 -1)\r\n",
        b"raycast-cancel\r\n",
    ]

    server = _TestRemoteServer(expected)
    server.chat("hello")
    server.set_user(types.UserID("user-1"))
    server.authenticate(types.UserID("user-1"), signature)
    server.resume_session(token)
    server.tap_object(
        types.ObjectID("obj-1"),
        types.TapKind.PRIMARY,
        types.Tag("tag-1"),
    )
    server.intent(types.IntentID("intent-1"), types.Vec3(1.0, 2.0, -3.5))
    server.raycast(types.Vec3(0.0, 1.0, 0.0), types.Vec3(0.0, 0.0, -1.0))
    server.raycast_cancel()

    assert not server.expected


def test_remote_client_serialization() -> None:
    nonce = types.Bytes16(bytes(range(16)))
    token_bytes = bytes(range(32))
    token = types.SessionToken(token_bytes)
    token_text = base64.urlsafe_b64encode(token_bytes).decode("ascii").rstrip("=")
    triangles = [
        (
            types.Color("#ff00ff"),
            types.Vec3(0.0, 0.0, 0.0),
            types.Vec3(1.0, 0.0, 0.0),
            types.Vec3(0.0, 1.0, 0.0),
        ),
        (
            types.Color("#00ff00"),
            types.Vec3(0.0, 0.0, 1.0),
            types.Vec3(1.0, 0.0, 1.0),
            types.Vec3(0.0, 1.0, 1.0),
        ),
    ]

    expected = [
        b"request-user\t\r\n",
        f"request-authentication\tuser-1\t{bytes(range(16)).hex()}\r\n".encode("utf-8"),
        f"announce-session\t{token_text}\t\r\n".encode("utf-8"),
        (
            "add-triangle-list\tgeom-1\t\t#ff00ff\t(0 0 0)\t(1 0 0)\t(0 1 0)\t#00ff00\t(0 0 1)\t(1 0 1)\t(0 1 1)\r\n"
        ).encode("utf-8"),
        b"set-object-transform\tobj-1\t(0 1 2)\t\t(1 1 1)\t0.5\r\n",
        b"enable-free-look\ttrue\r\n",
        b"set-background-color\t#ff00ff\r\n",
    ]

    client = _TestRemoteClient(expected)
    client.request_user(None)
    client.request_authentication(types.UserID("user-1"), nonce)
    client.announce_session(token, None)
    client.add_triangle_list("geom-1", None, triangles)
    client.set_object_transform(
        "obj-1",
        types.Vec3(0.0, 1.0, 2.0),
        None,
        types.Vec3(1.0, 1.0, 1.0),
        0.5,
    )
    client.enable_free_look(True)
    client.set_background_color(types.Color("#ff00ff"))

    assert not client.expected


def test_remote_client_all_commands() -> None:
    client = _CollectRemoteClient()
    user = types.UserID("user-1")
    nonce = types.Bytes16(bytes(range(16)))
    token_bytes = bytes(range(32))
    token = types.SessionToken(token_bytes)
    geom_id = "geom-1"
    obj_id = "obj-1"
    intent_id = types.IntentID("intent-1")
    tag = types.Tag("tag-1")
    color = types.Color("#00ff00")
    vec2 = types.Vec2(1.0, 2.0)
    vec3 = types.Vec3(-0.0, 1.0, 2.0)
    uri = types.URI("https://example.com")
    sha = types.Bytes32(bytes(range(32)))

    client.chat(user, "hello")
    client.request_user("prompt")
    client.request_authentication(user, nonce)
    client.accept_user(user)
    client.reject_user(user, "reason")
    client.announce_session(token, 15)
    client.revoke_session(token)
    client.request_input("prompt", "default")
    client.cancel_input()
    client.set_banner("hello", -0.0)
    client.create_intent(intent_id, "label")
    client.destroy_intent(intent_id)
    client.raycast_request()
    client.raycast_cancel()
    client.create_geometry(geom_id)
    client.destroy_geometry(geom_id)
    client.add_triangle_list(
        geom_id,
        tag,
        [
            (
                color,
                types.Vec3(0.0, 0.0, 0.0),
                types.Vec3(1.0, 0.0, 0.0),
                types.Vec3(0.0, 1.0, 0.0),
            ),
        ],
    )
    client.add_triangle_strip(
        geom_id,
        None,
        color,
        types.Vec3(0.0, 0.0, 0.0),
        types.Vec3(1.0, 0.0, 0.0),
        types.Vec3(0.0, 1.0, 0.0),
        [types.Vec3(1.0, 1.0, 0.0)],
    )
    client.add_triangle_fan(
        geom_id,
        None,
        color,
        types.Vec3(0.0, 0.0, 0.0),
        types.Vec3(1.0, 0.0, 0.0),
        types.Vec3(0.0, 1.0, 0.0),
        [types.Vec3(1.0, 1.0, 0.0)],
    )
    client.remove_triangles(geom_id, "tag-1")
    client.create_text_geometry(geom_id, vec2, uri, sha, "text", None)
    client.create_sprite_geometry(geom_id, vec2, uri, sha, None, None)
    client.set_text_property(geom_id, "text", types.AnyValue("value"))
    client.create_object(obj_id, types.GeomID("geom-2"))
    client.destroy_object(obj_id)
    client.reparent_object(types.ObjectID("parent-1"), "child-1", None)
    client.set_object_geometry(obj_id, None)
    client.set_object_property(obj_id, "prop", types.AnyValue("value"))
    client.set_object_transform(
        obj_id,
        vec3,
        types.Euler(0.0, 1.0, 2.0),
        types.Vec3(1.0, 1.0, 1.0),
        0.5,
    )
    client.track_object(obj_id, None, None, None)
    client.enable_free_look(False)
    client.set_background_color(color)

    commands = [_packet_command(packet) for packet in client.packets]
    assert commands == [
        "chat",
        "request-user",
        "request-authentication",
        "accept-user",
        "reject-user",
        "announce-session",
        "revoke-session",
        "request-input",
        "cancel-input",
        "set-banner",
        "create-intent",
        "destroy-intent",
        "raycast-request",
        "raycast-cancel",
        "create-geometry",
        "destroy-geometry",
        "add-triangle-list",
        "add-triangle-strip",
        "add-triangle-fan",
        "remove-triangles",
        "create-text-geometry",
        "create-sprite-geometry",
        "set-text-property",
        "create-object",
        "destroy-object",
        "reparent-object",
        "set-object-geometry",
        "set-object-property",
        "set-object-transform",
        "track-object",
        "enable-free-look",
        "set-background-color",
    ]
    assert client.packets[9].decode("utf-8").endswith("\thello\t0\r\n")


def test_remote_client_rejects_bad_triangle_tuple() -> None:
    client = _CollectRemoteClient()
    bad_triangles = cast(
        "list[tuple[types.Color, types.Vec3, types.Vec3, types.Vec3]]",
        [(types.Color("#ff00ff"), types.Vec3(0.0, 0.0, 0.0))],
    )
    with pytest.raises(ValueError, match="tuple length does not match serializers"):
        client.add_triangle_list(
            "geom-1",
            None,
            bad_triangles,
        )


def test_remote_server_all_commands() -> None:
    server = _CollectRemoteServer()
    server.chat("hello")
    server.set_user(types.UserID("user-1"))
    server.authenticate(types.UserID("user-1"), types.Bytes64(bytes(range(64))))
    token = types.SessionToken(bytes(range(32)))
    server.resume_session(token)
    server.send_input("input")
    server.tap_object(types.ObjectID("obj-1"), types.TapKind.PRIMARY, types.Tag("tag-1"))
    server.tell_object(types.ObjectID("obj-1"), "hello")
    server.intent(types.IntentID("intent-1"), types.Vec3(1.0, 2.0, 3.0))
    server.raycast(types.Vec3(0.0, 1.0, 0.0), types.Vec3(0.0, 0.0, -1.0))
    server.raycast_cancel()

    commands = [_packet_command(packet) for packet in server.packets]
    assert commands == [
        "chat",
        "set-user",
        "authenticate",
        "resume-session",
        "send-input",
        "tap-object",
        "tell-object",
        "intent",
        "raycast",
        "raycast-cancel",
    ]
