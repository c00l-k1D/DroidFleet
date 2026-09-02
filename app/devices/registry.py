from __future__ import annotations

import json
import os
import tempfile
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class DeviceRecord:
    serial: str
    device_id: str
    name: str = ""
    device_type: str = "Android"
    os: str = "--"
    model: str = "--"
    ip: str = "--"
    status: str = "OFFLINE"
    battery: str = "--"
    cpu: str = "--"
    ram: str = "--"
    temperature: str = "--"
    last_seen: str = "--"
    group: str = "Без группы"
    tags: list[str] = field(default_factory=list)

    @property
    def display_name(self) -> str:
        return self.name or self.model or self.serial


class DeviceRegistry:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.records: dict[str, DeviceRecord] = {}
        self.custom_groups: set[str] = set()
        self.load()

    def load(self):
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            self.custom_groups = set(payload.get("groups", []))
            fields = set(DeviceRecord.__dataclass_fields__)
            for item in payload.get("devices", []):
                record = DeviceRecord(**{key: value for key, value in item.items() if key in fields})
                self.records[record.serial] = record
        except FileNotFoundError:
            return
        except (OSError, TypeError, ValueError) as exc:
            raise RuntimeError(f"Не удалось прочитать конфигурацию устройств: {exc}") from exc

    def get_or_create(self, serial: str) -> DeviceRecord:
        record = self.records.get(serial)
        if record is None:
            record = DeviceRecord(
                serial=serial,
                device_id=f"dev-{uuid.uuid5(uuid.NAMESPACE_URL, serial).hex[:12]}",
            )
            self.records[serial] = record
        return record

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"version": 1, "groups": sorted(self.custom_groups), "devices": [asdict(item) for item in self.records.values()]}
        fd, temporary_path = tempfile.mkstemp(prefix="devices-", suffix=".json", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(payload, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
            os.replace(temporary_path, self.path)
        except OSError as exc:
            try:
                os.unlink(temporary_path)
            except OSError:
                pass
            raise RuntimeError(f"Не удалось сохранить конфигурацию устройств: {exc}") from exc

    def update(self, serial: str, **values):
        record = self.get_or_create(serial)
        for key, value in values.items():
            if hasattr(record, key):
                setattr(record, key, value)
        self.save()
        return record

    def groups(self) -> set[str]:
        return self.custom_groups | {record.group for record in self.records.values() if record.group}
