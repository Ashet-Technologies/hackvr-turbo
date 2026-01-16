from __future__ import annotations

import base64
from typing import Optional

import pytest

from hackvr.base import ProtocolBase, command
from hackvr.common import types


class BaseProtocol(ProtocolBase):
    @command("all-types")
    def all_types(
        self,
        name: str,
        text: types.ZString,
        count: int,
        ratio: float,
        enabled: bool,
        pos2: types.Vec2,
        pos3: types.Vec3,
        shade: types.Color,
        payload16: types.Bytes16,
        payload32: types.Bytes32,
        payload64: types.Bytes64,
        any_value: types.AnyValue,
        uri: types.URI,
        user: types.UserID,
        obj: types.ObjectID,
        geom: types.GeomID,
        intent: types.IntentID,
        tag: types.Tag,
        tap: types.TapKind,
        size: types.SizeMode,
        track: types.TrackMode,
        reparent: types.ReparentMode,
        anchor: types.Anchor,
        version: types.Version,
        euler: types.Euler,
        session: types.SessionToken,
    ) -> None:
        raise NotImplementedError

    @command("optional-values")
    def optional_values(
        self,
        maybe_count: Optional[int],
        maybe_ratio: float | None,
    ) -> None:
        raise NotImplementedError

class Server(BaseProtocol):
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...]]] = []
        self.errors: list[tuple[str, str, list[str]]] = []

    def handle_error(self, cmd: str, message: str, args: list[str]) -> None:
        self.errors.append((cmd, message, args))

    def all_types(self, *args: object) -> None:
        self.calls.append(("all-types", args))

    def optional_values(self, *args: object) -> None:
        self.calls.append(("optional-values", args))


def test_execute_command_parses_all_types():
    server = Server()
    token = base64.urlsafe_b64encode(bytes(range(32))).decode("ascii").rstrip("=")
    args = [
        "name",
        "text",
        "12",
        "3.5",
        "true",
        "(1 2)",
        "(3 4 5)",
        "#aabbcc",
        "aa" * 16,
        "bb" * 32,
        "cc" * 64,
        "any",
        "https://example.com",
        "user",
        "obj-1",
        "geom-1",
        "intent-1",
        "tag-1",
        "primary",
        "cover",
        "plane",
        "local",
        "top-left",
        "v2",
        "(0 1 2)",
        token,
    ]
    server.execute_command("all-types", args)

    assert server.errors == []
    assert len(server.calls) == 1
    _, parsed = server.calls[0]
    assert parsed[0] == "name"
    assert parsed[1] == "text"
    assert parsed[2] == 12
    assert parsed[3] == 3.5
    assert parsed[4] is True
    assert parsed[5] == types.Vec2(1.0, 2.0)
    assert parsed[6] == types.Vec3(3.0, 4.0, 5.0)
    assert parsed[18] == types.TapKind.PRIMARY
    assert parsed[19] == types.SizeMode.COVER
    assert parsed[20] == types.TrackMode.PLANE
    assert parsed[21] == types.ReparentMode.LOCAL
    assert parsed[22] == types.Anchor.TOP_LEFT
    assert parsed[24] == types.Euler(0.0, 1.0, 2.0)


def test_execute_command_optional_values():
    server = Server()
    server.execute_command("optional-values", ["", ""])
    assert server.calls[0][1] == (None, None)

    server.execute_command("optional-values", ["5", "1.25"])
    assert server.calls[1][1] == (5, 1.25)


def test_execute_command_unknown_and_invalid():
    server = Server()
    server.execute_command("missing", [])
    assert server.errors[0][0] == "missing"

    server.execute_command("optional-values", ["bad", "1.0"])
    assert server.errors[1][0] == "optional-values"


def test_zstring_cannot_be_optional():
    with pytest.raises(TypeError):
        class BadZstring(ProtocolBase):
            @command("bad-zstring")
            def bad_zstring(self, value: types.ZString | None) -> None:
                raise NotImplementedError
