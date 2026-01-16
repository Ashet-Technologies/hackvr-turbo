"""Base protocol dispatcher for HackVR commands."""

from __future__ import annotations

from abc import ABC
from dataclasses import dataclass
import inspect
from types import UnionType
from typing import Any, Callable, get_args, get_origin, get_type_hints, Union

from .common import types


@dataclass(frozen=True)
class _CommandSpec:
    name: str
    method_name: str
    func: Callable[..., None]
    parameters: list[inspect.Parameter]


def command(name: str) -> Callable[[Callable[..., None]], Callable[..., None]]:
    def decorator(func: Callable[..., None]) -> Callable[..., None]:
        setattr(func, "__command_name__", name)
        setattr(func, "__isabstractmethod__", True)
        return func

    return decorator


class ProtocolBase(ABC):
    _command_specs: dict[str, _CommandSpec] = {}

    def __init_subclass__(cls) -> None:
        super().__init_subclass__()
        cls._command_specs = {}
        for attr_name, attr in cls.__dict__.items():
            command_name = getattr(attr, "__command_name__", None)
            if command_name is None:
                continue
            signature = inspect.signature(attr)
            if signature.return_annotation not in (inspect.Signature.empty, None, type(None), "None"):
                raise TypeError(f"@command {command_name} must return None")
            parameters = list(signature.parameters.values())
            if not parameters or parameters[0].name != "self":
                raise TypeError(f"@command {command_name} must be an instance method")
            cls._command_specs[command_name] = _CommandSpec(
                name=command_name,
                method_name=attr_name,
                func=attr,
                parameters=parameters[1:],
            )

    def execute_command(self, cmd: str, args: list[str]) -> None:
        spec = self._lookup_command(cmd)
        if spec is None:
            self.handle_error(cmd, "unknown command", args)
            return

        try:
            parsed_args = self._parse_args(spec, args)
        except Exception as exc:  # noqa: BLE001
            self.handle_error(cmd, str(exc), args)
            return

        handler = getattr(self, spec.method_name)
        handler(*parsed_args)

    def handle_error(self, cmd: str, message: str, args: list[str]) -> None:
        _ = cmd, message, args
        return

    def _lookup_command(self, cmd: str) -> _CommandSpec | None:
        for cls in type(self).mro():
            if hasattr(cls, "_command_specs") and cmd in cls._command_specs:
                return cls._command_specs[cmd]
        return None

    def _parse_args(self, spec: _CommandSpec, args: list[str]) -> list[Any]:
        type_hints = get_type_hints(spec.func, include_extras=True)
        parsed_args: list[Any] = []
        for index, param in enumerate(spec.parameters):
            annotation = type_hints.get(param.name, str)
            optional, inner = _unwrap_optional(annotation)
            if optional and inner is types.ZString:
                raise ValueError("zstring cannot be optional")
            value = args[index] if index < len(args) else ""
            if not optional:
                assert value is not None
            parsed_args.append(self._parse_value(inner, value, optional))
        return parsed_args

    def _parse_value(self, annotation: Any, value: str, optional: bool) -> Any:
        parser_map: dict[Any, Callable[[str, bool], Any]] = {
            types.String: types.parse_string,
            types.ZString: types.parse_zstring,
            types.Int: types.parse_int,
            types.Float: types.parse_float,
            types.Bool: types.parse_bool,
            types.Vec2: types.parse_vec2,
            types.Vec3: types.parse_vec3,
            types.Euler: types.parse_euler,
            types.Color: types.parse_color,
            types.Bytes16: types.parse_bytes16,
            types.Bytes32: types.parse_bytes32,
            types.Bytes64: types.parse_bytes64,
            types.AnyValue: types.parse_any,
            types.URI: types.parse_uri,
            types.UserID: types.parse_userid,
            types.ObjectID: types.parse_object,
            types.GeomID: types.parse_geom,
            types.IntentID: types.parse_intent,
            types.Tag: types.parse_tag,
            types.TapKind: types.parse_tapkind,
            types.SizeMode: types.parse_sizemode,
            types.TrackMode: types.parse_track_mode,
            types.ReparentMode: types.parse_reparent_mode,
            types.Anchor: types.parse_anchor,
            types.Version: types.parse_version,
            types.SessionToken: types.parse_session_token,
        }
        parser = parser_map.get(annotation)
        if parser is None:
            raise ValueError(f"unsupported type annotation: {annotation!r}")
        return parser(value, optional)


def _unwrap_optional(annotation: Any) -> tuple[bool, Any]:
    origin = get_origin(annotation)
    if origin is None:
        return False, annotation
    if origin in (Union, UnionType):
        args = get_args(annotation)
        if len(args) == 2 and type(None) in args:
            inner = args[0] if args[1] is type(None) else args[1]
            return True, inner
    return False, annotation
