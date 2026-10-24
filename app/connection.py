from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from urllib.parse import urlparse

from app.security import validate_server_url


class ConnectionMode(str, Enum):
    SELF_HOST = "local"
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
            ConnectionMode.EXTERNAL_SERVER: "EXTERNAL SERVER",
        }[self.mode]

    @property
    def config_value(self) -> str:
        return self.mode.value

    @property
    def requires_tunnel(self) -> bool:
        return False

    @property
    def requires_agent_url(self) -> bool:
        return self.mode is ConnectionMode.EXTERNAL_SERVER

    def configure_store(self, store, local_url: str, public_url: str = "") -> None:
        urls = {
            ConnectionMode.SELF_HOST: local_url,
            ConnectionMode.EXTERNAL_SERVER: "",
        }
        store.set_agent_base_url(urls[self.mode])

    def build_agent_url(self, public_url: str = "") -> str:
        return ""

    def validate_agent_url(self, value: str) -> bool:
        if not value:
            return False
        try:
            validate_server_url(value, allow_insecure_loopback=False)
        except ValueError:
            return False
        parsed = urlparse(value)
        return bool(parsed.scheme == "https" and parsed.netloc and parsed.path.endswith("/api/agent/heartbeat"))