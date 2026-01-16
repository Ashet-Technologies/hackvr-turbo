"""Server-side (C→S) protocol commands."""

from __future__ import annotations

from .base import ProtocolBase, command
from .common import types


class Server(ProtocolBase):
    @command("hackvr-hello")
    def hackvr_hello(
        self,
        max_version: types.Version,
        uri: types.URI,
        session_token: types.SessionToken | None,
    ) -> None:
        raise NotImplementedError

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
