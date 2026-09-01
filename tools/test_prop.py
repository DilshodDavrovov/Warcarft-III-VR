# -*- coding: utf-8 -*-
"""Проверка пропорционального клавишного драйвера: разный 'газ' по углу головы."""
import ctypes, ctypes.wintypes as wt, time, sys, math
import cv2, mss, numpy as np
sys.path.insert(0, r"d:\Games\Warcraft\vr")
from camera_sync import CameraSync

u=ctypes.windll.user32
try: ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception: pass
def hwnd(): return u.FindWindowW("Warcraft III",None) or u.FindWindowW(None,"Warcraft III")
def grab(sct,h):
    r=wt.RECT(); u.GetClientRect(h,ctypes.byref(r)); p=wt.POINT(0,0); u.ClientToScreen(h,ctypes.byref(p))
    s=sct.grab({"left":p.x,"top":p.y,"width":r.right-r.left,"height":r.bottom-r.top})
    return cv2.cvtColor(cv2.resize(np.frombuffer(s.bgra,np.uint8).reshape(s.height,s.width,4)[:,:,:3],(320,180)),cv2.COLOR_BGR2GRAY).astype(np.int16)

def run(cs,sct,h,yaw_deg,pitch_deg,label,secs=1.6):
    a=grab(sct,h); keys=set(); t0=time.time()
    while time.time()-t0<secs:
        cs.set_pose(math.radians(yaw_deg),math.radians(pitch_deg))
        for kk in cs.status()['held']: keys.add(kk)
        time.sleep(0.03)
    b=grab(sct,h)
    print(f"  {label:24s} diff={float(np.abs(b-a).mean()):6.2f} keys={sorted(keys)}")
    cs.set_pose(0,0); time.sleep(0.7)

def main():
    h=hwnd()
    if not h: raise SystemExit("no game")
    if u.IsIconic(h): u.ShowWindow(h,9); time.sleep(0.4)
    u.SetForegroundWindow(h); time.sleep(0.4)
    sct=mss.mss(); cs=CameraSync(); cs.enable(); time.sleep(0.2)
    print("пропорциональный драйвер (больше угол головы = быстрее вращение):")
    run(cs,sct,h,  8,0,"голова вправо чуть (8°)")
    run(cs,sct,h, 35,0,"голова вправо сильно (35°)")
    run(cs,sct,h,-35,0,"голова влево сильно (35°)")
    run(cs,sct,h,  0,25,"голова вверх (25°)")
    run(cs,sct,h,  0,-25,"голова вниз (25°)")
    run(cs,sct,h,  3,0,"в мёртвой зоне (3°)")
    cs.disable()
    print("held после disable:", cs.status()['held'])

if __name__=="__main__":
    main()
