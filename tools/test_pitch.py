# -*- coding: utf-8 -*-
"""Чистая проверка наклона: держим позу свежей всё время замера."""
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

def hold(sct,h,cs,yaw,pitch,label,secs=1.2):
    a=grab(sct,h); t0=time.time(); held_seen=set()
    while time.time()-t0<secs:
        cs.set_pose(yaw,pitch)          # держим позу свежей
        for k in cs.status()['held']: held_seen.add(k)
        time.sleep(0.03)
    b=grab(sct,h)
    print(f"  {label:16s}: diff={float(np.abs(b-a).mean()):6.2f} keys={sorted(held_seen)}")
    cs.set_pose(0,0); time.sleep(0.8)

def main():
    h=hwnd()
    if not h: raise SystemExit("no window")
    u.SetForegroundWindow(h); time.sleep(0.4)
    sct=mss.mss(); cs=CameraSync(); cs.enable(); time.sleep(0.3)
    # сначала вернём AoA к среднему: наклон вниз, потом меряем оба направления
    hold(sct,h,cs, 0.0, 0.4, "вверх #1")
    hold(sct,h,cs, 0.0,-0.4, "вниз #1")
    hold(sct,h,cs, 0.0, 0.4, "вверх #2")
    hold(sct,h,cs, 0.0,-0.4, "вниз #2")
    hold(sct,h,cs, 0.5, 0.0, "поворот влево")
    cs.disable()
    print("done")

if __name__=="__main__":
    main()
