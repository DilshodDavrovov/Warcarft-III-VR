# -*- coding: utf-8 -*-
"""
Head-look для Warcraft III 1.26 через ВСТРОЕННЫЕ клавиши камеры игры.

Почему не «прямая запись угла в память»: на билде 1.26 такого примитива нет.
Я перебрал ~850 угловых адресов: значения, запись в которые поворачивает
вид, НЕ удерживаются (перезаписываются рендером каждый кадр); а те, что
удерживаются, на вид не влияют. Живое состояние камеры пересобирается из
входа каждый кадр, поэтому «poke угла» невозможен (то же ограничение обходил
хак Xenon — он не пишет в камеру, а меняет таблицу настроек + рефреш-клавиша).

Рабочее решение — управлять камерой её же РОДНЫМИ клавишами:
    голова влево/вправо -> Insert / Delete   (поворот)
    голова вверх/вниз   -> PageDown / PageUp  (наклон, угол атаки)

Скорость поворота — пропорциональна тому, насколько повёрнута голова:
чуть повернул — камера едет медленно, сильно повернул — быстро, вернул
голову к центру — стоп. Работает надёжно в любой партии, без записи в память.

Игра должна быть активным окном на ПК. Использовать в одиночной игре
(на анти-чит-серверах автоматизация ввода тоже может быть нарушением).
"""

import ctypes
import time
import threading

# ------------------------- настройки -------------------------
DEADZONE_YAW = 0.10       # рад (~6°): в пределах — не крутим
DEADZONE_PITCH = 0.12     # рад (~7°)
FULLSPEED_YAW = 0.6       # рад (~34°): при таком повороте головы — макс. скорость
FULLSPEED_PITCH = 0.5     # рад (~29°)
MIN_DUTY = 0.25           # минимальная доля «газа» сразу за мёртвой зоной
INVERT_YAW = False        # True -> поменять лево/право
INVERT_PITCH = False      # True -> поменять верх/низ
ENABLE_PITCH = True       # False -> только поворот, без наклона
KEEP_FOREGROUND = True
TICK_HZ = 60
DUTY_PERIOD = 0.18        # сек: период широтно-импульсной модуляции скорости
# --------------------------------------------------------------

user32 = ctypes.windll.user32
VK = {"INSERT": 0x2D, "DELETE": 0x2E, "PAGEUP": 0x21, "PAGEDOWN": 0x22}
_EXT = set(VK.values())
KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002


class CameraSync:
    """API: set_pose/enable/disable/recenter/status. Пропорциональный клавишный драйвер."""

    def __init__(self, log=print):
        self.log = log
        self._pose = (0.0, 0.0)     # (yaw, pitch) рад, относительно нейтрали
        self._pose_time = 0.0
        self._enabled = False
        self._held = {}
        self._hwnd = 0
        self._last_error = ""
        threading.Thread(target=self._loop, daemon=True).start()

    # ---------- API ----------

    def set_pose(self, yaw, pitch):
        self._pose = (float(yaw), float(pitch))
        self._pose_time = time.time()

    def recenter(self):
        pass   # нейтраль держит клиент; серверу сбрасывать нечего

    def enable(self):
        self._enabled = True

    def disable(self):
        self._enabled = False
        self._release_all()

    def status(self):
        return {
            "enabled": self._enabled,
            "attached": bool(self._hwnd),
            "mode": "keys-proportional",
            "held": [n for n, v in self._held.items() if v],
            "error": self._last_error,
        }

    # ---------- окно/клавиши ----------

    def _find_window(self):
        # Reforged (OsWindow) в приоритете; классика ("Warcraft III") запасным
        return (user32.FindWindowW("OsWindow", None)
                or user32.FindWindowW("Warcraft III", None)
                or user32.FindWindowW(None, "Warcraft III"))

    def _ensure_foreground(self):
        if KEEP_FOREGROUND and user32.GetForegroundWindow() != self._hwnd:
            user32.SetForegroundWindow(self._hwnd)
            time.sleep(0.02)

    def _key(self, name, down):
        vk = VK[name]
        if self._held.get(name, False) == down:
            return
        sc = user32.MapVirtualKeyW(vk, 0)
        flags = KEYEVENTF_EXTENDEDKEY if vk in _EXT else 0
        if not down:
            flags |= KEYEVENTF_KEYUP
        user32.keybd_event(vk, sc, flags, 0)
        self._held[name] = down

    def _release_all(self):
        for n in VK:
            self._key(n, False)

    # ---------- пропорциональная ось ----------

    def _duty(self, value, dead, full):
        """Доля 'газа' 0..1 и знак по величине отклонения головы."""
        mag = abs(value)
        if mag <= dead:
            return 0.0, 0
        s = (mag - dead) / max(1e-6, (full - dead))
        s = max(MIN_DUTY, min(1.0, s))
        return s, (1 if value > 0 else -1)

    def _drive_axis(self, value, dead, full, key_pos, key_neg, invert, phase_on):
        duty, sign = self._duty(value, dead, full)
        if invert:
            sign = -sign
        if sign == 0 or not phase_on(duty):
            self._key(key_pos, False); self._key(key_neg, False)
            return
        if sign > 0:
            self._key(key_pos, True); self._key(key_neg, False)
        else:
            self._key(key_neg, True); self._key(key_pos, False)

    # ---------- главный цикл ----------

    def _loop(self):
        period = 1.0 / TICK_HZ
        while True:
            time.sleep(period)
            if not self._enabled:
                if any(self._held.values()):
                    self._release_all()
                self._hwnd = 0
                continue

            h = self._find_window()
            if not h:
                self._last_error = "окно игры не найдено (war3.exe -window)"
                self._hwnd = 0
                continue
            self._hwnd = h
            self._last_error = ""
            self._ensure_foreground()

            if time.time() - self._pose_time > 1.0:
                if any(self._held.values()):
                    self._release_all()
                continue

            # широтно-импульсная модуляция: «газ» = доля периода, когда клавиша нажата
            ph = (time.time() % DUTY_PERIOD) / DUTY_PERIOD
            def phase_on(duty, ph=ph):
                return ph < duty

            yaw, pitch = self._pose
            self._drive_axis(yaw, DEADZONE_YAW, FULLSPEED_YAW,
                             "INSERT", "DELETE", INVERT_YAW, phase_on)
            if ENABLE_PITCH:
                self._drive_axis(pitch, DEADZONE_PITCH, FULLSPEED_PITCH,
                                 "PAGEDOWN", "PAGEUP", INVERT_PITCH, phase_on)
