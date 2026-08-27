from dataclasses import dataclass


@dataclass(frozen=True)
class Device:
    serial: str
    state: str = "device"

    @property
    def online(self) -> bool:
        return self.state == "device"


@dataclass(frozen=True)
class HardwareInfo:
    manufacturer: str = "--"
    model: str = "--"
    screen: str = "--"
    battery: str = "--"
    temperature: str = "--"
    android_version: str = "--"


def parse_getprop(output: str) -> dict[str, str]:
    properties = {}
    for line in output.splitlines():
        if line.startswith("[") and "]: [" in line and line.endswith("]"):
            name, value = line[1:].split("]: [", 1)
            properties[name] = value[:-1]
    return properties


def parse_battery(output: str) -> tuple[str, str]:
    level = "--"
    temperature = "--"
    for line in output.splitlines():
        key, separator, value = line.partition(":")
        if not separator:
            continue
        value = value.strip()
        if key.strip().lower() == "level":
            level = f"{value}%"
        elif key.strip().lower() == "temperature":
            try:
                temperature = f"{int(value) / 10:.1f} C"
            except ValueError:
                temperature = value
    return level, temperature


def parse_screen(output: str) -> str:
    for line in output.splitlines():
        if "Physical size:" in line or "Override size:" in line:
            return line.split(":", 1)[1].strip()
    return "--"
