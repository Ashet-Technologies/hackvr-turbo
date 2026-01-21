from __future__ import annotations

import base64

from hackvr import RemoteClient, RemoteServer
from hackvr.common import types


class TestRemoteServer(RemoteServer):
    def __init__(self, expected: list[bytes]) -> None:
        self.expected = expected

    def send_packet(self, data: bytes) -> None:
        assert data == self.expected.pop(0)


class TestRemoteClient(RemoteClient):
    def __init__(self, expected: list[bytes]) -> None:
        self.expected = expected

    def send_packet(self, data: bytes) -> None:
        assert data == self.expected.pop(0)


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

    server = TestRemoteServer(expected)
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

    client = TestRemoteClient(expected)
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
