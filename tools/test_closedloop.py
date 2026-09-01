# -*- coding: utf-8 -*-
"""Проверяет closed-loop драйвер: цель по голове -> камера доворачивается и стоит."""
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

def drive(cs,sct,h,yaw_rad,pitch_rad,label,secs=2.5):
    a=grab(sct,h); t0=time.time()
    while time.time()-t0<secs:
        cs.set_pose(yaw_rad,pitch_rad); time.sleep(0.03)
    b=grab(sct,h)
    st=cs.status()
    diff=float(np.abs(b-a).mean())
    print(f"  {label:20s} цель yaw={math.degrees(yaw_rad):+5.0f}° pitch={math.degrees(pitch_rad):+4.0f}° | "
          f"est_yaw={st['est_yaw']:+6.1f} est_pitch={st['est_pitch']:+5.1f} held={st['held']} diff={diff:.1f}")

def main():
    h=hwnd()
    if not h: raise SystemExit("no game window")
    if u.IsIconic(h): u.ShowWindow(h,9); time.sleep(0.4)
    u.SetForegroundWindow(h); time.sleep(0.4)
    sct=mss.mss(); cs=CameraSync(); cs.enable(); time.sleep(0.2)
    print("closed-loop тест (камера должна доворачиваться к цели и вставать):")
    drive(cs,sct,h, math.radians(40),0,"голова вправо 40°")
    drive(cs,sct,h, 0,0,             "голова прямо (возврат)")
    drive(cs,sct,h, math.radians(-40),0,"голова влево 40°")
    drive(cs,sct,h, 0,0,             "голова прямо (возврат)")
    drive(cs,sct,h, 0, math.radians(25),"голова вверх 25°")
    drive(cs,sct,h, 0, 0,            "голова прямо (возврат)")
    cs.disable()
    print("done, held after disable:", cs.status()['held'])

if __name__=="__main__":
    main()
