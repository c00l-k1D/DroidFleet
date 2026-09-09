from concurrent.futures import ThreadPoolExecutor


class BatchExecutor:
    def __init__(self, workers: int):
        self.executor = ThreadPoolExecutor(max_workers=workers)

    def run(self, targets, action):
        for serial in targets:
            self.executor.submit(self._safe_run, action, serial)

    @staticmethod
    def _safe_run(action, serial):
        try:
            action(serial)
        except Exception:
            pass

    def close(self):
        self.executor.shutdown(wait=False, cancel_futures=True)
