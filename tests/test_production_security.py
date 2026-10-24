import json
from pathlib import Path

import pytest

from app.production_security import (
    AccessController,
    AgentIdentityRegistry,
    AuditLogger,
    ApprovalGate,
    AuthManager,
    DeviceAccessPolicy,
    MfaVerifier,
    Permission,
    Role,
    SecurityContext,
    SignedArtifact,
    SignedCommand,
)


def test_rbac_allows_roles_only_for_permitted_actions():
    controller = AccessController()
    assert controller.can(Role.OPERATOR, Permission.DEVICE_REBOOT)
    assert controller.can(Role.SHELL_OPERATOR, Permission.SHELL_EXECUTE)
    assert not controller.can(Role.VIEWER, Permission.DEVICE_REBOOT)
    assert not controller.can(Role.OPERATOR, Permission.AGENT_REVOKE)


def test_mfa_verifier_accepts_valid_totp_and_rejects_invalid():
    secret = "JBSWY3DPEHPK3PXP"
    valid_code = MfaVerifier.generate_code(secret)
    assert MfaVerifier.verify(secret, valid_code)
    assert not MfaVerifier.verify(secret, "000000")


def test_audit_logger_appends_jsonl_events():
    path = Path("./data/test_audit.log")
    if path.exists():
        path.unlink()
    logger = AuditLogger(path)
    logger.log("user.login", {"user": "admin"}, "success")
    raw = path.read_text(encoding="utf-8").strip()
    payload = json.loads(raw)
    assert payload["event"] == "user.login"
    assert payload["result"] == "success"


def test_signed_artifact_verifies_sha256_and_signature():
    unsigned = Path("./data/test_unsigned.bin")
    signed = Path("./data/test_signed.bin")
    signed.write_bytes(b"payload")
    unsigned.write_bytes(b"tampered-payload")
    signature = SignedArtifact.sign_file(signed, secret="prod-secret")
    assert SignedArtifact.verify_file(signed, signature, secret="prod-secret")
    assert not SignedArtifact.verify_file(unsigned, signature, secret="prod-secret")


def test_approval_gate_requires_extra_confirmation_for_large_batches():
    assert ApprovalGate.requires_approval("device.reboot", 3, threshold=5) is False
    assert ApprovalGate.requires_approval("device.reboot", 8, threshold=5) is True
    assert SecurityContext(role=Role.OPERATOR).can_perform(Permission.DEVICE_REBOOT, 3)
    assert not SecurityContext(role=Role.VIEWER).can_perform(Permission.DEVICE_REBOOT, 1)


def test_auth_manager_validates_passwords_and_roles():
    manager = AuthManager()
    manager.register_user("ops", "passw0rd", Role.OPERATOR)
    assert manager.verify_password("ops", "passw0rd")
    assert not manager.verify_password("ops", "wrong-pass")
    assert manager.get_role("ops") is Role.OPERATOR


def test_scope_policy_blocks_cross_group_access():
    policy = DeviceAccessPolicy({Role.OPERATOR: {"Samsung", "Pixel"}})
    assert policy.can_access(Role.OPERATOR, "Samsung")
    assert not policy.can_access(Role.OPERATOR, "iPhone")
    assert not policy.can_access(Role.VIEWER, "Samsung")


def test_signed_command_rejects_expired_or_replayed_payloads():
    secret = "super-secret-key"
    signed = SignedCommand.create({"device_id": "abc", "action": "reboot", "params": {}}, secret, ttl_seconds=120)
    assert SignedCommand.verify(signed, secret)
    assert not SignedCommand.verify({**signed, "signature": "bad"}, secret)
    expired = SignedCommand.create({"device_id": "abc", "action": "reboot", "params": {}}, secret, ttl_seconds=1, issued_at=1000)
    assert not SignedCommand.verify({**expired, "expires_at": "1970-01-01T00:00:01Z"}, secret)


def test_agent_revocation_blocks_unknown_or_revoked_agents():
    registry = AgentIdentityRegistry()
    registry.register("agent-alpha", "token-alpha")
    registry.revoke("agent-alpha")
    assert registry.is_revoked("agent-alpha")
    assert not registry.register("agent-alpha", "token-alpha")
