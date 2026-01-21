from __future__ import annotations

from hackvr import Client, Server
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
