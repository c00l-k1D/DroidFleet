from __future__ import annotations

import base64
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from app.adb.client import AdbClient
from app.actions.coordinates import normalize_to_device
from app.actions.input import send_tap, send_swipe, send_zoom


def _normalize_device(device):
    if isinstance(device, dict):
        serial = str(device.get("serial") or device.get("name") or "unknown").strip()
        model = str(device.get("model") or device.get("name") or serial).strip()
        status = str(device.get("status") or "online").strip().lower()
    else:
        serial = str(getattr(device, "serial", device)).strip() or "unknown"
        model = str(getattr(device, "model", serial)).strip() or serial
        status = str(getattr(device, "status", "online")).strip().lower()
    return {"serial": serial, "model": model, "status": status}


def _device_by_serial(devices, serial):
    for device in devices:
        normalized = _normalize_device(device)
        if normalized["serial"] == serial:
            return normalized
    return None


def _render_screenshot(screenshot_data=None, serial=""):
    if screenshot_data:
        data_url = "data:image/png;base64," + base64.b64encode(screenshot_data).decode("ascii")
        return f'<img class="device-screen" src="{data_url}" alt="{serial} screen">'
    return '<div class="device-screen placeholder">No screenshot</div>'


def render_device_details(serial, devices, screenshot_data=None):
    device = _device_by_serial(devices, serial) or {"serial": serial, "model": serial, "status": "online"}
    screenshot_html = _render_screenshot(screenshot_data, serial)
    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>DroidLeet — {device['model']}</title>
    <style>
        :root {{
            --bg: #0c1117;
            --panel: #151d27;
            --primary: #4ec6ff;
            --text: #eaf4ff;
            --muted: #97a9bd;
            --online: #5fe39d;
        }}
        * {{ box-sizing: border-box; }}
        body {{
            margin: 0;
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            font-family: "Segoe UI", Arial, sans-serif;
            background: linear-gradient(180deg, #0a0f14 0%, #101a24 100%);
            color: var(--text);
        }}
        .panel {{
            width: min(960px, 94vw);
            background: rgba(13, 17, 22, 0.8);
            border: 1px solid rgba(120, 160, 190, 0.18);
            border-radius: 18px;
            box-shadow: 0 20px 50px rgba(0,0,0,0.35);
            padding: 28px 26px 20px;
        }}
        .header {{
            text-align: center;
            font-size: 1.5rem;
            font-weight: 700;
            color: var(--primary);
            margin-bottom: 18px;
        }}
        .device-box {{
            background: linear-gradient(180deg, rgba(28, 39, 51, 0.96), rgba(17, 24, 31, 0.96));
            border: 1px solid rgba(142, 163, 182, 0.15);
            border-radius: 14px;
            padding: 22px 18px;
        }}
        .device-name {{
            font-size: 1.5rem;
            margin-bottom: 12px;
            font-weight: 700;
            text-align: center;
        }}
        .status {{
            display: inline-flex;
            align-items: center;
            gap: 8px;
            color: var(--online);
            font-weight: 700;
            margin-bottom: 14px;
        }}
        .dot {{
            width: 10px;
            height: 10px;
            background: var(--online);
            border-radius: 50%;
            box-shadow: 0 0 10px rgba(95, 227, 157, 0.9);
        }}
        .serial {{
            color: var(--muted);
            margin-bottom: 20px;
            word-break: break-all;
            text-align: center;
        }}
        .screen-wrap {{
            display: flex;
            justify-content: center;
            margin: 20px 0;
        }}
        .device-screen {{
            max-width: min(90vw, 720px);
            max-height: 460px;
            border-radius: 12px;
            border: 1px solid rgba(130, 153, 172, 0.3);
            box-shadow: 0 14px 30px rgba(0,0,0,0.2);
            background: #0e1720;
            touch-action: none;
            cursor: crosshair;
        }}
        .device-screen.placeholder {{
            padding: 40px 16px;
            color: var(--muted);
            min-width: 220px;
            text-align: center;
        }}
        .actions {{
            display: flex;
            justify-content: center;
            gap: 12px;
            flex-wrap: wrap;
            margin-top: 10px;
        }}
        .btn {{
            display: inline-block;
            border-radius: 10px;
            padding: 12px 18px;
            text-decoration: none;
            font-weight: 700;
            letter-spacing: 0.08em;
            transition: transform 0.12s ease;
        }}
        .btn:hover {{ transform: translateY(-1px); }}
        .secondary {{
            background: rgba(122, 149, 169, 0.12);
            color: var(--text);
            border: 1px solid rgba(142, 163, 182, 0.2);
        }}
        .control-btn {{
            background: rgba(122, 149, 169, 0.12);
            color: var(--text);
            border: 1px solid rgba(142, 163, 182, 0.2);
            border-radius: 8px;
            padding: 10px 14px;
            font-weight: 700;
            text-decoration: none;
        }}
    </style>
</head>
<body>
    <main class="panel">
        <div class="header">DroidLeet</div>
        <div class="device-box">
            <div class="device-name">{device['model']}</div>
            <div class="status"><span class="dot"></span> Online</div>
            <div class="serial">{device['serial']}</div>
            <div class="screen-wrap">{screenshot_html}</div>
            <div class="actions">
                <button class="control-btn" type="button" data-action="HOME" data-serial="{device['serial']}">HOME</button>
                <button class="control-btn" type="button" data-action="BACK" data-serial="{device['serial']}">BACK</button>
                <button class="control-btn" type="button" data-action="POWER" data-serial="{device['serial']}">POWER</button>
                <button class="control-btn" type="button" data-action="RECENTS" data-serial="{device['serial']}">RECENTS</button>
                <button class="control-btn" type="button" data-action="KEEP_AWAKE_ON" data-serial="{device['serial']}">KEEP AWAKE</button>
                <button class="control-btn" type="button" data-action="SCREEN_OFF" data-serial="{device['serial']}">SCREEN OFF</button>
                <button class="control-btn" type="button" data-action="SWIPE" data-serial="{device['serial']}">SWIPE</button>
                <a class="btn secondary" href="/">Back to devices</a>
            </div>
        </div>
    </main>
    <script>
        const serial = "{device['serial']}";
        const image = document.querySelector('.device-screen');
        if (image) {{
            const refreshImage = () => {{
                const url = `/screen?serial=${{encodeURIComponent(serial)}}&_=${{Date.now()}}`;
                image.src = url;
            }};
            setInterval(refreshImage, 1800);

            const sendAction = (action, extra = '') => {{
                const qs = new URLSearchParams({{ serial, action }});
                for (const [key, value] of Object.entries(extra)) {{
                    qs.append(key, value);
                }}
                fetch(`/control?${{qs.toString()}}`);
            }};

            document.querySelectorAll('[data-action]').forEach((button) => {{
                button.addEventListener('click', () => {{
                    const action = button.dataset.action;
                    if (action === 'SWIPE') {{
                        sendAction('SWIPE', {{ x1: '200', y1: '200', x2: '500', y2: '200', duration: '200' }});
                        return;
                    }}
                    sendAction(action);
                }});
            }});

            let pointerStart = null;
            image.addEventListener('pointerdown', (event) => {{
                const rect = image.getBoundingClientRect();
                pointerStart = {{
                    x: Math.round(((event.clientX - rect.left) / rect.width) * 1000),
                    y: Math.round(((event.clientY - rect.top) / rect.height) * 1000)
                }};
                image.setPointerCapture?.(event.pointerId);
            }});

            image.addEventListener('pointermove', (event) => {{
                if (!pointerStart) return;
                const rect = image.getBoundingClientRect();
                const currentX = Math.round(((event.clientX - rect.left) / rect.width) * 1000);
                const currentY = Math.round(((event.clientY - rect.top) / rect.height) * 1000);
                pointerStart = {{ ...pointerStart, currentX, currentY }};
            }});

            image.addEventListener('pointerup', (event) => {{
                if (!pointerStart) return;
                const rect = image.getBoundingClientRect();
                const endX = Math.round(((event.clientX - rect.left) / rect.width) * 1000);
                const endY = Math.round(((event.clientY - rect.top) / rect.height) * 1000);
                const dx = endX - pointerStart.x;
                const dy = endY - pointerStart.y;

                if (Math.max(Math.abs(dx), Math.abs(dy)) > 80) {{
                    sendAction('SWIPE', {{ x1: String(pointerStart.x), y1: String(pointerStart.y), x2: String(endX), y2: String(endY), duration: '180' }});
                }} else {{
                    sendAction('TAP', {{ x: String(endX), y: String(endY) }});
                }}
                pointerStart = null;
            }});

            image.addEventListener('wheel', (event) => {{
                event.preventDefault();
                const rect = image.getBoundingClientRect();
                const x = Math.round(((event.clientX - rect.left) / rect.width) * 1000);
                const y = Math.round(((event.clientY - rect.top) / rect.height) * 1000);
                const action = event.deltaY < 0 ? 'ZOOM_IN' : 'ZOOM_OUT';
                sendAction(action, {{ x: String(x), y: String(y) }});
            }}, {{ passive: false }});
        }}
    </script>
</body>
</html>
"""


def render_device_cards(devices):
    normalized = [_normalize_device(device) for device in devices]
    if not normalized:
        cards_html = """
        <div class="empty-state">
            <p>Нет онлайн-устройств</p>
        </div>
        """
    else:
        cards_html = "\n".join(
            f"""
            <div class="device-card">
                <div class="device-label">[ {device['model']} ]</div>
                <div class="device-status">
                    <span class="status-dot online"></span>
                    <span>Online</span>
                </div>
                <button class="connect-btn" data-serial="{device['serial']}" onclick="window.location.href='/connect?serial=' + encodeURIComponent(this.dataset.serial)">CONNECT</button>
            </div>
            """.format(device=device)
            for device in normalized
        )

    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>DroidLeet</title>
    <style>
        :root {{
            --bg: #0c1117;
            --panel: #151d27;
            --panel-alt: #1d2a38;
            --primary: #4ec6ff;
            --accent: #8fd5ff;
            --text: #eaf4ff;
            --muted: #97a9bd;
            --online: #5fe39d;
            --shadow: rgba(0, 0, 0, 0.35);
        }}
        * {{ box-sizing: border-box; }}
        body {{
            margin: 0;
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            font-family: "Segoe UI", Arial, sans-serif;
            background: linear-gradient(180deg, #0a0f14 0%, #101a24 100%);
            color: var(--text);
        }}
        .app {{
            width: min(720px, 90vw);
            background: rgba(13, 17, 22, 0.8);
            border: 1px solid rgba(120, 160, 190, 0.18);
            box-shadow: 0 20px 50px var(--shadow);
            border-radius: 18px;
            padding: 28px 26px 20px;
        }}
        .title {{
            text-align: center;
            font-size: 1.7rem;
            font-weight: 700;
            letter-spacing: 0.08em;
            margin-bottom: 20px;
            color: var(--accent);
        }}
        .devices {{
            display: flex;
            flex-direction: column;
            gap: 14px;
            margin-bottom: 24px;
        }}
        .device-card {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 18px;
            background: linear-gradient(180deg, rgba(28, 39, 51, 0.96), rgba(17, 24, 31, 0.96));
            border: 1px solid rgba(142, 163, 182, 0.15);
            border-radius: 12px;
            padding: 14px 16px;
            min-height: 64px;
        }}
        .device-label {{
            flex: 1;
            font-size: 1.05rem;
            letter-spacing: 0.02em;
            color: var(--text);
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }}
        .device-status {{
            display: inline-flex;
            align-items: center;
            gap: 8px;
            color: var(--online);
            font-weight: 600;
            font-size: 0.92rem;
            min-width: 92px;
            justify-content: flex-end;
        }}
        .status-dot {{
            display: inline-block;
            width: 10px;
            height: 10px;
            border-radius: 50%;
            background: var(--online);
            box-shadow: 0 0 10px rgba(95, 227, 157, 0.9);
        }}
        .connect-btn {{
            border: 0;
            border-radius: 10px;
            background: linear-gradient(180deg, #4ec6ff 0%, #1a9be8 100%);
            color: #061522;
            font-weight: 800;
            letter-spacing: 0.14em;
            padding: 12px 18px;
            cursor: pointer;
            box-shadow: 0 8px 16px rgba(30, 155, 232, 0.35);
            transition: transform 0.12s ease;
        }}
        .connect-btn:hover {{
            transform: translateY(-1px);
        }}
        .footer-note {{
            text-align: center;
            color: var(--muted);
            font-size: 0.92rem;
            line-height: 1.5;
            margin-top: 12px;
        }}
        .empty-state {{
            text-align: center;
            color: var(--muted);
            padding: 22px 16px;
            border: 1px dashed rgba(142, 163, 182, 0.3);
            border-radius: 12px;
        }}
        @media (max-width: 560px) {{
            .device-card {{
                flex-wrap: wrap;
                justify-content: center;
                text-align: center;
            }}
            .device-label {{
                width: 100%;
                text-align: center;
            }}
            .device-status {{
                justify-content: center;
            }}
        }}
    </style>
</head>
<body>
    <main class="app">
        <div class="title">DroidLeet</div>
        <div class="devices">
            {cards_html}
        </div>
        <div class="footer-note">
            Разработчик подключается к конкретному устройству и тестирует приложение.
        </div>
    </main>
</body>
</html>
"""


def _device_payload(client):
    if not client or not getattr(client, "executable", None):
        return []
    devices = []
    for serial, state in client.device_states():
        if state != "device":
            continue
        try:
            info = client.hardware_info(serial)
            model = info.model or serial
        except Exception:
            model = serial
        devices.append({"serial": serial, "model": model, "status": "online"})
    return devices


class DeviceWebHandler(BaseHTTPRequestHandler):
    server_version = "DroidLeet/1.0"

    def _refresh_devices(self):
        if self.server.client and getattr(self.server.client, "executable", None):
            self.server.devices = _device_payload(self.server.client)
        return self.server.devices

    def _capture_screenshot(self, serial):
        client = getattr(self.server, "client", None)
        if not client or not getattr(client, "executable", None):
            return None
        try:
            result = client.run(["exec-out", "screencap", "-p"], serial, timeout=2)
            if result.returncode == 0 and result.stdout:
                return result.stdout
        except Exception:
            pass
        return None

    def _send_text(self, text, status=200):
        body = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_image(self, payload):
        self.send_response(200)
        self.send_header("Content-Type", "image/png")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _run_control_action(self, client, serial, action, query):
        key_map = {"HOME": "KEYCODE_HOME", "BACK": "KEYCODE_BACK", "POWER": "KEYCODE_POWER", "RECENTS": "KEYCODE_APP_SWITCH"}
        if action in key_map:
            key = key_map[action]
            return client.run(["shell", "input", "keyevent", key], serial, timeout=3)
        if action == "SCREEN_OFF":
            client.run(["shell", "svc", "power", "stayon", "true"], serial, timeout=3)
            return client.run(["shell", "input", "keyevent", "KEYCODE_POWER"], serial, timeout=3)
        if action == "SCREEN_ON":
            client.run(["shell", "svc", "power", "stayon", "true"], serial, timeout=3)
            return client.run(["shell", "input", "keyevent", "KEYCODE_POWER"], serial, timeout=3)
        if action == "KEEP_AWAKE_ON":
            return client.run(["shell", "svc", "power", "stayon", "true"], serial, timeout=3)
        if action == "KEEP_AWAKE_OFF":
            return client.run(["shell", "svc", "power", "stayon", "false"], serial, timeout=3)
        if action == "WAKE":
            return client.run(["shell", "input", "keyevent", "KEYCODE_WAKEUP"], serial, timeout=3)
        if action == "TAP":
            norm_x = int(query.get("x", ["500"])[0])
            norm_y = int(query.get("y", ["500"])[0])
            device_x, device_y = normalize_to_device(norm_x, norm_y, client, serial)
            return send_tap(client, serial, device_x, device_y)
        if action == "SWIPE":
            norm_x1 = int(query.get("x1", ["200"])[0])
            norm_y1 = int(query.get("y1", ["200"])[0])
            norm_x2 = int(query.get("x2", ["500"])[0])
            norm_y2 = int(query.get("y2", ["500"])[0])
            duration = int(query.get("duration", ["180"])[0])
            x1, y1 = normalize_to_device(norm_x1, norm_y1, client, serial)
            x2, y2 = normalize_to_device(norm_x2, norm_y2, client, serial)
            return send_swipe(client, serial, x1, y1, x2, y2, duration)
        if action in {"ZOOM_IN", "ZOOM_OUT"}:
            norm_cx = int(query.get("x", ["500"])[0])
            norm_cy = int(query.get("y", ["500"])[0])
            cx, cy = normalize_to_device(norm_cx, norm_cy, client, serial)
            # Calculate offset relative to device resolution
            width, _ = client.get_device_resolution(serial)
            offset = max(60, width // 18)  # Scale offset with device resolution
            return send_zoom(client, serial, cx, cy, zoom_in=(action == "ZOOM_IN"), offset=offset)
        raise ValueError(f"Unsupported action: {action}")

    def do_GET(self):
        parsed = urlparse(self.path)
        self._refresh_devices()
        if parsed.path == "/api/devices":
            payload = json.dumps({"devices": self.server.devices}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        if parsed.path.startswith("/screen"):
            query = parse_qs(parsed.query)
            serial = query.get("serial", ["unknown"])[0]
            payload = self._capture_screenshot(serial)
            if not payload:
                self._send_text("No screenshot available", status=404)
                return
            self._send_image(payload)
            return

        if parsed.path.startswith("/control"):
            query = parse_qs(parsed.query)
            serial = query.get("serial", ["unknown"])[0]
            action = (query.get("action", ["HOME"])[0] or "HOME").upper()
            client = getattr(self.server, "client", None)
            if client and getattr(client, "executable", None):
                try:
                    self._run_control_action(client, serial, action, query)
                    self._send_text(f"Sent {action} to {serial}")
                    return
                except Exception as exc:
                    self._send_text(f"Control error: {exc}", status=500)
                    return
            self._send_text("ADB not available", status=500)
            return

        if parsed.path.startswith("/connect"):
            query = parse_qs(parsed.query)
            serial = query.get("serial", ["unknown"])[0]
            body = render_device_details(serial, self.server.devices, screenshot_data=self._capture_screenshot(serial)).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        body = render_device_cards(self.server.devices).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        return


class DeviceWebServer(ThreadingHTTPServer):
    allow_reuse_address = True

    def __init__(self, server_address, RequestHandlerClass, client):
        super().__init__(server_address, RequestHandlerClass)
        self.client = client
        self.devices = _device_payload(client)


def run_web_interface(host: str = "127.0.0.1", port: int = 8000, client: AdbClient | None = None):
    adb_client = client or AdbClient()
    server = DeviceWebServer((host, port), DeviceWebHandler, adb_client)
    print(f"DroidLeet web UI: http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nWeb UI stopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    run_web_interface()
