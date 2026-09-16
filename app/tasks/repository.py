from __future__ import annotations

import json
from pathlib import Path


class TaskRepository:
    def __init__(self, path: Path):
        self.path = Path(path)

    def load(self) -> list[dict]:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return []
        except (OSError, TypeError, ValueError) as exc:
            raise RuntimeError(f"Не удалось прочитать задания: {exc}") from exc
        if not isinstance(payload, list):
            raise RuntimeError("Файл заданий должен содержать JSON-массив")
        return [item for item in payload if isinstance(item, dict)]

    def save(self, tasks: list[dict]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        try:
            temporary.write_text(json.dumps(tasks, ensure_ascii=False, indent=2), encoding="utf-8")
            temporary.replace(self.path)
        except OSError as exc:
            raise RuntimeError(f"Не удалось сохранить задания: {exc}") from exc
