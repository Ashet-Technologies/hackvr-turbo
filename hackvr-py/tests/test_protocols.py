from __future__ import annotations

import pytest

from hackvr import AbstractClient as Client, AbstractServer as Server
from hackvr.common import types

SERVER_COMMANDS = {
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
}

CLIENT_COMMANDS = {
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
}


def _make_collector(base_cls):
    methods = {}

    def handle_error(self, cmd, message, args):
        self.errors.append((cmd, message, args))

    methods["handle_error"] = handle_error

    for cmd, spec in base_cls._command_specs.items():

        def _factory(command_name):
            def _handler(self, *args):
                self.calls.append((command_name, args))

            return _handler

        methods[spec.method_name] = _factory(cmd)

    return type(f"Dummy{base_cls.__name__}", (base_cls,), methods)


def test_command_registration():
    assert set(Server._command_specs) == SERVER_COMMANDS
    assert set(Client._command_specs) == CLIENT_COMMANDS


def test_server_dispatch():
    DummyServer = _make_collector(Server)
    server = DummyServer()
    server.calls = []
    server.errors = []

    server.execute_command("chat", ["hello"])
    server.execute_command("set-user", ["user-1"])
    server.execute_command("raycast-cancel", [])

    assert server.errors == []
    assert server.calls[0][0] == "chat"
    assert server.calls[1][0] == "set-user"
    assert server.calls[2][0] == "raycast-cancel"


def test_client_dispatch_with_lists():
    DummyClient = _make_collector(Client)
    client = DummyClient()
    client.calls = []
    client.errors = []

    client.execute_command(
        "add-triangle-list",
        [
            "geom-1",
            "",
            "#ff00ff",
            "(0 0 0)",
            "(1 0 0)",
            "(0 1 0)",
            "#00ff00",
            "(0 0 1)",
            "(1 0 1)",
            "(0 1 1)",
        ],
    )
    client.execute_command(
        "add-triangle-strip",
        ["geom-2", "", "#ffffff", "(0 0 0)", "(1 0 0)", "(0 1 0)", "(1 1 0)"],
    )
    client.execute_command("create-object", ["obj-1", "geom-2"])

    assert client.errors == []
    command, args = client.calls[0]
    assert command == "add-triangle-list"
    assert args[0] == "geom-1"
    assert args[1] is None
    triangles = args[2]
    assert len(triangles) == 2
    assert triangles[0][0] == types.Color("#ff00ff")
    assert triangles[0][1] == types.Vec3(0.0, 0.0, 0.0)

    command, args = client.calls[1]
    assert command == "add-triangle-strip"
    assert args[-1] == [types.Vec3(1.0, 1.0, 0.0)]


def _make_raiser(base_cls):
    methods = {}

    def handle_error(self, cmd, message, args):
        raise NotImplementedError

    methods["handle_error"] = handle_error

    for spec in base_cls._command_specs.values():

        def _factory(method_name):
            def _handler(self, *args):
                return getattr(base_cls, method_name)(self, *args)

            return _handler

        methods[spec.method_name] = _factory(spec.method_name)

    return type(f"Raising{base_cls.__name__}", (base_cls,), methods)


def test_client_methods_raise_not_implemented():
    RaisingClient = _make_raiser(Client)
    client = RaisingClient()
    token = types.SessionToken(bytes(range(32)))
    vec2 = types.Vec2(1.0, 2.0)
    vec3 = types.Vec3(0.0, 1.0, 2.0)
    euler = types.Euler(0.0, 1.0, 2.0)
    with pytest.raises(NotImplementedError):
        client.chat(types.UserID("user-1"), "hello")
    with pytest.raises(NotImplementedError):
        client.request_user("prompt")
    with pytest.raises(NotImplementedError):
        client.request_authentication(types.UserID("user-1"), types.Bytes16(bytes(range(16))))
    with pytest.raises(NotImplementedError):
        client.accept_user(types.UserID("user-1"))
    with pytest.raises(NotImplementedError):
        client.reject_user(types.UserID("user-1"), "reason")
    with pytest.raises(NotImplementedError):
        client.announce_session(token, 10)
    with pytest.raises(NotImplementedError):
        client.revoke_session(token)
    with pytest.raises(NotImplementedError):
        client.request_input("prompt", "default")
    with pytest.raises(NotImplementedError):
        client.cancel_input()
    with pytest.raises(NotImplementedError):
        client.set_banner("text", 1.0)
    with pytest.raises(NotImplementedError):
        client.create_intent(types.IntentID("intent-1"), "label")
    with pytest.raises(NotImplementedError):
        client.destroy_intent(types.IntentID("intent-1"))
    with pytest.raises(NotImplementedError):
        client.raycast_request()
    with pytest.raises(NotImplementedError):
        client.raycast_cancel()
    with pytest.raises(NotImplementedError):
        client.create_geometry("geom-1")
    with pytest.raises(NotImplementedError):
        client.destroy_geometry("geom-1")
    with pytest.raises(NotImplementedError):
        client.add_triangle_list(
            "geom-1",
            None,
            [
                (
                    types.Color("#ff00ff"),
                    types.Vec3(0.0, 0.0, 0.0),
                    types.Vec3(1.0, 0.0, 0.0),
                    types.Vec3(0.0, 1.0, 0.0),
                )
            ],
        )
    with pytest.raises(NotImplementedError):
        client.add_triangle_strip(
            "geom-1",
            None,
            types.Color("#ff00ff"),
            vec3,
            vec3,
            vec3,
            [vec3],
        )
    with pytest.raises(NotImplementedError):
        client.add_triangle_fan(
            "geom-1",
            None,
            types.Color("#ff00ff"),
            vec3,
            vec3,
            vec3,
            [vec3],
        )
    with pytest.raises(NotImplementedError):
        client.remove_triangles("geom-1", "tag-1")
    with pytest.raises(NotImplementedError):
        client.create_text_geometry(
            "geom-1",
            vec2,
            types.URI("https://example.com"),
            types.Bytes32(bytes(range(32))),
            "text",
            None,
        )
    with pytest.raises(NotImplementedError):
        client.create_sprite_geometry(
            "geom-1",
            vec2,
            types.URI("https://example.com"),
            types.Bytes32(bytes(range(32))),
            None,
            None,
        )
    with pytest.raises(NotImplementedError):
        client.set_text_property("geom-1", "prop", types.AnyValue("value"))
    with pytest.raises(NotImplementedError):
        client.create_object("obj-1", types.GeomID("geom-1"))
    with pytest.raises(NotImplementedError):
        client.destroy_object("obj-1")
    with pytest.raises(NotImplementedError):
        client.reparent_object(types.ObjectID("parent-1"), "child-1", None)
    with pytest.raises(NotImplementedError):
        client.set_object_geometry("obj-1", None)
    with pytest.raises(NotImplementedError):
        client.set_object_property("obj-1", "prop", types.AnyValue("value"))
    with pytest.raises(NotImplementedError):
        client.set_object_transform("obj-1", vec3, euler, vec3, 0.5)
    with pytest.raises(NotImplementedError):
        client.track_object("obj-1", None, None, None)
    with pytest.raises(NotImplementedError):
        client.enable_free_look(True)
    with pytest.raises(NotImplementedError):
        client.set_background_color(types.Color("#ff00ff"))


def test_server_methods_raise_not_implemented():
    RaisingServer = _make_raiser(Server)
    server = RaisingServer()
    with pytest.raises(NotImplementedError):
        server.chat("hello")
    with pytest.raises(NotImplementedError):
        server.set_user(types.UserID("user-1"))
    with pytest.raises(NotImplementedError):
        server.authenticate(types.UserID("user-1"), types.Bytes64(bytes(range(64))))
    with pytest.raises(NotImplementedError):
        server.resume_session(types.SessionToken(bytes(range(32))))
    with pytest.raises(NotImplementedError):
        server.send_input("input")
    with pytest.raises(NotImplementedError):
        server.tap_object(types.ObjectID("obj-1"), types.TapKind.PRIMARY, types.Tag("tag-1"))
    with pytest.raises(NotImplementedError):
        server.tell_object(types.ObjectID("obj-1"), "hello")
    with pytest.raises(NotImplementedError):
        server.intent(types.IntentID("intent-1"), types.Vec3(1.0, 2.0, 3.0))
    with pytest.raises(NotImplementedError):
        server.raycast(types.Vec3(0.0, 1.0, 0.0), types.Vec3(0.0, 0.0, -1.0))
    with pytest.raises(NotImplementedError):
        server.raycast_cancel()
