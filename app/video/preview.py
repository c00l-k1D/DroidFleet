from concurrent.futures import ThreadPoolExecutor
import io
import queue
import threading
from PIL import Image
from .decoder import decode_preview
from app.adb.commands import screencap


class PreviewService:
    def __init__(self, root, client, on_image, on_failure, width, height, workers):
        self.root = root
        self.client = client
        self.on_image = on_image
        self.on_failure = on_failure
        self.default_width = width
        self.default_height = height
        self.executor = ThreadPoolExecutor(max_workers=workers)
        self.busy = set()
        self.lock = threading.Lock()
        self.running = True
        self.device_resolutions = {}  # Cache device resolutions
        self.results = queue.Queue()

    def set_device_resolution(self, serial, width, height):
        """Set the screen resolution for a specific device."""
        self.device_resolutions[serial] = (width, height)

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
            source_image = Image.open(io.BytesIO(result.stdout))
            # Use device-specific resolution if available, otherwise use default
            width, height = self.device_resolutions.get(serial, (self.default_width, self.default_height))
            image = decode_preview(result.stdout, width, height)
            image.source_size = source_image.size
            self.results.put(("image", serial, image))
        except Exception:
            self.results.put(("failure", serial, None))
        finally:
            with self.lock:
                self.busy.discard(serial)

    def drain_results(self):
        while True:
            try:
                result_type, serial, image = self.results.get_nowait()
            except queue.Empty:
                return
            if result_type == "image":
                self.on_image(serial, image)
            else:
                self.on_failure(serial)

    def close(self):
        self.running = False
        self.executor.shutdown(wait=False, cancel_futures=True)
