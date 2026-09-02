class DeviceMonitor:
    def __init__(self, client, on_change):
        self.client = client
        self.on_change = on_change

    def refresh(self):
        devices = self.client.devices() if self.client.executable else []
        self.on_change(devices)
        return devices
