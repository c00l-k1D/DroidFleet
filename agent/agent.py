from __future__ import annotations

import argparse
import base64
import hashlib
import json
import logging
import logging.handlers
import os
import random
import subprocess
import sys
import threading
import time
import uuid
import ssl
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from urllib.parse import urlparse

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent import config
from agent.network import primary_address
from agent import process as process_module
from agent.process import _process_command, list_processes, process_status, restart_process, start_process, stop_process
from agent.screen import control_input, screen_info, screenshot_jpeg
from agent.system import snapshot
from agent.android import connected_devices

LOGGER = logging.getLogger("FarmAgent")


def configure_autostart(server_url: str) -> None:
    if not getattr(sys, "frozen", False) or os.name != "nt" or not server_url:
        return
    hostname = urlparse(server_url).hostname or ""
    if not hostname.endswith((".ngrok-free.dev", ".ngrok-free.app", ".ngrok.app", ".ngrok.io")):
        return
    import winreg

    command = f'"{Path(sys.executable).resolve()}" --server "{server_url}"'
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run") as key:
        winreg.SetValueEx(key, "DroidFleetFarmAgent", 0, winreg.REG_SZ, command)


def show_update_progress(downloaded: int, total: int) -> None:
    if total <= 0:
        return
    percent = min(100, downloaded * 100 // total)
    width = 30
    filled = percent * width // 100
    line = f"\r[UPDATE] Загрузка: [{'#' * filled}{'-' * (width - filled)}] {percent:3d}%"
    sys.stdout.write(line)
    sys.stdout.flush()


def collect_payload() -> dict:
    payload = snapshot()
    payload["ip"] = primary_address()
    payload["screen"] = screen_info()
    payload["update_completed"] = config.UPDATE_COMPLETED
    payload["agent_uptime"] = max(0, int(time.time() - config.STARTED_AT))
    if config.LAST_PING_MS is not None:
        payload["ping_ms"] = config.LAST_PING_MS
    payload["capabilities"] = sorted(COMMAND_HANDLERS)
    payload["android_devices"] = connected_devices()
    return payload


def send_heartbeat(payload: dict) -> float:
    started = time.perf_counter()
    request_json(config.SERVER_URL, payload)
    return round((time.perf_counter() - started) * 1000, 1)


def request_json(url: str, payload: dict | None = None) -> dict:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    last_error = None
    is_https = urlparse(url).scheme == "https"
    for attempt in range(config.NETWORK_RETRIES + 1):
        try:
            # Build a fresh TLS context for every retry. Ngrok may close the
            # previous edge connection while the agent is still polling.
            ssl_context = ssl.create_default_context() if is_https else None
            request = Request(
                url,
                data=body,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "Connection": "keep-alive",
                    "Cache-Control": "no-cache",
                    "User-Agent": f"FarmAgent/{config.AGENT_VERSION}",
                },
                method="POST" if body else "GET",
            )
            with urlopen(request, timeout=config.REQUEST_TIMEOUT, context=ssl_context) as response:
                if response.status < 200 or response.status >= 300:
                    raise RuntimeError(f"server returned HTTP {response.status}")
                data = response.read()
                return json.loads(data.decode("utf-8")) if data else {}
        except HTTPError as exc:
            # Ngrok may briefly return 502/503/504 while its edge reconnects.
            # Treat those responses like a broken TLS socket; permanent 4xx
            # responses still fail immediately and remain visible to callers.
            if exc.code not in {429, 502, 503, 504}:
                raise
            last_error = exc
            if attempt < config.NETWORK_RETRIES:
                retry_after = exc.headers.get("Retry-After", "") if exc.headers else ""
                try:
                    delay = max(0.0, min(float(retry_after), config.NETWORK_MAX_BACKOFF))
                except (TypeError, ValueError):
                    delay = 0.0
                if not delay:
                    delay = min(
                        config.NETWORK_MAX_BACKOFF,
                        config.NETWORK_BACKOFF * (2 ** attempt),
                    )
                delay += random.uniform(0.0, min(2.0, delay * 0.25))
                LOGGER.debug(
                    "HTTP retry %d/%d in %.1fs: %s",
                    attempt + 1,
                    config.NETWORK_RETRIES,
                    delay,
                    exc,
                )
                time.sleep(delay)
        except (OSError, URLError, RuntimeError) as exc:
            last_error = exc
            if attempt < config.NETWORK_RETRIES:
                delay = min(
                    config.NETWORK_MAX_BACKOFF,
                    config.NETWORK_BACKOFF * (2 ** attempt),
                )
                delay += random.uniform(0.0, min(2.0, delay * 0.25))
                LOGGER.debug("network retry %d/%d in %.1fs: %s", attempt + 1, config.NETWORK_RETRIES, delay, exc)
                time.sleep(delay)
    raise RuntimeError(f"request failed: {url}: {last_error}") from last_error


def install_update() -> dict:
    if not getattr(sys, "frozen", False):
        raise RuntimeError("Удалённое обновление доступно только для собранного FarmAgent.exe")
    update_url = config.SERVER_URL.rsplit("/heartbeat", 1)[0] + "/update"
    last_error = None
    for attempt in range(3):
        try:
            LOGGER.info("[UPDATE] Начата загрузка новой версии")
            request = Request(update_url, headers={"Accept": "application/octet-stream"})
            with urlopen(request, timeout=max(config.REQUEST_TIMEOUT, 30)) as response:
                total = int(response.headers.get("Content-Length", "0") or 0)
                downloaded = 0
                chunks = []
                while True:
                    chunk = response.read(256 * 1024)
                    if not chunk:
                        break
                    chunks.append(chunk)
                    downloaded += len(chunk)
                    if total:
                        show_update_progress(downloaded, total)
                binary = b"".join(chunks)
                expected = response.headers.get("X-DroidFleet-SHA256", "").strip().casefold()
            break
        except (OSError, URLError, RuntimeError) as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(1 + attempt)
    else:
        raise RuntimeError(f"сервер отклонил подключение к {update_url}: {last_error}") from last_error
    actual = hashlib.sha256(binary).hexdigest()
    if not binary or not expected or actual != expected:
        raise RuntimeError("проверка SHA-256 обновления не пройдена")
    if total:
        show_update_progress(len(binary), total)
        sys.stdout.write("\n")
        sys.stdout.flush()
    LOGGER.info("[UPDATE] Файл загружен и проверен, начинается установка")

    current = Path(sys.executable).resolve()
    staged = current.with_name(f"{current.stem}.update-{uuid.uuid4().hex}.exe")
    launcher_url = config.SERVER_URL.rsplit("/heartbeat", 1)[0] + "/update-launcher"
    launcher_staged = current.with_name(f"FarmAgent-start-{uuid.uuid4().hex}.cmd")
    try:
        launcher_request = Request(launcher_url, headers={"Accept": "text/plain"})
        with urlopen(launcher_request, timeout=max(config.REQUEST_TIMEOUT, 30)) as response:
            launcher_binary = response.read()
        if launcher_binary:
            with launcher_staged.open("wb") as stream:
                stream.write(launcher_binary)
                stream.flush()
                os.fsync(stream.fileno())
    except HTTPError as exc:
        if exc.code != 404:
            raise RuntimeError(f"не удалось скачать FarmAgent-start.cmd: HTTP {exc.code}") from exc
        LOGGER.info("[UPDATE] Launcher не опубликован, будет создан локально")
    except (OSError, URLError, RuntimeError) as exc:
        launcher_staged.unlink(missing_ok=True)
        raise RuntimeError(f"не удалось скачать FarmAgent-start.cmd: {exc}") from exc
    with staged.open("wb") as stream:
        stream.write(binary)
        stream.flush()
        os.fsync(stream.fileno())
    if staged.stat().st_size != len(binary):
        staged.unlink(missing_ok=True)
        raise RuntimeError("обновление записано не полностью")
    script = staged.with_suffix(".cmd")
    script.write_text(
        "@echo off\n"
        "setlocal\n"
        f'set "STAGED={staged}"\n'
        f'set "CURRENT={current}"\n'
        f'set "CURRENT_DIR={current.parent}"\n'
        f'set "LAUNCHER_STAGED={launcher_staged}"\n'
        f'set "LAUNCHER={current.parent / "FarmAgent-start.cmd"}"\n'
        f'set "BACKUP={current}.old-{uuid.uuid4().hex}"\n'
        f'set "SERVER={config.SERVER_URL}"\n'
        f'set "PID={os.getpid()}"\n'
        ":wait_process\n"
        'tasklist /FI "PID eq %PID%" | find "%PID%" >nul\n'
        "if not errorlevel 1 (timeout /t 1 /nobreak >nul & goto wait_process)\n"
        "set /a ATTEMPTS=0\n"
        ":replace\n"
        'if not exist "%STAGED%" goto failed\n'
        'if exist "%CURRENT%" move /Y "%CURRENT%" "%BACKUP%" >nul 2>&1\n'
        'if exist "%CURRENT%" goto retry\n'
        'move /Y "%STAGED%" "%CURRENT%" >nul 2>&1\n'
        "if not errorlevel 1 goto install_launcher\n"
        'if exist "%BACKUP%" move /Y "%BACKUP%" "%CURRENT%" >nul 2>&1\n'
        ":retry\n"
        "set /a ATTEMPTS+=1\n"
        "if %ATTEMPTS% GEQ 30 goto failed\n"
        "timeout /t 1 /nobreak >nul\n"
        "goto replace\n"
        ":install_launcher\n"
        'if not exist "%LAUNCHER_STAGED%" goto write_launcher\n'
        'move /Y "%LAUNCHER_STAGED%" "%LAUNCHER%" >nul 2>&1\n'
        "if not errorlevel 1 goto cleanup\n"
        "goto failed\n"
        ":write_launcher\n"
        '> "%LAUNCHER%" echo @echo off\n'
        '>> "%LAUNCHER%" echo cd /d "%~dp0"\n'
        '>> "%LAUNCHER%" echo start "FarmAgent" "%~dp0FarmAgent.exe" --server "%SERVER%"\n'
        "goto cleanup\n"
        ":cleanup\n"
        'if exist "%BACKUP%" del /q "%BACKUP%" >nul 2>&1\n'
        ":launch\n"
        'start "FarmAgent" /D "%CURRENT_DIR%" cmd /k ""%CURRENT%" --server "%SERVER%" --updated"\n'
        'del /q "%~f0"\n'
        "exit /b 0\n"
        ":failed\n"
        'if not exist "%CURRENT%" if exist "%BACKUP%" move /Y "%BACKUP%" "%CURRENT%" >nul 2>&1\n'
        'start "FarmAgent" /D "%CURRENT_DIR%" cmd /k ""%CURRENT%" --server "%SERVER%""\n'
        'del /q "%~f0"\n'
        "exit /b 1\n",
        encoding="utf-8",
    )
    subprocess.Popen(
        ["cmd.exe", "/c", str(script)],
        cwd=str(current.parent),
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    LOGGER.info("[UPDATE] Установка запущена, агент перезапустится автоматически")
    return {"updated": True, "version": config.AGENT_VERSION}


def poll_command(device_id: str) -> dict | None:
    poll_url = config.SERVER_URL.rsplit("/heartbeat", 1)[0] + "/poll?device_id=" + device_id
    response = request_json(poll_url)
    return response.get("command")


def send_result(result: dict, device_id: str) -> None:
    result["device_id"] = device_id
    request_json(config.SERVER_URL.rsplit("/heartbeat", 1)[0] + "/result", result)


def stream_frames(device_id: str, stop_event: threading.Event) -> None:
    frame_interval = 1 / config.STREAM_FPS
    next_frame = time.monotonic()
    while not stop_event.is_set():
        try:
            stream_result = execute_command_safely({"command": "SCREENSHOT", "command_id": f"stream-{time.time_ns()}"})
            send_result(stream_result, device_id)
        except (OSError, RuntimeError, URLError, ValueError) as exc:
            LOGGER.warning("stream frame failed: %s", exc)
        next_frame += frame_interval
        stop_event.wait(max(0, next_frame - time.monotonic()))


def pull_configuration() -> None:
    config_url = config.SERVER_URL.rsplit("/heartbeat", 1)[0] + "/config"
    response = request_json(config_url)
    process_module.configure_processes(response.get("process_definitions", {}))
    server_url = str(response.get("server_url", "")).strip().rstrip("/")
    if server_url:
        config.SERVER_URL = server_url + "/heartbeat"


def _command_result(command: dict, **values) -> dict:
    return {"command_id": command.get("command_id"), "command": str(command.get("command", "")).upper(), **values}


def _status_command(command: dict) -> dict:
    processes = []
    for name, definition in process_module.PROCESS_DEFINITIONS.items():
        item = process_status(name)
        item["configured"] = bool(_process_command(definition["command"]))
        item["configuration_variable"] = definition["command"]
        processes.append(item)
    return _command_result(command, processes=processes)


def _logs_command(command: dict) -> dict:
        try:
            lines = config.LOG_FILE.read_text(encoding="utf-8", errors="replace").splitlines()[-200:]
        except OSError:
            lines = []
        return _command_result(command, logs=lines)


def _screenshot_command(command: dict) -> dict:
    return _command_result(command, screenshot=screenshot_jpeg(config.SCREENSHOT_QUALITY))


def _stream_command(command: dict) -> dict:
    return _command_result(command, streaming=str(command.get("command", "")).upper() == "START_STREAM")


def _update_command(command: dict) -> dict:
    return _command_result(command, **install_update())


def _input_command(command: dict) -> dict:
    control_input(str(command.get("command", "")).upper(), command.get("params", {}))
    return _command_result(command, ok=True)


def _system_info_command(command: dict) -> dict:
    return _command_result(command, system=snapshot(), screen=screen_info())


def _process_list_command(command: dict) -> dict:
    return _command_result(command, processes=list_processes())


def _send_file_command(command: dict) -> dict:
    params = command.get("params", {})
    name = Path(str(params.get("name", "transfer.bin"))).name or "transfer.bin"
    destination = str(params.get("destination", "")).strip()
    if not destination:
        destination = str(Path.home() / "Downloads" / name)
    encoded = str(params.get("content", ""))
    expected_hash = str(params.get("sha256", "")).lower()
    if not encoded:
        raise ValueError("file content is empty")
    LOGGER.info("[FILE] receiving %s", name)
    raw = base64.b64decode(encoded, validate=True)
    if len(raw) > config.MAX_TRANSFER_BYTES:
        raise ValueError(f"file exceeds {config.MAX_TRANSFER_BYTES // (1024 * 1024)} MB limit")
    actual_hash = hashlib.sha256(raw).hexdigest()
    if expected_hash and actual_hash != expected_hash:
        raise ValueError("file checksum mismatch")
    target = Path(destination).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(raw)
    LOGGER.info("[FILE] received %s (%d bytes) -> %s", name, len(raw), target)
    return _command_result(command, ok=True, path=str(target), size=len(raw), sha256=actual_hash)


COMMAND_HANDLERS = {
    "STATUS": _status_command,
    "GET_LOGS": _logs_command,
    "SCREENSHOT": _screenshot_command,
    "START_STREAM": _stream_command,
    "STOP_STREAM": _stream_command,
    "UPDATE": _update_command,
    "MOUSE_MOVE": _input_command,
    "MOUSE_DOWN": _input_command,
    "MOUSE_UP": _input_command,
    "KEY": _input_command,
    "SYSTEM_INFO": _system_info_command,
    "LIST_PROCESSES": _process_list_command,
    "SEND_FILE": _send_file_command,
}


def execute_command(command: dict) -> dict:
    action = str(command.get("command", "")).upper()
    process = str(command.get("process", ""))
    handler = COMMAND_HANDLERS.get(action)
    if handler:
        return handler(command)
    if process not in process_module.PROCESS_DEFINITIONS:
        raise ValueError("a valid process is required")
    handlers = {"START": start_process, "STOP": stop_process, "RESTART": restart_process}
    if action not in handlers:
        raise ValueError(f"unsupported command: {action}")
    return {"command_id": command.get("command_id"), "command": action, **handlers[action](process)}


def execute_command_safely(command: dict) -> dict:
    try:
        return execute_command(command)
    except Exception as exc:
        LOGGER.exception("Command %s failed", command.get("command"))
        return {
            "command_id": command.get("command_id"),
            "command": command.get("command"),
            "error": f"{type(exc).__name__}: {exc}",
        }


def run(once: bool = False) -> int:
    LOGGER.info("FarmAgent started; server=%s", config.SERVER_URL)
    LOGGER.info("FarmAgent готов к работе и ожидает команды")
    last_screenshot = 0.0
    last_heartbeat = 0.0
    streaming = False
    stream_stop = threading.Event()
    stream_thread = None
    next_poll_at = time.monotonic() + random.uniform(0.0, config.COMMAND_POLL_INTERVAL)
    poll_backoff = config.COMMAND_POLL_INTERVAL
    last_network_warning = {"heartbeat": 0.0, "poll": 0.0}
    payload = collect_payload()
    while True:
        try:
            now = time.monotonic()
            if now - last_heartbeat >= max(1, config.HEARTBEAT_INTERVAL):
                payload = collect_payload()
                try:
                    config.LAST_PING_MS = send_heartbeat(payload)
                    pull_configuration()
                    last_heartbeat = now
                except (OSError, RuntimeError, URLError, ValueError) as exc:
                    if now - last_network_warning["heartbeat"] >= 30:
                        LOGGER.warning("heartbeat/config failed: %s", exc)
                        last_network_warning["heartbeat"] = now
            command = None
            if now >= next_poll_at:
                try:
                    command = poll_command(payload["device_id"])
                    poll_backoff = config.COMMAND_POLL_INTERVAL
                    next_poll_at = now + config.COMMAND_POLL_INTERVAL + random.uniform(0.0, 0.25)
                except (OSError, RuntimeError, URLError, ValueError) as exc:
                    if now - last_network_warning["poll"] >= 30:
                        LOGGER.warning("command poll failed: %s", exc)
                        last_network_warning["poll"] = now
                    poll_backoff = min(10.0, max(config.COMMAND_POLL_INTERVAL, poll_backoff * 2))
                    next_poll_at = now + poll_backoff + random.uniform(0.0, 0.5)
            if command:
                try:
                    result = execute_command_safely(command)
                    if command.get("command") == "START_STREAM":
                        streaming = bool(result.get("streaming"))
                        stream_stop.clear()
                        if stream_thread is None or not stream_thread.is_alive():
                            stream_thread = threading.Thread(target=stream_frames, args=(payload["device_id"], stream_stop), name="screen-stream", daemon=True)
                            stream_thread.start()
                    elif command.get("command") == "STOP_STREAM":
                        streaming = False
                        stream_stop.set()
                    send_result(result, payload["device_id"])
                    if command.get("command") == "SCREENSHOT":
                        if result.get("screenshot"):
                            LOGGER.info("SCREENSHOT sent (ok)")
                        else:
                            LOGGER.error("SCREENSHOT failed: %s", result.get("error", "empty result"))
                    if command.get("command") == "UPDATE" and result.get("updated"):
                        LOGGER.info("Update staged; restarting FarmAgent")
                        return 0
                except (OSError, RuntimeError, ValueError) as exc:
                    LOGGER.error("Result delivery for %s failed: %s", command.get("command"), exc)
            if config.SCREENSHOT_INTERVAL > 0 and time.monotonic() - last_screenshot >= config.SCREENSHOT_INTERVAL:
                send_result({"command_id": "periodic", "command": "SCREENSHOT", "screenshot": screenshot_jpeg(config.SCREENSHOT_QUALITY)}, payload["device_id"])
                last_screenshot = time.monotonic()
        except (OSError, RuntimeError, URLError, ValueError) as exc:
            LOGGER.warning("agent loop failed: %s", exc)
        if once:
            stream_stop.set()
            return 0
        time.sleep(max(0.03, config.COMMAND_POLL_INTERVAL))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="FarmAgent", description="DroidFleet cross-platform agent")
    parser.add_argument("--once", action="store_true", help="send one heartbeat and exit")
    parser.add_argument("--server", help="heartbeat URL")
    parser.add_argument("--updated", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.server:
        config.SERVER_URL = args.server
    config.UPDATE_COMPLETED = args.updated
    print("=" * 54)
    print(f"FarmAgent | DroidFleet {config.AGENT_VERSION}")
    print("Visible remote-support mode. Keep this console open.")
    print("=" * 54)
    config.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.handlers.RotatingFileHandler(
                config.LOG_FILE, encoding="utf-8", maxBytes=5 * 1024 * 1024, backupCount=3
            ),
        ],
    )
    try:
        configure_autostart(config.SERVER_URL)
        LOGGER.info("Автозапуск FarmAgent настроен")
    except OSError as exc:
        LOGGER.warning("Не удалось настроить автозапуск: %s", exc)
    if args.updated:
        LOGGER.info("[UPDATE] Обновление установлено, подключение к серверу восстанавливается")
    return run(args.once)


if __name__ == "__main__":
    raise SystemExit(main())
