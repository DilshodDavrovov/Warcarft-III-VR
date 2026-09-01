# -*- coding: utf-8 -*-
"""
Автономная проверка камеры WC3 1.26: пишем тестовые значения в память
и СМОТРИМ через захват экрана, изменилась ли картинка.

Фазы:
  A. дамп float-полей вокруг game.dll+0x93645C
  B. запись тестовых значений в кандидатов + визуальная проверка (diff кадров)
"""

import ctypes
import ctypes.wintypes as wt
import math
import struct
import sys
import time

import cv2
import mss
import numpy as np

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    pass

DIST_OFFSET = 0x93645C
PROCESS_ALL = 0x0010 | 0x0020 | 0x0008 | 0x0400  # read|write|operation|query
TH32 = 0x08 | 0x10


class MODULEENTRY32(ctypes.Structure):
    _fields_ = [
        ("dwSize", wt.DWORD), ("th32ModuleID", wt.DWORD), ("th32ProcessID", wt.DWORD),
        ("GlblcntUsage", wt.DWORD), ("ProccntUsage", wt.DWORD),
        ("modBaseAddr", ctypes.POINTER(ctypes.c_byte)), ("modBaseSize", wt.DWORD),
        ("hModule", wt.HMODULE), ("szModule", ctypes.c_char * 256),
        ("szExePath", ctypes.c_char * 260),
    ]


def find_window():
    hwnd = user32.FindWindowW("Warcraft III", None)
    if not hwnd:
        hwnd = user32.FindWindowW(None, "Warcraft III")
    return hwnd


def attach():
    hwnd = find_window()
    if not hwnd:
        sys.exit("NO_WINDOW: окно игры не найдено")
    pid = wt.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    h = kernel32.OpenProcess(PROCESS_ALL, False, pid.value)
    if not h:
        sys.exit(f"OPEN_FAIL: err {ctypes.get_last_error()}")
    snap = kernel32.CreateToolhelp32Snapshot(TH32, pid.value)
    me = MODULEENTRY32()
    me.dwSize = ctypes.sizeof(MODULEENTRY32)
    base = size = None
    if kernel32.Module32First(snap, ctypes.byref(me)):
        while True:
            if me.szModule.lower() == b"game.dll":
                base = ctypes.cast(me.modBaseAddr, ctypes.c_void_p).value
                size = me.modBaseSize
                break
            if not kernel32.Module32Next(snap, ctypes.byref(me)):
                break
    kernel32.CloseHandle(snap)
    if not base:
        sys.exit("NO_GAMEDLL")
    return hwnd, h, base, size


def rmem(h, addr, size):
    buf = ctypes.create_string_buffer(size)
    got = ctypes.c_size_t()
    if not kernel32.ReadProcessMemory(h, ctypes.c_void_p(addr), buf, size, ctypes.byref(got)):
        return None
    return buf.raw


def wfloat(h, addr, value):
    data = struct.pack("<f", value)
    n = ctypes.c_size_t()
    ok = kernel32.WriteProcessMemory(h, ctypes.c_void_p(addr), data, 4, ctypes.byref(n))
    if not ok:
        old = wt.DWORD()
        kernel32.VirtualProtectEx(h, ctypes.c_void_p(addr), 4, 0x40, ctypes.byref(old))
        ok = kernel32.WriteProcessMemory(h, ctypes.c_void_p(addr), data, 4, ctypes.byref(n))
    return bool(ok)


def rfloat(h, addr):
    d = rmem(h, addr, 4)
    return struct.unpack("<f", d)[0] if d else None


def grab(sct, hwnd):
    rect = wt.RECT()
    user32.GetClientRect(hwnd, ctypes.byref(rect))
    pt = wt.POINT(0, 0)
    user32.ClientToScreen(hwnd, ctypes.byref(pt))
    shot = sct.grab({"left": pt.x, "top": pt.y,
                     "width": rect.right - rect.left, "height": rect.bottom - rect.top})
    img = np.frombuffer(shot.bgra, np.uint8).reshape(shot.height, shot.width, 4)[:, :, :3]
    small = cv2.resize(img, (320, 180), interpolation=cv2.INTER_AREA)
    return cv2.cvtColor(small, cv2.COLOR_BGR2GRAY).astype(np.int16)


def vis_diff(sct, hwnd, action, settle=0.7):
    """Возвращает (базовый шум, diff после действия)."""
    a = grab(sct, hwnd)
    time.sleep(0.35)
    b = grab(sct, hwnd)
    noise = float(np.abs(b - a).mean())
    action()
    time.sleep(settle)
    c = grab(sct, hwnd)
    return noise, float(np.abs(c - b).mean())


def main():
    hwnd, h, base, size = attach()
    print(f"attached: game.dll base={base:#x} size={size:#x}")
    dist_addr = base + DIST_OFFSET

    # --- фаза A: дамп ---
    data = rmem(h, dist_addr - 0x100, 0x200)
    print("\n=== дамп float вокруг game.dll+0x93645C ===")
    interesting = []
    for i in range(0, len(data) - 3, 4):
        off = DIST_OFFSET - 0x100 + i
        (f,) = struct.unpack_from("<f", data, i)
        if 1e-6 < abs(f) < 1e7:
            mark = " <== DIST" if off == DIST_OFFSET else ""
            print(f"  +{off:#08x}  {f:14.4f}{mark}")
            interesting.append((off, f))

    dist = rfloat(h, dist_addr)
    print(f"\ndistance = {dist}")

    with mss.mss() as sct:
        # --- фаза B: дистанция ---
        if dist and 100 < dist < 6000:
            noise, diff = vis_diff(sct, hwnd, lambda: wfloat(h, dist_addr, dist - 700), 1.0)
            after = rfloat(h, dist_addr)
            print(f"\n[TEST dist] {dist:.0f} -> {dist-700:.0f}: шум={noise:.2f} diff={diff:.2f} "
                  f"readback={after:.1f} => {'ВЛИЯЕТ' if diff > max(3*noise, noise+2) else 'нет эффекта'}")
            wfloat(h, dist_addr, dist)
            time.sleep(0.5)

        # --- фаза B2: кандидаты углов рядом ---
        for off, f in interesting:
            if off == DIST_OFFSET:
                continue
            addr = base + off
            kind = None
            if abs(f - 90.0) < 1.0:
                kind, test = "rot90deg", f + 45.0
            elif abs(f - math.pi / 2) < 0.03:
                kind, test = "rot90rad", f + 0.8
            elif abs(f - 304.0) < 2.0:
                kind, test = "aoa304deg", f + 25.0
            elif abs(f - (304 - 360)) < 2.0:
                kind, test = "aoa-56deg", f + 25.0
            elif abs(f - math.radians(304 - 360)) < 0.03:
                kind, test = "aoa-56rad", f + 0.45
            elif abs(f - 70.0) < 1.0:
                kind, test = "fov70deg", f + 30.0
            elif abs(f - math.radians(70)) < 0.02:
                kind, test = "fov70rad", f + 0.5
            if not kind:
                continue
            noise, diff = vis_diff(sct, hwnd, lambda a=addr, t=test: wfloat(h, a, t), 0.9)
            back = rfloat(h, addr)
            hit = diff > max(3 * noise, noise + 2)
            print(f"[TEST {kind}] +{off:#x} {f:.3f} -> {test:.3f}: шум={noise:.2f} "
                  f"diff={diff:.2f} readback={back:.3f} => {'ВЛИЯЕТ' if hit else 'нет'}")
            wfloat(h, addr, f)
            time.sleep(0.4)

    kernel32.CloseHandle(h)
    print("\nготово")


if __name__ == "__main__":
    main()
