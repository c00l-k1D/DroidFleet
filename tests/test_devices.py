from app.adb.device import parse_ip, parse_ram
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
