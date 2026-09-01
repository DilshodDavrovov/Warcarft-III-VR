# -*- coding: utf-8 -*-
"""Читает память war3 вокруг game.dll+0x93645C и печатает float-поля камеры."""
import ctypes
import ctypes.wintypes as wt
import struct
import sys

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

PROCESS_VM_READ = 0x0010
PROCESS_QUERY_INFORMATION = 0x0400
TH32CS_SNAPMODULE = 0x08
TH32CS_SNAPMODULE32 = 0x10

DIST_OFFSET = 0x93645C  # camera distance, float, default 1650 (WC3 1.26.0.6401)


class MODULEENTRY32(ctypes.Structure):
    _fields_ = [
        ("dwSize", wt.DWORD), ("th32ModuleID", wt.DWORD), ("th32ProcessID", wt.DWORD),
        ("GlblcntUsage", wt.DWORD), ("ProccntUsage", wt.DWORD),
        ("modBaseAddr", ctypes.POINTER(ctypes.c_byte)), ("modBaseSize", wt.DWORD),
        ("hModule", wt.HMODULE), ("szModule", ctypes.c_char * 256),
        ("szExePath", ctypes.c_char * 260),
    ]


def game_pid():
    hwnd = user32.FindWindowW("Warcraft III", None)
    if not hwnd:
        sys.exit("Окно игры не найдено — запусти Warcraft III")
    pid = wt.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def module_base(pid, name=b"game.dll"):
    snap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPMODULE | TH32CS_SNAPMODULE32, pid)
    if snap == -1:
        sys.exit("Не удалось получить список модулей (запусти от администратора)")
    me = MODULEENTRY32()
    me.dwSize = ctypes.sizeof(MODULEENTRY32)
    base = None
    if kernel32.Module32First(snap, ctypes.byref(me)):
        while True:
            if me.szModule.lower() == name:
                base = ctypes.cast(me.modBaseAddr, ctypes.c_void_p).value
                break
            if not kernel32.Module32Next(snap, ctypes.byref(me)):
                break
    kernel32.CloseHandle(snap)
    if base is None:
        sys.exit("game.dll не найден в процессе")
    return base


def read_mem(h, addr, size):
    buf = ctypes.create_string_buffer(size)
    got = ctypes.c_size_t()
    if not kernel32.ReadProcessMemory(h, ctypes.c_void_p(addr), buf, size, ctypes.byref(got)):
        sys.exit(f"ReadProcessMemory failed @ {addr:#x} (err {ctypes.get_last_error()})")
    return buf.raw


def main():
    pid = game_pid()
    h = kernel32.OpenProcess(PROCESS_VM_READ | PROCESS_QUERY_INFORMATION, False, pid)
    if not h:
        sys.exit("OpenProcess failed — запусти от администратора")
    base = module_base(pid)
    print(f"PID={pid}  game.dll base = {base:#x}")
    start = base + DIST_OFFSET - 0x80
    data = read_mem(h, start, 0x180)
    print(f"\nfloat-поля вокруг game.dll+{DIST_OFFSET:#x} (дистанция должна быть ~1650):\n")
    for i in range(0, len(data), 4):
        off = DIST_OFFSET - 0x80 + i
        (f,) = struct.unpack_from("<f", data, i)
        (d,) = struct.unpack_from("<I", data, i)
        mark = "  <== DISTANCE" if off == DIST_OFFSET else ""
        if abs(f) > 1e-6 and abs(f) < 1e7:
            print(f"  game.dll+{off:#08x}  float={f:12.4f}  raw={d:#010x}{mark}")
        elif mark:
            print(f"  game.dll+{off:#08x}  float={f!r}  raw={d:#010x}{mark}")
    kernel32.CloseHandle(h)


if __name__ == "__main__":
    main()
