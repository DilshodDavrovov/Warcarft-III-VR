# -*- coding: utf-8 -*-
"""Проверяет CameraSync (клавишный драйвер): подаём позу, смотрим diff кадров."""
import ctypes, ctypes.wintypes as wt, time, sys
import cv2, mss, numpy as np
sys.path.insert(0, r"d:\Games\Warcraft\vr")
from camera_sync import CameraSync

u = ctypes.windll.user32
try: ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception: pass

def hwnd(): return u.FindWindowW("Warcraft III", None) or u.FindWindowW(None, "Warcraft III")
def grab(sct, h):
    r = wt.RECT(); u.GetClientRect(h, ctypes.byref(r))
    p = wt.POINT(0,0); u.ClientToScreen(h, ctypes.byref(p))
    s = sct.grab({"left":p.x,"top":p.y,"width":r.right-r.left,"height":r.bottom-r.top})
    img = np.frombuffer(s.bgra,np.uint8).reshape(s.height,s.width,4)[:,:,:3]
    return cv2.cvtColor(cv2.resize(img,(320,180)),cv2.COLOR_BGR2GRAY).astype(np.int16)

def measure(sct, h, cs, yaw, pitch, label, secs=1.0):
    cs.set_pose(yaw, pitch)
    a = grab(sct,h); time.sleep(secs); b = grab(sct,h)
    diff = float(np.abs(b-a).mean())
    print(f"  {label:22s} yaw={yaw:+.2f} pitch={pitch:+.2f}: diff={diff:6.2f} held={cs.status()['held']}")
    cs.set_pose(0,0); time.sleep(0.6)
    return diff

def main():
    h = hwnd()
    if not h: raise SystemExit("no game window")
    u.SetForegroundWindow(h); time.sleep(0.4)
    sct = mss.mss()
    cs = CameraSync()
    cs.enable(); cs.set_pose(0,0); time.sleep(0.3)
    print("status:", cs.status())
    print("\n-- поворот (yaw) --")
    measure(sct,h,cs, 0.4, 0.0, "голова влево")
    measure(sct,h,cs,-0.4, 0.0, "голова вправо")
    print("-- наклон (pitch) --")
    measure(sct,h,cs, 0.0, 0.4, "голова вверх")
    measure(sct,h,cs, 0.0,-0.4, "голова вниз")
    print("-- мёртвая зона --")
    measure(sct,h,cs, 0.05, 0.0, "малый наклон головы")
    cs.disable(); time.sleep(0.3)
    print("после disable held:", cs.status()['held'])
    print("done")

if __name__ == "__main__":
    main()
