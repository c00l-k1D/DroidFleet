from collections import deque
from datetime import datetime
import threading


class FleetLogger:
    def __init__(self, limit=2000):
        self._records = deque(maxlen=limit)
        self._lock = threading.Lock()

    def log(self, level, message):
        record = f"{datetime.now():%Y-%m-%d %H:%M:%S} [{level.upper()}] {message}"
        with self._lock:
            self._records.append(record)

    def info(self, message):
        self.log("INFO", message)

    def warning(self, message):
        self.log("WARN", message)

    def error(self, message):
        self.log("ERROR", message)

    def text(self):
        with self._lock:
            return "\n".join(self._records)
