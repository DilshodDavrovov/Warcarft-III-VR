# -*- coding: utf-8 -*-
"""
WC3 VR Server — захватывает окно Warcraft III и стримит его в браузер Quest 2 (WebXR).

Запуск:  python server.py            (или через START-VR-SERVER.bat)
Затем на Quest 2 в браузере открыть  https://<IP этого ПК>:8443
"""

import ctypes
import ctypes.wintypes as wt
import json
import socket
import ssl
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import cv2
import mss
import numpy as np

from camera_sync import CameraSync
from cam_hook_driver import HookCameraSync
from cam_cine_driver import CineCameraSync

# ------------------------- настройки -------------------------
PORT = 8443                 # HTTPS-порт
TARGET_FPS = 30             # целевой FPS стрима
JPEG_QUALITY = 75           # 1..100 (выше = чётче, но больше трафик)
MAX_WIDTH = 1600            # кадр ужимается до этой ширины (0 = без сжатия)
# Классы окна: "Warcraft III" = классика 1.26-1.29; "OsWindow" = Reforged 1.32.
# Порядок = приоритет. Сейчас классика первой (1.29 играбельна офлайн без логина);
# для стрима Reforged поставь "OsWindow" первым.
# Warcraft III (классика 1.26) первым — для неё работает истинный 1:1 код-хук.
WINDOW_CLASSES = ["Warcraft III", "OsWindow"]
# Режим камеры:
#   "cinematic" = ИСТИННАЯ свободная камера 360° (кинематографический вызов, ТОЛЬКО 1.26)
#   "keys"      = клавишный джойстик (любая версия, с клампом)
CAMERA_MODE = "cinematic"
WINDOW_TITLE_EXACT = "Warcraft III"  # запасной поиск по точному заголовку
# --------------------------------------------------------------

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"

user32 = ctypes.windll.user32
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    pass


def find_game_window():
    """Ищет окно игры: по списку классов (Reforged/классика), затем по заголовку."""
    for cls in WINDOW_CLASSES:
        hwnd = user32.FindWindowW(cls, None)
        if hwnd and user32.IsWindowVisible(hwnd):
            return hwnd
    hwnd = user32.FindWindowW(None, WINDOW_TITLE_EXACT)
    if hwnd and user32.IsWindowVisible(hwnd):
        return hwnd
    return None


def window_client_rect(hwnd):
    """Экранные координаты клиентской области окна (без рамок)."""
    rect = wt.RECT()
    if not user32.GetClientRect(hwnd, ctypes.byref(rect)):
        return None
    pt = wt.POINT(0, 0)
    if not user32.ClientToScreen(hwnd, ctypes.byref(pt)):
        return None
    w, h = rect.right - rect.left, rect.bottom - rect.top
    if w < 32 or h < 32:
        return None
    return {"left": pt.x, "top": pt.y, "width": w, "height": h}


class FrameHub:
    """Последний JPEG-кадр + уведомление ожидающих клиентов."""

    def __init__(self):
        self.cond = threading.Condition()
        self.jpeg = None
        self.seq = 0
        self.size = (0, 0)
        self.fps = 0.0
        self.source = "нет"

    def publish(self, jpeg, size):
        with self.cond:
            self.jpeg = jpeg
            self.size = size
            self.seq += 1
            self.cond.notify_all()

    def wait_frame(self, last_seq, timeout=2.0):
        with self.cond:
            if self.seq == last_seq:
                self.cond.wait(timeout)
            return self.jpeg, self.seq


hub = FrameHub()

# --- управление мышью игры из VR-указателя ---
MOUSEEVENTF = {"ldown": 0x0002, "lup": 0x0004, "rdown": 0x0008, "rup": 0x0010}
_mouse_state = {"left": False, "right": False}


def _release_mouse():
    """Отпустить зажатые кнопки (когда указатель ушёл с экрана / вышли из VR)."""
    if _mouse_state["left"]:
        user32.mouse_event(MOUSEEVENTF["lup"], 0, 0, 0, 0); _mouse_state["left"] = False
    if _mouse_state["right"]:
        user32.mouse_event(MOUSEEVENTF["rup"], 0, 0, 0, 0); _mouse_state["right"] = False


def handle_input(p):
    """Позиция указателя (nx,ny в [0..1] по кадру) -> курсор игры; кнопки -> клики."""
    if not p.get("active", True):
        _release_mouse(); return
    hwnd = find_game_window()
    if not hwnd:
        return
    rect = window_client_rect(hwnd)
    if not rect:
        return
    try:
        nx = min(1.0, max(0.0, float(p.get("nx", 0.5))))
        ny = min(1.0, max(0.0, float(p.get("ny", 0.5))))
    except (TypeError, ValueError):
        return
    sx = rect["left"] + int(nx * (rect["width"] - 1))
    sy = rect["top"] + int(ny * (rect["height"] - 1))
    user32.SetCursorPos(sx, sy)
    # фронты кнопок: нажатие/отпускание только по смене состояния
    for name, want in (("left", bool(p.get("left"))), ("right", bool(p.get("right")))):
        if want and not _mouse_state[name]:
            user32.mouse_event(MOUSEEVENTF[name[0] + "down"], 0, 0, 0, 0); _mouse_state[name] = True
        elif not want and _mouse_state[name]:
            user32.mouse_event(MOUSEEVENTF[name[0] + "up"], 0, 0, 0, 0); _mouse_state[name] = False


if CAMERA_MODE == "cinematic":
    camsync = CineCameraSync()
elif CAMERA_MODE == "hook":
    camsync = HookCameraSync()
else:
    camsync = CameraSync()


def capture_loop():
    period = 1.0 / TARGET_FPS
    encode_params = [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY]
    fps_count, fps_t0 = 0, time.time()
    with mss.mss() as sct:
        while True:
            t_start = time.time()
            hwnd = find_game_window()
            region = window_client_rect(hwnd) if hwnd else None
            if region is None:
                # игра не найдена / свёрнута — берём весь основной монитор
                region = sct.monitors[1]
                hub.source = "весь экран (окно игры не найдено)"
            else:
                hub.source = "окно Warcraft III"

            try:
                shot = sct.grab(region)
            except Exception:
                time.sleep(0.5)
                continue

            frame = np.frombuffer(shot.bgra, dtype=np.uint8).reshape(shot.height, shot.width, 4)[:, :, :3]
            if MAX_WIDTH and shot.width > MAX_WIDTH:
                scale = MAX_WIDTH / shot.width
                frame = cv2.resize(frame, (MAX_WIDTH, max(2, int(shot.height * scale))), interpolation=cv2.INTER_AREA)

            ok, jpeg = cv2.imencode(".jpg", frame, encode_params)
            if ok:
                hub.publish(jpeg.tobytes(), (frame.shape[1], frame.shape[0]))
                fps_count += 1
                now = time.time()
                if now - fps_t0 >= 1.0:
                    hub.fps = fps_count / (now - fps_t0)
                    fps_count, fps_t0 = 0, now

            elapsed = time.time() - t_start
            if elapsed < period:
                time.sleep(period - elapsed)


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *_):
        pass

    def _send_file(self, path, ctype):
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        route = self.path.split("?")[0]
        if route == "/":
            self._send_file(STATIC / "index.html", "text/html; charset=utf-8")
        elif route == "/three.module.min.js":
            self._send_file(STATIC / "three.module.min.js", "text/javascript")
        elif route == "/status":
            body = json.dumps({
                "source": hub.source, "fps": round(hub.fps, 1),
                "width": hub.size[0], "height": hub.size[1],
                "camsync": camsync.status(),
            }).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif route == "/stream":
            self.send_response(200)
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            seq = 0
            try:
                while True:
                    jpeg, seq_new = hub.wait_frame(seq)
                    if jpeg is None or seq_new == seq:
                        continue
                    seq = seq_new
                    self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\n")
                    self.wfile.write(f"Content-Length: {len(jpeg)}\r\n\r\n".encode())
                    self.wfile.write(jpeg)
                    self.wfile.write(b"\r\n")
            except (ConnectionError, BrokenPipeError, OSError):
                pass
        else:
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()

    def do_POST(self):
        route = self.path.split("?")[0]
        length = int(self.headers.get("Content-Length", 0) or 0)
        try:
            payload = json.loads(self.rfile.read(length)) if length else {}
        except (ValueError, UnicodeDecodeError):
            payload = {}

        if route == "/pose":
            camsync.set_pose(payload.get("yaw", 0.0), payload.get("pitch", 0.0))
            if hasattr(camsync, "set_move"):
                camsync.set_move(payload.get("mx", 0.0), payload.get("my", 0.0))
            body = b"{}"
        elif route == "/camsync":
            if payload.get("on"):
                camsync.enable()
            else:
                camsync.disable()
            body = json.dumps(camsync.status()).encode()
        elif route == "/input":
            handle_input(payload)
            body = b"{}"
        elif route == "/recenter":
            camsync.recenter()
            body = b"{}"
        else:
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def main():
    ctypes.windll.kernel32.SetConsoleTitleW("WC3 VR Server")
    threading.Thread(target=capture_loop, daemon=True).start()

    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(ROOT / "certs" / "cert.pem", ROOT / "certs" / "key.pem")
    server.socket = ctx.wrap_socket(server.socket, server_side=True)

    ip = lan_ip()
    print("=" * 56)
    print("  WC3 VR Server запущен")
    print(f"  На Quest 2 открой в браузере:  https://{ip}:{PORT}")
    print("  (согласись с предупреждением о сертификате:")
    print("   Advanced -> Proceed)")
    print("=" * 56)
    server.serve_forever()


if __name__ == "__main__":
    main()
