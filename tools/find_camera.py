# -*- coding: utf-8 -*-
"""
Дифференциальный поиск ЖИВЫХ полей камеры WC3 1.26 (метод Cheat Engine).

Идея: несколько раз поворачиваем/наклоняем камеру в известном направлении
и оставляем только те float-адреса, что меняются СОГЛАСОВАННО с движением
(монотонно в одну сторону, разворачиваются в другую). Шум и вершинные
буферы отсеиваются за 5-6 раундов.

Затем каждый выживший адрес проверяется записью: двигается ли камера и
«прилипает» ли значение (игра его не перезатирает).

Результат сохраняется в vr/tools/camera_addrs.json (смещения от game.dll
и «сырые» heap-адреса), чтобы драйвер мог их использовать/перепроверить.
"""

import ctypes
import ctypes.wintypes as wt
import json
import struct
import sys
import time
from pathlib import Path

import cv2
import mss
import numpy as np

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    pass

PROCESS_ALL = 0x0010 | 0x0020 | 0x0008 | 0x0400
TH32 = 0x08 | 0x10
MEM_COMMIT = 0x1000
WRITABLE = {0x04, 0x08, 0x40, 0x80}
VK = {"INS": 0x2D, "DEL": 0x2E, "PGUP": 0x21, "PGDN": 0x22}
EXT = set(VK.values())


class MBI(ctypes.Structure):
    _fields_ = [("BaseAddress", ctypes.c_size_t), ("AllocationBase", ctypes.c_size_t),
                ("AllocationProtect", wt.DWORD), ("PartitionId", wt.WORD),
                ("RegionSize", ctypes.c_size_t), ("State", wt.DWORD),
                ("Protect", wt.DWORD), ("Type", wt.DWORD)]


class MODULEENTRY32(ctypes.Structure):
    _fields_ = [("dwSize", wt.DWORD), ("th32ModuleID", wt.DWORD), ("th32ProcessID", wt.DWORD),
                ("GlblcntUsage", wt.DWORD), ("ProccntUsage", wt.DWORD),
                ("modBaseAddr", ctypes.POINTER(ctypes.c_byte)), ("modBaseSize", wt.DWORD),
                ("hModule", wt.HMODULE), ("szModule", ctypes.c_char * 256),
                ("szExePath", ctypes.c_char * 260)]


def attach():
    hwnd = user32.FindWindowW("Warcraft III", None) or user32.FindWindowW(None, "Warcraft III")
    if not hwnd:
        sys.exit("NO_WINDOW: запусти war3.exe -window и зайди в игру")
    pid = wt.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    h = kernel32.OpenProcess(PROCESS_ALL, False, pid.value)
    if not h:
        sys.exit(f"OPEN_FAIL {ctypes.get_last_error()} (запусти от администратора)")
    snap = kernel32.CreateToolhelp32Snapshot(TH32, pid.value)
    me = MODULEENTRY32(); me.dwSize = ctypes.sizeof(MODULEENTRY32)
    gbase = gsize = None
    if kernel32.Module32First(snap, ctypes.byref(me)):
        while True:
            if me.szModule.lower() == b"game.dll":
                gbase = ctypes.cast(me.modBaseAddr, ctypes.c_void_p).value
                gsize = me.modBaseSize
                break
            if not kernel32.Module32Next(snap, ctypes.byref(me)):
                break
    kernel32.CloseHandle(snap)
    if not gbase:
        sys.exit("NO_GAMEDLL")
    return hwnd, h, gbase, gsize


def regions(h):
    addr, out = 0, []
    mbi = MBI()
    while addr < 0x7FFF0000:
        if not kernel32.VirtualQueryEx(h, ctypes.c_void_p(addr), ctypes.byref(mbi), ctypes.sizeof(mbi)):
            break
        if mbi.State == MEM_COMMIT and (mbi.Protect & 0xFF) in WRITABLE and mbi.RegionSize < 0x8000000:
            out.append((mbi.BaseAddress, mbi.RegionSize))
        addr = mbi.BaseAddress + mbi.RegionSize
    return out


def read_region(h, base, size):
    buf = ctypes.create_string_buffer(size)
    got = ctypes.c_size_t()
    if not kernel32.ReadProcessMemory(h, ctypes.c_void_p(base), buf, size, ctypes.byref(got)):
        return None
    n = got.value & ~3
    return np.frombuffer(buf.raw[:n], dtype=np.float32).copy()


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
    buf = ctypes.create_string_buffer(4)
    got = ctypes.c_size_t()
    if not kernel32.ReadProcessMemory(h, ctypes.c_void_p(addr), buf, 4, ctypes.byref(got)):
        return None
    return struct.unpack("<f", buf.raw)[0]


class Screen:
    def __init__(self, hwnd):
        self.hwnd = hwnd
        self.sct = mss.mss()
    def gray(self):
        r = wt.RECT(); user32.GetClientRect(self.hwnd, ctypes.byref(r))
        p = wt.POINT(0, 0); user32.ClientToScreen(self.hwnd, ctypes.byref(p))
        s = self.sct.grab({"left": p.x, "top": p.y, "width": r.right - r.left, "height": r.bottom - r.top})
        img = np.frombuffer(s.bgra, np.uint8).reshape(s.height, s.width, 4)[:, :, :3]
        return cv2.cvtColor(cv2.resize(img, (320, 180)), cv2.COLOR_BGR2GRAY).astype(np.int16)


def press(vk, dur=0.5):
    sc = user32.MapVirtualKeyW(vk, 0)
    flag = 0x0001 if vk in EXT else 0
    t0 = time.time()
    while time.time() - t0 < dur:
        user32.keybd_event(vk, sc, flag, 0)
        time.sleep(0.03)
    user32.keybd_event(vk, sc, flag | 0x0002, 0)
    time.sleep(0.35)   # дать камере доехать (инерция)


def read_all(h, regs):
    out = {}
    for base, size in regs:
        a = read_region(h, base, size)
        if a is not None:
            out[base] = a
    return out


def idle_stable_mask(h, regs, rounds=3, tol=1e-4):
    """Маска адресов, НЕ меняющихся, пока ввода нет (убирает анимации/таймеры)."""
    prev = read_all(h, regs)
    mask = {b: np.ones(prev[b].shape, bool) for b in prev}
    for r in range(rounds):
        time.sleep(0.6)
        cur = read_all(h, regs)
        alive = 0
        for b in prev:
            c = cur.get(b)
            if c is None or c.shape != prev[b].shape:
                mask[b][:] = False
                continue
            with np.errstate(all="ignore"):
                d = c.astype(np.float64) - prev[b].astype(np.float64)
                stable = np.isfinite(c) & np.isfinite(prev[b]) & (np.abs(d) <= tol)
            mask[b] &= stable
            prev[b] = c
            alive += int(mask[b].sum())
        print(f"  idle-раунд {r+1}: стабильных ~{alive}")
    return mask, prev


def scan_axis(h, regs, name, key_fwd, key_bak, base_mask, base_vals, eps):
    """Среди idle-стабильных ищет монотонно реагирующие на вращение (с согласованной амплитудой)."""
    print(f"\n=== скан '{name}' ===")
    dirs = [(+1, key_fwd), (+1, key_fwd), (-1, key_bak), (+1, key_fwd), (-1, key_bak)]
    mask = {b: base_mask[b].copy() for b in base_mask}
    prev = {b: base_vals[b].copy() for b in base_vals}
    ksign = {b: None for b in prev}
    mag0 = {b: None for b in prev}

    for step, (d, vk) in enumerate(dirs):
        press(vk, 0.5)
        cur = read_all(h, regs)
        alive = 0
        for b in prev:
            c = cur.get(b)
            if c is None or c.shape != prev[b].shape:
                mask[b][:] = False
                continue
            with np.errstate(all="ignore"):
                delta = c.astype(np.float64) - prev[b].astype(np.float64)
                ad = np.abs(delta)
                moved = np.isfinite(delta) & (ad > eps) & (ad < 1000.0)
                sgn = np.sign(delta)
            if ksign[b] is None:
                mask[b] &= moved
                ksign[b] = (sgn * d)
                mag0[b] = ad
            else:
                consistent = moved & (sgn == (ksign[b] * d)) \
                    & (ad > 0.35 * mag0[b]) & (ad < 3.0 * mag0[b])
                mask[b] &= consistent
            prev[b] = c
            alive += int(mask[b].sum())
        print(f"  раунд {step+1} (dir {'+' if d>0 else '-'}): выживших ~{alive}")

    survivors = []
    for b in prev:
        for i in np.where(mask[b])[0]:
            survivors.append((b + 4 * int(i), float(prev[b][i])))
    return survivors


_size_cache = {}
def size_of(regs, base):
    if not _size_cache:
        _size_cache.update({b: s for b, s in regs})
    return _size_cache[base]


def write_test(h, screen, addr, val, name):
    """Пишем val+delta, проверяем движение камеры и «прилипание»."""
    delta = 0.5 if abs(val) < 10 else 40.0   # рад vs град эвристика
    a = screen.gray(); time.sleep(0.25); b = screen.gray()
    noise = float(np.abs(b - a).mean())
    wfloat(h, addr, val + delta)
    time.sleep(0.4)
    c = screen.gray()
    diff = float(np.abs(c - b).mean())
    back = rfloat(h, addr)
    sticky = back is not None and abs(back - (val + delta)) < abs(delta) * 0.5 + 0.5
    wfloat(h, addr, val)
    time.sleep(0.3)
    moves = diff > max(3 * noise, noise + 2)
    return moves, sticky, diff, noise, back


def main():
    hwnd, h, gbase, gsize = attach()
    user32.SetForegroundWindow(hwnd); time.sleep(0.5)
    print(f"game.dll {gbase:#x} (+{gsize:#x})")
    screen = Screen(hwnd)
    regs = regions(h)
    print(f"писчих регионов: {len(regs)}, всего {sum(s for _,s in regs)/1e6:.0f} МБ")

    result = {"game_dll_base": gbase, "game_dll_size": gsize, "axes": {}}

    print("\n=== idle-стабильность (не трогаем ввод) ===")
    base_mask, base_vals = idle_stable_mask(h, regs)

    for axis, kf, kb, eps in [("yaw", VK["INS"], VK["DEL"], 5e-3),
                              ("pitch", VK["PGDN"], VK["PGUP"], 5e-3)]:
        survivors = scan_axis(h, regs, axis, kf, kb, base_mask, base_vals, eps)
        print(f"  кандидатов после скана: {len(survivors)}")
        survivors.sort(key=lambda t: abs(t[1]))   # разумные углы вперёд
        confirmed = []
        for addr, val in survivors[:120]:
            moves, sticky, diff, noise, back = write_test(h, screen, addr, val, axis)
            in_gd = gbase <= addr < gbase + gsize
            src = f"game.dll+{addr-gbase:#x}" if in_gd else f"heap {addr:#x}"
            tag = "★УПРАВЛЯЕТ" if (moves and sticky) else ("двигает" if moves else "-")
            if moves:
                print(f"  {src:24s} val={val:9.4f} diff={diff:5.1f}(шум{noise:4.1f}) sticky={sticky} {tag}")
            if moves and sticky:
                confirmed.append({"addr": addr, "offset_from_gamedll": addr - gbase if in_gd else None,
                                  "in_game_dll": in_gd, "value": val})
        result["axes"][axis] = confirmed
        print(f"  >> управляющих адресов для {axis}: {len(confirmed)}")

    out = Path(r"d:\Games\Warcraft\vr\tools\camera_addrs.json")
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"\nсохранено: {out}")
    kernel32.CloseHandle(h)


if __name__ == "__main__":
    main()
