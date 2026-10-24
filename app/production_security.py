from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _isoformat_utc(ts: float | None = None) -> str:
    value = _utc_now() if ts is None else datetime.fromtimestamp(ts, tz=timezone.utc)
    return value.isoformat().replace("+00:00", "Z")


class Role(str, Enum):
    VIEWER = "viewer"
    OPERATOR = "operator"
    SHELL_OPERATOR = "shell_operator"
    FILE_OPERATOR = "file_operator"
    AGENT_ADMIN = "agent_admin"
    AUDITOR = "auditor"
    SUPERADMIN = "superadmin"


class Permission(str, Enum):
    DEVICE_VIEW = "device.view"
    DEVICE_REBOOT = "device.reboot"
    SHELL_EXECUTE = "shell.execute"
    FILE_TRANSFER = "file.transfer"
    AGENT_ENROLL = "agent.enroll"
    AGENT_REVOKE = "agent.revoke"
    AUDIT_VIEW = "audit.view"
    SETTINGS_WRITE = "settings.write"


ROLE_PERMISSIONS: dict[Role, set[Permission]] = {
    Role.VIEWER: {Permission.DEVICE_VIEW, Permission.AUDIT_VIEW},
    Role.OPERATOR: {Permission.DEVICE_VIEW, Permission.DEVICE_REBOOT, Permission.FILE_TRANSFER},
    Role.SHELL_OPERATOR: {Permission.DEVICE_VIEW, Permission.SHELL_EXECUTE},
    Role.FILE_OPERATOR: {Permission.DEVICE_VIEW, Permission.FILE_TRANSFER},
    Role.AGENT_ADMIN: {Permission.DEVICE_VIEW, Permission.AGENT_ENROLL, Permission.AGENT_REVOKE, Permission.SETTINGS_WRITE},
    Role.AUDITOR: {Permission.DEVICE_VIEW, Permission.AUDIT_VIEW},
    Role.SUPERADMIN: set(Permission),
}


class AccessController:
    @staticmethod
    def can(role: Role | str, permission: Permission | str) -> bool:
        role_name = Role(role) if isinstance(role, str) else role
        permission_name = Permission(permission) if isinstance(permission, str) else permission
        return permission_name in ROLE_PERMISSIONS.get(role_name, set())


class DeviceAccessPolicy:
    def __init__(self, scopes_by_role: dict[Role | str, set[str]] | None = None):
        self.scopes_by_role: dict[Role, set[str]] = {}
        for role, groups in (scopes_by_role or {}).items():
            normalized = Role(role) if isinstance(role, str) else role
            self.scopes_by_role[normalized] = {str(group).strip() for group in groups if str(group).strip()}

    def can_access(self, role: Role | str, group_name: str) -> bool:
        normalized_role = Role(role) if isinstance(role, str) else role
        if normalized_role is Role.SUPERADMIN:
            return True
        allowed = self.scopes_by_role.get(normalized_role, set())
        return bool(group_name) and group_name in allowed

    def filter_targets(self, role: Role | str, serials: list[str], device_groups: dict[str, str]) -> list[str]:
        normalized_role = Role(role) if isinstance(role, str) else role
        if normalized_role is Role.SUPERADMIN:
            return list(serials)
        allowed = self.scopes_by_role.get(normalized_role, set())
        return [serial for serial in serials if device_groups.get(serial, "") in allowed]


class SecurityContext:
    def __init__(self, user: str = "local-admin", role: Role | str = Role.SUPERADMIN, *, mfa_verified: bool = True, scopes: set[str] | None = None):
        self.user = user
        self.role = Role(role) if isinstance(role, str) else role
        self.mfa_verified = mfa_verified
        self.scopes = {str(scope).strip() for scope in (scopes or []) if str(scope).strip()}

    def can_perform(self, permission: Permission | str, target_count: int = 1, *, require_approval: bool = True) -> bool:
        permission_name = Permission(permission) if isinstance(permission, str) else permission
        if not AccessController.can(self.role, permission_name):
            return False
        if require_approval and ApprovalGate.requires_approval(permission_name.value, target_count):
            return self.mfa_verified
        return True

    def filter_targets(self, serials: list[str], device_groups: dict[str, str]) -> list[str]:
        if not self.scopes:
            return list(serials)
        return [serial for serial in serials if device_groups.get(serial, "") in self.scopes]


class ApprovalGate:
    DEFAULT_THRESHOLD = 5
    RESTRICTED_ACTIONS = {
        Permission.DEVICE_REBOOT.value,
        Permission.SHELL_EXECUTE.value,
        Permission.AGENT_REVOKE.value,
        Permission.SETTINGS_WRITE.value,
    }

    @staticmethod
    def requires_approval(action: str, target_count: int, threshold: int | None = None) -> bool:
        if target_count <= 0:
            return False
        limit = threshold if threshold is not None else ApprovalGate.DEFAULT_THRESHOLD
        return target_count >= limit

    @staticmethod
    def approve(action: str, target_count: int, *, role: Role | str | None = None, mfa_verified: bool = True, threshold: int | None = None) -> bool:
        if ApprovalGate.requires_approval(action, target_count, threshold=threshold):
            if role is None:
                return False
            return AccessController.can(role, Permission.SETTINGS_WRITE) and mfa_verified
        return True


class AuthManager:
    def __init__(self):
        self._users: dict[str, dict[str, Any]] = {}

    @staticmethod
    def _hash_password(password: str, salt: bytes | None = None) -> tuple[str, bytes]:
        salt = salt or secrets.token_bytes(16)
        derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 200_000)
        return derived.hex(), salt

    def register_user(self, username: str, password: str, role: Role | str) -> dict[str, Any]:
        username = (username or "").strip()
        if not username or not password:
            raise ValueError("username and password are required")
        role_name = Role(role) if isinstance(role, str) else role
        password_hash, salt = self._hash_password(password)
        record = {
            "username": username,
            "password_hash": password_hash,
            "salt": salt,
            "role": role_name,
        }
        self._users[username] = record
        return record

    def verify_password(self, username: str, password: str) -> bool:
        record = self._users.get((username or "").strip())
        if record is None:
            return False
        expected_hash, _ = self._hash_password(password, record["salt"])
        return hmac.compare_digest(expected_hash, record["password_hash"])

    def get_role(self, username: str) -> Role | None:
        record = self._users.get((username or "").strip())
        return record["role"] if record else None


class MfaVerifier:
    @staticmethod
    def _normalize_secret(secret: str) -> bytes:
        key = secret.strip().upper().replace(" ", "")
        if len(key) % 8:
            key += "=" * ((8 - (len(key) % 8)) % 8)
        return base64.b32decode(key, casefold=True)

    @staticmethod
    def generate_code(secret: str, timestamp: int | None = None) -> str:
        epoch = int(timestamp if timestamp is not None else time.time())
        counter = int(epoch // 30)
        key = MfaVerifier._normalize_secret(secret)
        digest = hmac.new(key, counter.to_bytes(8, "big"), hashlib.sha1).digest()
        offset = digest[-1] & 0x0F
        binary = ((digest[offset] & 0x7F) << 24) | ((digest[offset + 1] & 0xFF) << 16) | ((digest[offset + 2] & 0xFF) << 8) | (digest[offset + 3] & 0xFF)
        code = binary % 1_000_000
        return f"{code:06d}"

    @staticmethod
    def verify(secret: str, code: str, *, window: int = 1, timestamp: int | None = None) -> bool:
        if not code or len(code) != 6 or not code.isdigit():
            return False
        epoch = int(timestamp if timestamp is not None else time.time())
        for shift in range(-window, window + 1):
            candidate = MfaVerifier.generate_code(secret, timestamp=epoch + shift * 30)
            if hmac.compare_digest(candidate, code):
                return True
        return False


class AuditLogger:
    def __init__(self, path: str | os.PathLike[str]):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def log(self, event: str, payload: dict[str, Any] | None = None, result: str = "success") -> dict[str, Any]:
        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "event": event,
            "result": result,
            "details": payload or {},
        }
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True))
            handle.write("\n")
        return record


class SignedArtifact:
    @staticmethod
    def _hash_bytes(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    @staticmethod
    def sign_file(path: str | os.PathLike[str], secret: str = "") -> str:
        blob = Path(path).read_bytes()
        digest = SignedArtifact._hash_bytes(blob)
        signature = hmac.new((secret or os.environ.get("DROIDFLEET_SIGNING_KEY", "droidfleet-dev-signing-key")).encode("utf-8"), digest.encode("utf-8"), hashlib.sha256).hexdigest()
        return f"{digest}:{signature}"

    @staticmethod
    def verify_file(path: str | os.PathLike[str], signature: str, secret: str = "") -> bool:
        try:
            digest, expected = signature.split(":", 1)
        except ValueError:
            return False
        actual_digest = SignedArtifact._hash_bytes(Path(path).read_bytes())
        if actual_digest != digest:
            return False
        generated = hmac.new((secret or os.environ.get("DROIDFLEET_SIGNING_KEY", "droidfleet-dev-signing-key")).encode("utf-8"), digest.encode("utf-8"), hashlib.sha256).hexdigest()
        return hmac.compare_digest(generated, expected)


class AgentIdentityRegistry:
    def __init__(self) -> None:
        self._agents: dict[str, str] = {}
        self._revoked: set[str] = set()

    def register(self, agent_id: str, token: str) -> bool:
        agent_id = (agent_id or "").strip()
        token = (token or "").strip()
        if not agent_id or not token:
            return False
        if agent_id in self._revoked or agent_id in self._agents:
            return False
        self._agents[agent_id] = token
        return True

    def revoke(self, agent_id: str) -> bool:
        agent_id = (agent_id or "").strip()
        if not agent_id:
            return False
        if agent_id in self._agents:
            self._revoked.add(agent_id)
            self._agents.pop(agent_id, None)
            return True
        self._revoked.add(agent_id)
        return True

    def is_revoked(self, agent_id: str) -> bool:
        return (agent_id or "").strip() in self._revoked

    def issue(self, agent_id: str) -> tuple[str, str]:
        value = (agent_id or "").strip()
        if not value:
            raise ValueError("agent_id is required")
        token = secrets.token_urlsafe(32)
        self.register(value, token)
        return value, token


class AgentSecureKeyStore:
    def __init__(self, base_dir: str | os.PathLike[str] | None = None):
        root = Path(base_dir or os.environ.get("DROIDFLEET_KEYSTORE_DIR", Path.home() / ".droidfleet" / "keys"))
        self.base_dir = root
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def save_private_key(self, agent_id: str, private_key: str | bytes) -> Path:
        serial = (agent_id or "").strip()
        if not serial:
            raise ValueError("agent_id is required")
        path = self.base_dir / f"{serial}.key"
        payload = private_key.encode("utf-8") if isinstance(private_key, str) else bytes(private_key)
        path.write_bytes(payload)
        os.chmod(path, 0o600)
        return path

    def load_private_key(self, agent_id: str) -> bytes:
        serial = (agent_id or "").strip()
        if not serial:
            raise ValueError("agent_id is required")
        path = self.base_dir / f"{serial}.key"
        if not path.exists():
            raise FileNotFoundError(path)
        return path.read_bytes()


class SignedCommand:
    _ALLOWED_KEYS = {"device_id", "action", "params", "command_id", "issued_at", "expires_at", "nonce", "signature"}
    _REPLAY_CACHE: dict[str, float] = {}

    @staticmethod
    def _canonicalize(payload: dict[str, Any]) -> str:
        return json.dumps(payload, separators=(",", ":"), sort_keys=True, ensure_ascii=False)

    @staticmethod
    def create(payload: dict[str, Any], secret: str, *, ttl_seconds: int = 300, issued_at: float | None = None, nonce: str | None = None) -> dict[str, Any]:
        command = dict(payload)
        command["command_id"] = command.get("command_id") or f"cmd-{secrets.token_hex(12)}"
        command["issued_at"] = _isoformat_utc(issued_at if issued_at is not None else time.time())
        command["nonce"] = nonce or secrets.token_hex(16)
        expires_at = time.time() + max(1, ttl_seconds)
        command["expires_at"] = _isoformat_utc(expires_at)
        signature_payload = {key: command[key] for key in sorted(command.keys()) if key != "signature"}
        command["signature"] = hmac.new(secret.encode("utf-8"), SignedCommand._canonicalize(signature_payload).encode("utf-8"), hashlib.sha256).hexdigest()
        return command

    @staticmethod
    def verify(payload: dict[str, Any], secret: str, *, replay_cache: dict[str, float] | None = None) -> bool:
        if not isinstance(payload, dict):
            return False
        if set(payload.keys()) - SignedCommand._ALLOWED_KEYS:
            return False
        for key in ("device_id", "action", "command_id", "issued_at", "expires_at", "nonce", "signature"):
            if key not in payload:
                return False
        try:
            expires_at = datetime.fromisoformat(payload["expires_at"].replace("Z", "+00:00")).timestamp()
            issued_at = datetime.fromisoformat(payload["issued_at"].replace("Z", "+00:00")).timestamp()
        except ValueError:
            return False
        if time.time() > expires_at:
            return False
        if issued_at > time.time() + 300:
            return False
        signature_payload = {key: payload[key] for key in sorted(payload.keys()) if key != "signature"}
        expected = hmac.new(secret.encode("utf-8"), SignedCommand._canonicalize(signature_payload).encode("utf-8"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, payload["signature"]):
            return False
        cache = replay_cache if replay_cache is not None else SignedCommand._REPLAY_CACHE
        nonce = payload["nonce"]
        now = time.time()
        cache = {key: value for key, value in cache.items() if value > now}
        if replay_cache is not None:
            replay_cache.clear(); replay_cache.update(cache)
        else:
            SignedCommand._REPLAY_CACHE.clear(); SignedCommand._REPLAY_CACHE.update(cache)
        if nonce in cache:
            return False
        cache[nonce] = expires_at
        if replay_cache is not None:
            replay_cache.clear(); replay_cache.update(cache)
        else:
            SignedCommand._REPLAY_CACHE.clear(); SignedCommand._REPLAY_CACHE.update(cache)
        return True


__all__ = [
    "AccessController",
    "AgentIdentityRegistry",
    "AgentSecureKeyStore",
    "ApprovalGate",
    "AuditLogger",
    "AuthManager",
    "DeviceAccessPolicy",
    "MfaVerifier",
    "Permission",
    "Role",
    "SecurityContext",
    "SignedArtifact",
    "SignedCommand",
    "ROLE_PERMISSIONS",
]
