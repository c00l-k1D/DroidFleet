from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from urllib.parse import urlparse


class ConnectionMode(str, Enum):
    SELF_HOST = "local"
    NGROK = "ngrok"
    EXTERNAL_SERVER = "external"


@dataclass(frozen=True)
class ConnectionProfile:
    mode: ConnectionMode

    @classmethod
    def from_value(cls, value: str | ConnectionMode) -> "ConnectionProfile":
        try:
            mode = value if isinstance(value, ConnectionMode) else ConnectionMode(str(value).casefold())
        except ValueError:
            mode = ConnectionMode.SELF_HOST
        return cls(mode)

    @property
    def label(self) -> str:
        return {
            ConnectionMode.SELF_HOST: "SELF-HOST",
            ConnectionMode.NGROK: "NGROK",
            ConnectionMode.EXTERNAL_SERVER: "EXTERNAL SERVER",
        }[self.mode]

    @property
    def config_value(self) -> str:
        return self.mode.value

    @property
    def requires_tunnel(self) -> bool:
        return self.mode is ConnectionMode.NGROK

    @property
    def requires_agent_url(self) -> bool:
        return self.mode in {ConnectionMode.NGROK, ConnectionMode.EXTERNAL_SERVER}

    def configure_store(self, store, local_url: str, public_url: str = "") -> None:
        urls = {
            ConnectionMode.SELF_HOST: local_url,
            ConnectionMode.NGROK: f"{public_url.rstrip('/')}/api/agent" if public_url else "",
            ConnectionMode.EXTERNAL_SERVER: "",
        }
        store.set_agent_base_url(urls[self.mode])

    def build_agent_url(self, public_url: str = "") -> str:
        if self.mode is ConnectionMode.NGROK and public_url:
            return f"{public_url.rstrip('/')}/api/agent/heartbeat"
        return ""

    def validate_agent_url(self, value: str) -> bool:
        parsed = urlparse(value)
        if self.mode is ConnectionMode.NGROK:
            return parsed.scheme == "https" and bool(parsed.netloc) and parsed.path == "/api/agent/heartbeat"
        if self.mode is ConnectionMode.EXTERNAL_SERVER:
            return bool(parsed.scheme in {"http", "https"} and parsed.netloc and parsed.path.endswith("/api/agent/heartbeat"))
        return True