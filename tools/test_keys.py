# -*- coding: utf-8 -*-
"""Проверяет, какие клавиши реально двигают камеру WC3 (визуальный diff)."""
import ctypes, ctypes.wintypes as wt, time
import cv2, mss, numpy as np

u = ctypes.windll.user32
try: ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception: pass

KEYS = {
    "Insert(rot L)": 0x2D, "Delete(rot R)": 0x2E,
    "PageUp(AoA+)": 0x21, "PageDown(AoA-)": 0x22,
    "Home": 0x24, "End": 0x23,
    "Up(pan)": 0x26, "Down(pan)": 0x28, "Left(pan)": 0x25, "Right(pan)": 0x27,
}
EXT = {0x2D,0x2E,0x21,0x22,0x24,0x23,0x26,0x28,0x25,0x27}


def hwnd():
    return u.FindWindowW("Warcraft III", None) or u.FindWindowW(None, "Warcraft III")


def grab(sct, h):
    r = wt.RECT(); u.GetClientRect(h, ctypes.byref(r))
    p = wt.POINT(0,0); u.ClientToScreen(h, ctypes.byref(p))
    s = sct.grab({"left":p.x,"top":p.y,"width":r.right-r.left,"height":r.bottom-r.top})
    img = np.frombuffer(s.bgra,np.uint8).reshape(s.height,s.width,4)[:,:,:3]
    g = cv2.cvtColor(cv2.resize(img,(320,180),interpolation=cv2.INTER_AREA),cv2.COLOR_BGR2GRAY)
    return g.astype(np.int16)


def press(vk, dur):
    sc = u.MapVirtualKeyW(vk, 0)
    flag = 0x0001 if vk in EXT else 0
    t0 = time.time()
    while time.time()-t0 < dur:
        u.keybd_event(vk, sc, flag, 0)
        time.sleep(0.03)
    u.keybd_event(vk, sc, flag|0x0002, 0)


def main():
    h = hwnd()
    if not h: raise SystemExit("no window")
    u.SetForegroundWindow(h); time.sleep(0.5)
    sct = mss.mss()
    print(f"{'key':16s} {'diff':>8s}  вывод")
    for name, vk in KEYS.items():
        a = grab(sct,h); time.sleep(0.25); b = grab(sct,h)
        noise = float(np.abs(b-a).mean())
        press(vk, 0.7)
        time.sleep(0.15)
        c = grab(sct,h)
        diff = float(np.abs(c-b).mean())
        verdict = "ДВИГАЕТ" if diff > max(3*noise, noise+2) else "-"
        print(f"{name:16s} {diff:8.2f}  (шум {noise:.2f}) {verdict}")
        # вернуть парной клавишей где возможно
        time.sleep(0.2)
    print("done")


if __name__ == "__main__":
    main()
