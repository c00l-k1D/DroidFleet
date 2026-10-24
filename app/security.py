from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
from pathlib import Path
from urllib.parse import urlparse

LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}
SECRET_PATTERNS = [
    re.compile(r"(?i)(authorization\s*[:=]\s*bearer\s+)\S+"),
    re.compile(r"(?i)(token\s*[:=]\s*)\S+"),
    re.compile(r"(?i)(password\s*[:=]\s*)\S+"),
    re.compile(r"(?i)(api[_-]?key\s*[:=]\s*)\S+"),
    re.compile(r"(?i)(secret\s*[:=]\s*)\S+"),
]


def allow_insecure_loopback_enabled() -> bool:
    return os.environ.get("DROIDFLEET_ALLOW_INSECURE_LOOPBACK", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def validate_server_url(url: str, allow_insecure_loopback: bool | None = None) -> str:
    value = (url or "").strip()
    if not value:
        raise ValueError("Server URL is required")
    parsed = urlparse(value)
    if parsed.scheme == "https" and parsed.netloc:
        return value.rstrip("/")
    if parsed.scheme == "http" and parsed.netloc:
        hostname = (parsed.hostname or "").lower()
        loopback_allowed = allow_insecure_loopback if allow_insecure_loopback is not None else allow_insecure_loopback_enabled()
        if hostname in LOOPBACK_HOSTS and loopback_allowed:
            return value.rstrip("/")
    raise ValueError("Only HTTPS is allowed. HTTP is permitted only for loopback debug mode.")


def hash_token(token: str, salt: bytes | None = None) -> tuple[str, bytes]:
    if not token:
        raise ValueError("Token cannot be empty")
    if salt is None:
        salt = os.urandom(16)
    digest = hmac.new(salt, token.encode("utf-8"), hashlib.sha256).hexdigest()
    return digest, salt


def redact_logcat(line: str) -> str:
    if not isinstance(line, str):
        return ""
    redacted = line
    for pattern in SECRET_PATTERNS:
        redacted = pattern.sub(r"\1[REDACTED]", redacted)
    return redacted


def safe_destination(filename: str, base_dir: str | os.PathLike[str] | None = None, max_bytes: int = 50 * 1024 * 1024, data: bytes | None = None) -> Path:
    if not filename or filename in {".", ".."}:
        raise ValueError("Invalid filename")
    candidate_path = Path(filename)
    if candidate_path.is_absolute() or ".." in candidate_path.parts or "/" in filename or "\\" in filename:
        raise ValueError("Path traversal detected")
    root = Path(base_dir or os.environ.get("DROIDFLEET_FILE_ROOT", "./data/inbox")).resolve()
    destination = (root / candidate_path.name).resolve()
    try:
        destination.relative_to(root)
    except ValueError as exc:
        raise ValueError("Path traversal detected") from exc
    if data is not None and len(data) > max_bytes:
        raise ValueError("File too large")
    if destination.exists():
        raise FileExistsError("Destination already exists")
    return destination


def derive_key(secret_key: str) -> bytes:
    return hashlib.sha256((secret_key or "droidfleet-dev-secret").encode("utf-8")).digest()


def encrypt_secret(value: str, secret_key: str | None = None) -> str:
    if not value:
        return ""
    key = derive_key(secret_key or os.environ.get("DROIDFLEET_SECRET_KEY", "droidfleet-dev-secret"))
    raw = value.encode("utf-8")
    nonce = os.urandom(16)
    encrypted = bytearray()
    for index, byte in enumerate(raw):
        encrypted.append(byte ^ key[index % len(key)] ^ nonce[index % len(nonce)])
    return "droidfleet:v1:" + base64.b64encode(nonce + bytes(encrypted)).decode("ascii")


def decrypt_secret(value: str, secret_key: str | None = None) -> str:
    if not value:
        return ""
    if not value.startswith("droidfleet:v1:"):
        return value
    key = derive_key(secret_key or os.environ.get("DROIDFLEET_SECRET_KEY", "droidfleet-dev-secret"))
    payload = base64.b64decode(value.removeprefix("droidfleet:v1:"), validate=True)
    nonce = payload[:16]
    encrypted = payload[16:]
    decrypted = bytearray()
    for index, byte in enumerate(encrypted):
        decrypted.append(byte ^ key[index % len(key)] ^ nonce[index % len(nonce)])
    return decrypted.decode("utf-8")
