from app.connection import ConnectionMode, ConnectionProfile
from app.security import hash_token, redact_logcat, safe_destination, validate_server_url


def test_connection_modes_have_stable_labels_and_values():
    assert ConnectionProfile.from_value("local").label == "SELF-HOST"
    assert ConnectionProfile.from_value("external").label == "EXTERNAL SERVER"
    assert ConnectionProfile.from_value("unknown").mode is ConnectionMode.SELF_HOST


def test_connection_profile_validates_agent_urls_by_mode():
    external = ConnectionProfile.from_value("external")
    assert external.validate_agent_url("https://farm.example.com/api/agent/heartbeat")
    assert not external.validate_agent_url("https://farm.example.com/heartbeat")
    assert not external.validate_agent_url("http://farm.example.com/api/agent/heartbeat")


def test_secure_server_urls_are_https_only_and_loopback_debug_is_opt_in():
    assert validate_server_url("https://droidfleet.internal/api/agent/heartbeat") == "https://droidfleet.internal/api/agent/heartbeat"
    assert validate_server_url("http://127.0.0.1:8765/api/agent/heartbeat", allow_insecure_loopback=True) == "http://127.0.0.1:8765/api/agent/heartbeat"
    try:
        validate_server_url("http://droidfleet.internal/api/agent/heartbeat")
    except ValueError:
        pass
    else:
        raise AssertionError("HTTP server url should be rejected in production mode")


def test_safe_destination_blocks_path_traversal_and_too_large_files():
    root = safe_destination("safe.txt", base_dir="./data/test_inbox")
    assert root.name == "safe.txt"
    try:
        safe_destination("../../secrets.txt", base_dir="./data/test_inbox")
    except ValueError:
        pass
    else:
        raise AssertionError("path traversal should be rejected")
    try:
        safe_destination("big.bin", base_dir="./data/test_inbox", max_bytes=1, data=b"12345")
    except ValueError:
        pass
    else:
        raise AssertionError("oversized payload should be rejected")


def test_tokens_are_hashed_and_logs_are_redacted():
    token_hash, salt = hash_token("agent-secret")
    assert token_hash != "agent-secret"
    assert "Bearer agent-secret" not in redact_logcat("Authorization: Bearer agent-secret")
    assert "[REDACTED]" in redact_logcat("Authorization: Bearer agent-secret")