import sys
import types

from app.ngrok import NgrokTunnel


def test_ngrok_tunnel_starts_and_stops_without_network(monkeypatch):
    calls = []
    tunnel = types.SimpleNamespace(public_url="https://example.ngrok.app")
    fake_ngrok = types.SimpleNamespace(
        set_auth_token=lambda token: calls.append(("token", token)),
        connect=lambda port, **options: calls.append(("connect", port, options)) or tunnel,
        disconnect=lambda url: calls.append(("disconnect", url)),
    )
    monkeypatch.setitem(sys.modules, "pyngrok", types.SimpleNamespace(ngrok=fake_ngrok))

    manager = NgrokTunnel(8765, authtoken="secret", region="eu")
    assert manager.start() == "https://example.ngrok.app"
    manager.stop()

    assert calls == [
        ("token", "secret"),
        ("connect", 8765, {"proto": "http", "region": "eu"}),
        ("disconnect", "https://example.ngrok.app"),
    ]


def test_ngrok_rejects_api_credential_as_agent_token():
    manager = NgrokTunnel(8765, authtoken="Bearer cr_example")
    try:
        manager.start()
    except RuntimeError as exc:
        assert "Agent Authtoken" in str(exc)
    else:
        raise AssertionError("API credential must not be used as an agent token")