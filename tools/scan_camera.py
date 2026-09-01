# -*- coding: utf-8 -*-
"""
Поиск ЖИВОЙ структуры камеры WC3 1.26 методом diff-скана:
  1) слепок памяти: все float ~ 90 (или pi/2)
  2) зажимаем Insert (камера крутится влево), два контрольных чтения
  3) кандидаты = поехавшие согласованно значения
  4) каждому кандидату — write-тест с визуальной проверкой (diff кадров)
  5) вокруг победителя печатаем структуру + ищем статический указатель на неё
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

PROCESS_ALL = 0x0010 | 0x0020 | 0x0008 | 0x0400
TH32 = 0x08 | 0x10
VK_INSERT, VK_DELETE = 0x2D, 0x2E
WM_KEYDOWN, WM_KEYUP = 0x100, 0x101
MEM_COMMIT = 0x1000
WRITABLE = {0x04, 0x08, 0x40, 0x80}  # RW, WRITECOPY, EXEC_RW, EXEC_WRITECOPY


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
        sys.exit("NO_WINDOW")
    pid = wt.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    h = kernel32.OpenProcess(PROCESS_ALL, False, pid.value)
    if not h:
        sys.exit(f"OPEN_FAIL {ctypes.get_last_error()}")
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
    return hwnd, h, gbase, gsize


def regions(h):
    addr, out = 0, []
    mbi = MBI()
    while addr < 0x7FFF0000:
        if not kernel32.VirtualQueryEx(h, ctypes.c_void_p(addr), ctypes.byref(mbi),
                                       ctypes.sizeof(mbi)):
            break
        if mbi.State == MEM_COMMIT and (mbi.Protect & 0xFF) in WRITABLE \
           and mbi.RegionSize < 0x8000000:
            out.append((mbi.BaseAddress, mbi.RegionSize))
        addr = mbi.BaseAddress + mbi.RegionSize
    return out


def rmem(h, addr, size):
    buf = ctypes.create_string_buffer(size)
    got = ctypes.c_size_t()
    if not kernel32.ReadProcessMemory(h, ctypes.c_void_p(addr), buf, size, ctypes.byref(got)):
        return None
    return buf.raw[:got.value]


def wfloat(h, addr, value):
    data = struct.pack("<f", value)
    n = ctypes.c_size_t()
    return bool(kernel32.WriteProcessMemory(h, ctypes.c_void_p(addr), data, 4, ctypes.byref(n)))


def rfloat(h, addr):
    d = rmem(h, addr, 4)
    return struct.unpack("<f", d)[0] if d and len(d) == 4 else None


def grab(sct, hwnd):
    rect = wt.RECT(); user32.GetClientRect(hwnd, ctypes.byref(rect))
    pt = wt.POINT(0, 0); user32.ClientToScreen(hwnd, ctypes.byref(pt))
    shot = sct.grab({"left": pt.x, "top": pt.y,
                     "width": rect.right - rect.left, "height": rect.bottom - rect.top})
    img = np.frombuffer(shot.bgra, np.uint8).reshape(shot.height, shot.width, 4)[:, :, :3]
    small = cv2.resize(img, (320, 180), interpolation=cv2.INTER_AREA)
    return cv2.cvtColor(small, cv2.COLOR_BGR2GRAY).astype(np.int16)


class KeyHolder:
    """Зажимает клавишу: шлёт повторные WM_KEYDOWN, потом WM_KEYUP."""
    def __init__(self, hwnd, vk):
        self.hwnd, self.vk = hwnd, vk
        self.lparam = 0x01500001 if vk == VK_INSERT else 0x01530001  # scancode ext
    def down(self):
        user32.PostMessageW(self.hwnd, WM_KEYDOWN, self.vk, self.lparam)
    def up(self):
        user32.PostMessageW(self.hwnd, WM_KEYUP, self.vk, self.lparam | 0xC0000000)
    def hold(self, seconds):
        t0 = time.time()
        while time.time() - t0 < seconds:
            self.down()
            time.sleep(0.03)
        self.up()


def main():
    hwnd, h, gbase, gsize = attach()
    print(f"game.dll {gbase:#x}..{gbase + gsize:#x}")
    sct = mss.mss()

    # ---------- фаза 1: слепок "всё, что похоже на 90 градусов" ----------
    regs = regions(h)
    total = sum(s for _, s in regs)
    print(f"регионов: {len(regs)}, всего {total/1e6:.0f} МБ")

    cand = []  # (addr, initial_value, 'deg'|'rad')
    for base, size in regs:
        data = rmem(h, base, size)
        if not data or len(data) < 4:
            continue
        arr = np.frombuffer(data[:len(data) & ~3], dtype=np.float32)
        deg_idx = np.where(np.abs(arr - 90.0) < 2.0)[0]
        rad_idx = np.where(np.abs(arr - math.pi / 2) < 0.04)[0]
        for i in deg_idx:
            cand.append((base + 4 * int(i), float(arr[i]), "deg"))
        for i in rad_idx:
            cand.append((base + 4 * int(i), float(arr[i]), "rad"))
    print(f"кандидатов ~90: {len(cand)}")

    # ---------- фаза 2: крутим камеру и смотрим, кто поехал ----------
    key = KeyHolder(hwnd, VK_INSERT)
    before = grab(sct, hwnd)
    key.hold(0.9)
    time.sleep(0.1)
    mid = grab(sct, hwnd)
    rot_visual = float(np.abs(mid - before).mean())
    print(f"визуальный сдвиг от Insert: {rot_visual:.2f} (шум ~0.35)")
    if rot_visual < 1.5:
        print("!! Insert через PostMessage не подействовал — пробую с фокусом")
        user32.SetForegroundWindow(hwnd)
        time.sleep(0.4)
        before = grab(sct, hwnd)
        user32.keybd_event(VK_INSERT, 0x52, 0, 0)
        time.sleep(0.9)
        user32.keybd_event(VK_INSERT, 0x52, 2, 0)
        mid = grab(sct, hwnd)
        rot_visual = float(np.abs(mid - before).mean())
        print(f"визуальный сдвиг (keybd_event): {rot_visual:.2f}")
        if rot_visual < 1.5:
            sys.exit("ROTATE_FAIL: не удалось повернуть камеру программно")

    moved = []
    for addr, v0, unit in cand:
        v1 = rfloat(h, addr)
        if v1 is None:
            continue
        d = abs(v1 - v0)
        if unit == "deg" and 1.0 < d < 200.0:
            moved.append((addr, v0, v1, unit))
        elif unit == "rad" and 0.02 < d < 4.0:
            moved.append((addr, v0, v1, unit))
    print(f"поехали после поворота: {len(moved)}")
    for a, v0, v1, u in moved[:40]:
        src = f"game.dll+{a - gbase:#x}" if gbase <= a < gbase + gsize else f"{a:#x} (heap)"
        print(f"  {src:28s} {u}: {v0:.4f} -> {v1:.4f}")

    # ---------- фаза 3: write-тест кандидатов ----------
    print("\n=== write-тесты ===")
    hits = []
    for addr, v0, v1, unit in moved[:40]:
        cur = rfloat(h, addr)
        if cur is None:
            continue
        test = cur + (40.0 if unit == "deg" else 0.7)
        a = grab(sct, hwnd); time.sleep(0.25); b = grab(sct, hwnd)
        noise = float(np.abs(b - a).mean())
        wfloat(h, addr, test)
        time.sleep(0.45)
        c = grab(sct, hwnd)
        diff = float(np.abs(c - b).mean())
        back = rfloat(h, addr)
        sticky = back is not None and abs(back - test) < 1.0
        hit = diff > max(3 * noise, noise + 1.5)
        src = f"game.dll+{addr - gbase:#x}" if gbase <= addr < gbase + gsize else f"{addr:#x} (heap)"
        print(f"  {src:28s} {unit} write {cur:.2f}->{test:.2f}: diff={diff:.2f} "
              f"(шум {noise:.2f}) sticky={sticky} => {'ВЛИЯЕТ' if hit else '-'}")
        wfloat(h, addr, cur)
        time.sleep(0.3)
        if hit:
            hits.append((addr, unit, sticky))

    # ---------- фаза 4: структура вокруг победителя + статический указатель ----------
    for addr, unit, sticky in hits:
        print(f"\n=== структура вокруг {addr:#x} ({unit}, sticky={sticky}) ===")
        blk = rmem(h, addr - 0x80, 0x120)
        if blk:
            for i in range(0, len(blk) - 3, 4):
                (f,) = struct.unpack_from("<f", blk, i)
                off = i - 0x80
                if 1e-6 < abs(f) < 1e7:
                    print(f"  rot{off:+#05x}  {f:14.4f}")
        # статический указатель в game.dll на окрестность структуры
        lo, hi = addr - 0x400, addr + 4
        gdata = rmem(h, gbase, gsize)
        if gdata:
            garr = np.frombuffer(gdata[:len(gdata) & ~3], dtype=np.uint32)
            idx = np.where((garr >= lo) & (garr <= hi))[0]
            for i in idx[:10]:
                ptr = int(garr[i])
                print(f"  static ptr: game.dll+{4*int(i):#x} -> {ptr:#x} "
                      f"(struct = ptr+{addr - ptr:#x})")

    # вернуть камеру вправо обратно
    KeyHolder(hwnd, VK_DELETE).hold(0.9)
    kernel32.CloseHandle(h)
    print("\nготово")


if __name__ == "__main__":
    main()
