from app.adb.client import AdbClient
from app.adb.device import adb_transport, parse_ip, parse_ram, parse_storage
from app.devices.registry import DeviceRegistry


def test_device_registry_persists_identity_and_metadata(tmp_path):
    path = tmp_path / "devices.json"
    registry = DeviceRegistry(path)
    record = registry.get_or_create("ABC123")
    record.name = "Рабочий планшет"
    record.group = "Тест"
    record.tags = ["android", "usb"]
    registry.save()

    restored = DeviceRegistry(path).get_or_create("ABC123")
    assert restored.device_id == record.device_id
    assert restored.name == "Рабочий планшет"
    assert restored.group == "Тест"
    assert restored.tags == ["android", "usb"]


def test_hardware_value_parsers():
    assert parse_ram("MemTotal:        4096000 kB\n") == "4000 MB"
    assert parse_ip("default via 192.168.1.1 dev wlan0 src 192.168.1.42 metric 100\n") == "192.168.1.42"
    assert parse_storage(
        "Filesystem      Size  Used Avail Use% Mounted on\n"
        "/dev/block      64G   20G   44G  32% /data\n"
    ) == "20G used / 64G total"


def test_android_transport_is_independent_from_agent_connection():
    assert adb_transport("ABC123") == "ADB USB"
    assert adb_transport("192.168.1.42:5555") == "ADB WI-FI"
    assert adb_transport("emulator-5554") == "ADB LOCAL"


def test_reconnect_does_not_pass_serial_to_adb(monkeypatch):
    client = AdbClient(executable="adb.exe")
    captured = {}

    def fake_run(args, serial=None, timeout=5):
        captured.update(args=args, serial=serial, timeout=timeout)
        return type("Result", (), {"returncode": 0})()

    monkeypatch.setattr(client, "run", fake_run)
    client.reconnect("ABC123")
    assert captured == {"args": ["reconnect"], "serial": None, "timeout": 5}


def test_registry_delete_persists(tmp_path):
    registry = DeviceRegistry(tmp_path / "devices.json")
    registry.get_or_create("ABC123")
    assert registry.delete("ABC123")
    assert DeviceRegistry(tmp_path / "devices.json").records == {}


def test_adb_uses_isolated_server_port(monkeypatch):
    client = AdbClient(executable="adb")
    calls = []
    environments = []

    def fake_run(args, serial=None, timeout=5):
        calls.append((args, timeout))
        environments.append(__import__("os").environ.get("ADB_SERVER_PORT"))
        return type("Result", (), {
            "returncode": 0,
            "stdout": b"List of devices attached\nABC123\tdevice\n",
        })()

    monkeypatch.setattr(client, "run", fake_run)
    assert client.devices() == ["ABC123"]
    assert calls == [(["devices"], 5)]
