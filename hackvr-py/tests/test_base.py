from __future__ import annotations

import base64

import pytest
from typing import Optional, Tuple, cast

from hackvr.base import ProtocolBase, RemoteBase, command
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


class AbstractListProtocol(ProtocolBase):
    @command("items")
    def items(self, values: list[int]) -> None:
        raise NotImplementedError

    @command("tuple-items")
    def tuple_items(self, values: list[tuple[types.Vec3, types.Vec3]]) -> None:
        raise NotImplementedError

    @command("empty-tuple-list")
    def empty_tuple_list(self, values: list[Tuple]) -> None:
        raise NotImplementedError

    @command("list-not-last")
    def list_not_last(self, values: list[int], extra: int) -> None:
        raise NotImplementedError

    @command("unsupported-annotation")
    def unsupported_annotation(self, payload: dict) -> None:
        raise NotImplementedError


class ListProtocol(AbstractListProtocol):
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...]]] = []
        self.errors: list[tuple[str, str, list[str]]] = []

    def handle_error(self, cmd: str, message: str, args: list[str]) -> None:
        self.errors.append((cmd, message, args))

    def items(self, values: list[int]) -> None:
        self.calls.append(("items", (values,)))

    def tuple_items(self, values: list[tuple[types.Vec3, types.Vec3]]) -> None:
        self.calls.append(("tuple-items", (values,)))

    def empty_tuple_list(self, values: list[Tuple]) -> None:
        self.calls.append(("empty-tuple-list", (values,)))

    def list_not_last(self, values: list[int], extra: int) -> None:
        self.calls.append(("list-not-last", (values, extra)))

    def unsupported_annotation(self, payload: dict) -> None:
        self.calls.append(("unsupported-annotation", (payload,)))


class ErrorProtocol(ProtocolBase):
    def handle_error(self, cmd: str, message: str, args: list[str]) -> None:
        super().handle_error(cmd, message, args)


class ErrorRemote(RemoteBase):
    def send_packet(self, data: bytes) -> None:
        super().send_packet(data)


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


def test_optional_zstring_is_allowed():
    class OptionalZstring(ProtocolBase):
        @command("optional-zstring")
        def optional_zstring(self, value: types.ZString | None) -> None:
            raise NotImplementedError

        def handle_error(self, cmd: str, message: str, args: list[str]) -> None:
            raise NotImplementedError


def test_parse_list_and_tuple_list():
    server = ListProtocol()
    server.execute_command("items", ["1", "2", "3"])
    assert server.errors == []
    assert server.calls[0][1] == ([1, 2, 3],)

    server.execute_command(
        "tuple-items",
        ["(0 0 0)", "(1 1 1)", "(2 2 2)", "(3 3 3)"],
    )
    assert server.errors == []
    _, parsed = server.calls[1]
    tuples = cast(list[tuple[types.Vec3, types.Vec3]], parsed[0])
    assert tuples[0] == (types.Vec3(0.0, 0.0, 0.0), types.Vec3(1.0, 1.0, 1.0))
    assert tuples[1] == (types.Vec3(2.0, 2.0, 2.0), types.Vec3(3.0, 3.0, 3.0))

    server.execute_command("empty-tuple-list", ["1", "2"])
    assert server.calls[2][1] == ([],)


def test_list_parsing_errors():
    server = ListProtocol()
    server.execute_command("tuple-items", ["(0 0 0)"])
    assert "list tuple payload does not align" in server.errors[0][1]

    server.execute_command("list-not-last", ["1", "2"])
    assert "list parameters must be last" in server.errors[1][1]

    server.execute_command("unsupported-annotation", ["value"])
    assert "unsupported type annotation" in server.errors[2][1]


def test_command_signature_validation():
    with pytest.raises(TypeError):
        class BadReturn(ProtocolBase):
            @command("bad-return")
            def bad_return(self) -> int:
                return 1

            def handle_error(self, cmd: str, message: str, args: list[str]) -> None:
                raise NotImplementedError

    with pytest.raises(TypeError):
        class NoSelf(ProtocolBase):
            @command("no-self")
            def no_self(value: str) -> None:
                raise NotImplementedError

            def handle_error(self, cmd: str, message: str, args: list[str]) -> None:
                raise NotImplementedError

    with pytest.raises(TypeError):
        class OptionalList(ProtocolBase):
            @command("optional-list")
            def optional_list(self, items: list[int] | None) -> None:
                raise NotImplementedError

            def handle_error(self, cmd: str, message: str, args: list[str]) -> None:
                raise NotImplementedError


def test_protocol_base_handle_error_is_abstract():
    protocol = ErrorProtocol()
    with pytest.raises(NotImplementedError):
        protocol.handle_error("cmd", "message", [])


def test_remote_base_send_packet_is_abstract():
    remote = ErrorRemote()
    with pytest.raises(NotImplementedError):
        remote.send_packet(b"payload")
