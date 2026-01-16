"""Base protocol dispatcher for HackVR commands."""

from __future__ import annotations

import inspect
from abc import ABC, abstractmethod
from dataclasses import dataclass
from types import UnionType
from typing import Any, Callable, Union, get_args, get_origin, get_type_hints

from .common import types


@dataclass(frozen=True)
class _CommandSpec:
    name: str
    method_name: str
    func: Callable[..., None]
    parameters: list[inspect.Parameter]


def command(name: str) -> Callable[[Callable[..., None]], Callable[..., None]]:
    def decorator(func: Callable[..., None]) -> Callable[..., None]:
        setattr(func, "__command_name__", name)  # noqa: B010
        setattr(func, "__isabstractmethod__", True)  # noqa: B010
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
            if signature.return_annotation not in (
                inspect.Signature.empty,
                None,
                type(None),
                "None",
            ):
                raise TypeError(f"@command {command_name} must return None")
            parameters = list(signature.parameters.values())
            if not parameters or parameters[0].name != "self":
                raise TypeError(f"@command {command_name} must be an instance method")
            type_hints = get_type_hints(attr, include_extras=True)
            for param in parameters[1:]:
                annotation = type_hints.get(param.name, str)
                optional, inner = _unwrap_optional(annotation)
                if optional and _is_list_annotation(inner):
                    raise TypeError(
                        f"@command {command_name} cannot use optional list parameters"
                    )
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

    @abstractmethod
    def handle_error(self, cmd: str, message: str, args: list[str]) -> None:
        raise NotImplementedError

    def _lookup_command(self, cmd: str) -> _CommandSpec | None:
        for cls in type(self).mro():
            if not issubclass(cls, ProtocolBase):
                continue
            command_specs = cls._command_specs
            if cmd in command_specs:
                return command_specs[cmd]
        return None

    def _parse_args(self, spec: _CommandSpec, args: list[str]) -> list[Any]:
        type_hints = get_type_hints(spec.func, include_extras=True)
        parsed_args: list[Any] = []
        for index, param in enumerate(spec.parameters):
            annotation = type_hints.get(param.name, str)
            optional, inner = _unwrap_optional(annotation)
            if _is_list_annotation(inner):
                if index != len(spec.parameters) - 1:
                    raise ValueError("list parameters must be last")
                remaining = args[index:] if index < len(args) else []
                parsed_args.append(self._parse_list(inner, remaining))
                return parsed_args
            value = args[index] if index < len(args) else ""
            if not optional:
                assert value is not None
            parsed_args.append(self._parse_value(inner, value, optional))
        return parsed_args

    def _parse_value(self, annotation: Any, value: str, optional: bool) -> Any:
        if types.is_zstring_annotation(annotation):
            return types.parse_zstring(value, optional)
        parser_map: dict[Any, Callable[[str, bool], Any]] = {
            str: types.parse_string,
            int: types.parse_int,
            float: types.parse_float,
            bool: types.parse_bool,
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

    def _parse_list(self, annotation: Any, values: list[str]) -> list[Any]:
        inner = _list_inner(annotation)
        if inner is None:
            raise ValueError("unsupported list annotation")
        origin = get_origin(inner)
        if origin is tuple:
            typeset = get_args(inner)
            if not typeset:
                return []
            if len(values) % len(typeset) != 0:
                raise ValueError("list tuple payload does not align")
            output = []
            for offset in range(0, len(values), len(typeset)):
                chunk = values[offset : offset + len(typeset)]
                output.append(
                    tuple(
                        self._parse_value(type_hint, chunk_value, False)
                        for type_hint, chunk_value in zip(typeset, chunk, strict=False)
                    )
                )
            return output
        return [self._parse_value(inner, item, False) for item in values]


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


def _is_list_annotation(annotation: Any) -> bool:
    return get_origin(annotation) is list


def _list_inner(annotation: Any) -> Any | None:
    if get_origin(annotation) is not list:
        return None
    args = get_args(annotation)
    if len(args) != 1:
        return None
    return args[0]
