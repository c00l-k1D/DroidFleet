from app.connection import ConnectionMode, ConnectionProfile


def test_connection_modes_have_stable_labels_and_values():
    assert ConnectionProfile.from_value("local").label == "SELF-HOST"
    assert ConnectionProfile.from_value("ngrok").label == "NGROK"
    assert ConnectionProfile.from_value("external").label == "EXTERNAL SERVER"
    assert ConnectionProfile.from_value("unknown").mode is ConnectionMode.SELF_HOST


def test_connection_profile_validates_agent_urls_by_mode():
    ngrok = ConnectionProfile.from_value("ngrok")
    external = ConnectionProfile.from_value("external")
    assert ngrok.validate_agent_url("https://farm.ngrok.app/api/agent/heartbeat")
    assert not ngrok.validate_agent_url("http://farm.ngrok.app/api/agent/heartbeat")
    assert external.validate_agent_url("https://farm.example.com/api/agent/heartbeat")
    assert not external.validate_agent_url("https://farm.example.com/heartbeat")