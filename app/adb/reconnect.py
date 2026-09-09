import time


class ReconnectService:
    def __init__(self, client, logger, attempts=3, delay=2):
        self.client = client
        self.logger = logger
        self.attempts = attempts
        self.delay = delay

    def reconnect(self, serial):
        for attempt in range(1, self.attempts + 1):
            try:
                self.logger.info(f"Переподключение {serial}: попытка {attempt}/{self.attempts}")
                result = self.client.reconnect(serial)
                if result.returncode == 0:
                    self.logger.info(f"Команда переподключения отправлена: {serial}")
                    return True
                details = result.stderr.decode(errors="replace").strip()
                self.logger.warning(f"Не удалось переподключить {serial}: {details or 'код ' + str(result.returncode)}")
            except Exception as exc:
                self.logger.warning(f"Ошибка переподключения {serial}: {exc}")
            if attempt < self.attempts:
                time.sleep(self.delay)
        self.logger.error(f"Устройство не переподключено после {self.attempts} попыток: {serial}")
        return False
