import json
from datetime import datetime, timezone
from pathlib import Path

from app.security import decrypt_secret, encrypt_secret


class AccountRepository:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def add_import(self, source: Path, targets: list[str]) -> int:
        entries = self._read()
        imported_at = datetime.now(timezone.utc).isoformat()
        for target in targets:
            entries.append({
                "source_file": source.name,
                "device_serial": target,
                "imported_at": imported_at,
                "destination": "/sdcard/Download/DroidFleet/accounts/",
            })
        self._write(entries)
        return len(targets)

    def _read(self) -> list[dict]:
        if not self.path.exists():
            return []
        try:
            raw = self.path.read_text(encoding="utf-8")
            data = json.loads(decrypt_secret(raw))
        except (OSError, ValueError, json.JSONDecodeError):
            return []
        return data if isinstance(data, list) else []

    def _write(self, entries: list[dict]):
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        payload = encrypt_secret(json.dumps(entries, ensure_ascii=False, indent=2))
        temporary.write_text(payload, encoding="utf-8")
        temporary.replace(self.path)
