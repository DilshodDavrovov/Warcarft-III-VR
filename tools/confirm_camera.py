# -*- coding: utf-8 -*-
"""
Уточняет, какой из кандидатов — настоящая камера:
  1) глобальный тест: запись должна менять ВЕСЬ кадр (поворот вида), а не
     локальный кусок (вершинный буфер);
  2) дамп окрестности: у настоящей структуры камеры рядом лежат дистанция
     (~1600-1700), координаты цели (крупные мировые float) и угол наклона.
"""
import ctypes, ctypes.wintypes as wt, json, struct, time
from pathlib import Path
import cv2, mss, numpy as np

u = ctypes.windll.user32
k = ctypes.windll.kernel32
try: ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception: pass
PROCESS_ALL = 0x0010|0x0020|0x0008|0x0400


def attach():
    h = u.FindWindowW("Warcraft III", None) or u.FindWindowW(None, "Warcraft III")
    if not h: raise SystemExit("no window")
    pid = wt.DWORD(); u.GetWindowThreadProcessId(h, ctypes.byref(pid))
    return h, k.OpenProcess(PROCESS_ALL, False, pid.value)

def rmem(h, a, n):
    b = ctypes.create_string_buffer(n); g = ctypes.c_size_t()
    if not k.ReadProcessMemory(h, ctypes.c_void_p(a), b, n, ctypes.byref(g)): return None
    return b.raw[:g.value]
def rfloat(h, a):
    d = rmem(h, a, 4); return struct.unpack("<f", d)[0] if d and len(d)==4 else None
def wfloat(h, a, v):
    d = struct.pack("<f", v); n = ctypes.c_size_t()
    ok = k.WriteProcessMemory(h, ctypes.c_void_p(a), d, 4, ctypes.byref(n))
    if not ok:
        old = wt.DWORD(); k.VirtualProtectEx(h, ctypes.c_void_p(a), 4, 0x40, ctypes.byref(old))
        ok = k.WriteProcessMemory(h, ctypes.c_void_p(a), d, 4, ctypes.byref(n))
    return bool(ok)

class Screen:
    def __init__(s, h): s.h=h; s.sct=mss.mss()
    def rect(s):
        for _ in range(20):
            r=wt.RECT(); u.GetClientRect(s.h,ctypes.byref(r))
            p=wt.POINT(0,0); u.ClientToScreen(s.h,ctypes.byref(p))
            if r.right-r.left > 8 and r.bottom-r.top > 8:
                return {"left":p.x,"top":p.y,"width":r.right-r.left,"height":r.bottom-r.top}
            time.sleep(0.1)
        raise SystemExit("окно игры без размера (свёрнуто?)")
    def gray(s):
        sh=s.sct.grab(s.rect())
        img=np.frombuffer(sh.bgra,np.uint8).reshape(sh.height,sh.width,4)[:,:,:3]
        return cv2.cvtColor(cv2.resize(img,(320,180)),cv2.COLOR_BGR2GRAY).astype(np.int16)

def global_test(h, screen, addr):
    """Возвращает (mean_diff, доля_изменённых_пикселей, sticky, back)."""
    v = rfloat(h, addr)
    if v is None: return None
    delta = 0.6 if abs(v) < 10 else 45.0
    b = screen.gray()
    wfloat(h, addr, v + delta); time.sleep(0.4)
    c = screen.gray()
    back = rfloat(h, addr)
    wfloat(h, addr, v); time.sleep(0.3)
    d = np.abs(c - b)
    frac = float((d > 8).mean())
    sticky = back is not None and abs(back - (v+delta)) < abs(delta)*0.5 + 0.5
    return float(d.mean()), frac, sticky, v, back

def main():
    h, ph = attach()
    time.sleep(0.3)
    screen = Screen(h)
    data = json.loads(Path(r"d:\Games\Warcraft\vr\tools\camera_addrs.json").read_text(encoding="utf-8"))
    gbase = data["game_dll_base"]
    yaw_cands = data["axes"].get("yaw", [])
    print(f"кандидатов yaw: {len(yaw_cands)}\n")
    ranked = []
    for c in yaw_cands:
        addr = c["addr"]
        res = global_test(ph, screen, addr)
        if not res: continue
        mean_d, frac, sticky, v, back = res
        glob = "ГЛОБАЛЬНО" if frac > 0.25 else "локально"
        print(f"  {addr:#x} val={v:.4f} mean={mean_d:5.1f} frac={frac:.2f} sticky={sticky} -> {glob}")
        ranked.append((frac, mean_d, addr, v))
    ranked.sort(reverse=True)
    print("\n=== окрестности лучших (ищем дистанцию ~1650 и координаты цели) ===")
    for frac, mean_d, addr, v in ranked[:4]:
        print(f"\n-- {addr:#x} (frac={frac:.2f}, val={v:.4f}) --")
        blk = rmem(ph, addr - 0x40, 0x90)
        if blk:
            for i in range(0, len(blk)-3, 4):
                (f,) = struct.unpack_from("<f", blk, i)
                (iv,) = struct.unpack_from("<i", blk, i)
                off = i - 0x40
                mk = " <== yaw" if off == 0 else ""
                if abs(f) > 1e-6 and abs(f) < 1e9:
                    note = ""
                    if 1000 < abs(f) < 6000: note = "  ? дистанция/координата"
                    if 200 < abs(f) < 360: note = "  ? угол(град)"
                    print(f"    +{off:+#05x}  float={f:12.3f}{mk}{note}")
    k.CloseHandle(ph)

if __name__ == "__main__":
    main()
