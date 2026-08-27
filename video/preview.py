from concurrent.futures import ThreadPoolExecutor
import threading
from PIL import ImageTk
from .decoder import decode_preview
from app.adb.commands import screencap


class PreviewService:
    def __init__(self, root, client, on_image, on_failure, width, height, workers):
        self.root = root
        self.client = client
        self.on_image = on_image
        self.on_failure = on_failure
        self.width = width
        self.height = height
        self.executor = ThreadPoolExecutor(max_workers=workers)
        self.busy = set()
        self.lock = threading.Lock()
        self.running = True

    def submit(self, serial):
        with self.lock:
            if serial in self.busy:
                return False
            self.busy.add(serial)
        self.executor.submit(self._capture, serial)
        return True

    def _capture(self, serial):
        try:
            result = self.client.run(screencap(), serial, timeout=2)
            if result.returncode != 0 or not result.stdout:
                raise RuntimeError("screencap failed")
            photo = ImageTk.PhotoImage(decode_preview(result.stdout, self.width, self.height))
            self.root.after(0, lambda: self.on_image(serial, photo))
        except Exception:
            self.root.after(0, lambda: self.on_failure(serial))
        finally:
            with self.lock:
                self.busy.discard(serial)

    def close(self):
        self.running = False
        self.executor.shutdown(wait=False, cancel_futures=True)
