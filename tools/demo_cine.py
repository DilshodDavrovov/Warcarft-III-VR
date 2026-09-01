# -*- coding: utf-8 -*-
"""
ДЕМО через кинематографическую камеру (свободную): 360° поворот + наклон в
вид от первого лица + осмотр. Управление через CineCameraSync (резидентный
поток + FUN_6f305a60). Кадры форсятся тычком Insert (кинематографич. камера
перебивает геймплейную), пишутся в MP4.
"""
import sys, time, math, struct, ctypes
import ctypes.wintypes as wt
import mss, numpy as np, cv2
sys.path.insert(0, r"d:\Games\Warcraft\vr")
import cam_cine_driver as C
from cam_cine_driver import CineCameraSync
u=ctypes.windll.user32; k=ctypes.windll.kernel32
try: ctypes.windll.shcore.SetProcessDpiAwareness(2)
except: pass
h=u.FindWindowW("Warcraft III",None)
OUT=r"d:\Games\Warcraft\vr\demo_camera.mp4"
def force_fg():
    fg=u.GetForegroundWindow(); t=u.GetWindowThreadProcessId(fg,None); c=k.GetCurrentThreadId()
    u.AttachThreadInput(t,c,True); u.BringWindowToTop(h); u.SetForegroundWindow(h); u.AttachThreadInput(t,c,False)
def tap(vk,dur=0.05):
    sc=u.MapVirtualKeyW(vk,0); t0=time.time()
    while time.time()-t0<dur: u.keybd_event(vk,sc,0x0001,0); time.sleep(0.015)
    u.keybd_event(vk,sc,0x0001|0x0002,0)
def rect():
    r=wt.RECT(); u.GetClientRect(h,ctypes.byref(r)); p=wt.POINT(0,0); u.ClientToScreen(h,ctypes.byref(p))
    return p.x,p.y,r.right,r.bottom
def main():
    force_fg(); time.sleep(0.3)
    cs=CineCameraSync(); cs.enable(); time.sleep(1.3)
    print("status:",cs.status())
    ph=cs._ph; ROT=cs._ROT; AOA=cs._AOA; DIST=cs._DIST
    def wf(a,v):
        n=ctypes.c_size_t(); k.WriteProcessMemory(ph,ctypes.c_void_p(a),struct.pack("<f",v),4,ctypes.byref(n))
    x,y,ww,hh=rect()
    vw=cv2.VideoWriter(OUT,cv2.VideoWriter_fourcc(*"mp4v"),15,(ww,hh))
    sct=mss.mss()
    def frame(rot,aoa,dist,label):
        wf(ROT,rot); wf(AOA,aoa); wf(DIST,dist); time.sleep(0.02)
        force_fg(); tap(0x2D); time.sleep(0.05)
        sh=sct.grab({"left":x,"top":y,"width":ww,"height":hh})
        img=np.frombuffer(sh.bgra,np.uint8).reshape(sh.height,sh.width,4)[:,:,:3].copy()
        if label: cv2.putText(img,label,(30,hh-40),cv2.FONT_HERSHEY_SIMPLEX,1.1,(0,255,255),3)
        vw.write(img)
    ISO=340.0     # изометрический наклон (обзор)
    FPV=250.0     # низкий драматичный угол (иммерсивный)
    OVER=1650.0   # дистанция обзора
    NEAR=750.0    # дистанция иммерсии
    def lerp(a,b,t): return a+(b-a)*t
    # ФАЗА 1: обзор, полный оборот 360
    for i in range(37): frame(90+i*10, ISO, OVER, "FREE 360 rotation")
    # ФАЗА 2: наклон в вид от первого лица + приближение
    for i in range(16):
        t=i/15.0; frame(90, lerp(ISO,FPV,t), lerp(OVER,NEAR,t), "tilt to first-person")
    # ФАЗА 3: осмотр от первого лица (поворот на горизонте)
    for i in range(37): frame(90+i*10, FPV, NEAR, "first-person look-around")
    # ФАЗА 4: назад к обзору
    for i in range(12):
        t=i/11.0; frame(90, lerp(FPV,ISO,t), lerp(NEAR,OVER,t), "back to overview")
    vw.release()
    cs.set_pose(0,0); cs.disable()
    print("saved",OUT)
if __name__=="__main__": main()
