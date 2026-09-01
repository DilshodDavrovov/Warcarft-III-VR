# -*- coding: utf-8 -*-
"""
ДЕМО режима ФИКСИРОВАННЫЙ ГЛАЗ (истинный поворот взгляда, глаз неподвижен):
- пан камеры на базу (освещённая зона),
- ПОЛНЫЙ оборот 360 по горизонтали (видно "то, что за спиной"),
- наклон вверх/вниз, свободный осмотр.
Эмулируем позу головы через CineCameraSync.set_pose(); драйвер держит глаз
на месте и поворачивает направление взгляда (SetPos+rotation+aoa+dist).
Пишем MP4.
"""
import sys, time, math, struct, ctypes
import ctypes.wintypes as wt
import mss, numpy as np, cv2
sys.path.insert(0, r"d:\Games\Warcraft\vr")
from cam_cine_driver import CineCameraSync
u=ctypes.windll.user32; k=ctypes.windll.kernel32
k.VirtualAllocEx.restype=ctypes.c_void_p
k.VirtualAllocEx.argtypes=[wt.HANDLE,ctypes.c_void_p,ctypes.c_size_t,wt.DWORD,wt.DWORD]
k.CreateRemoteThread.restype=wt.HANDLE
try: ctypes.windll.shcore.SetProcessDpiAwareness(2)
except: pass
OUT=r"d:\Games\Warcraft\vr\demo_fixeye.mp4"
KEY=r"C:\Users\User\AppData\Local\Temp\claude\d--Games-Warcraft\68b4b6b4-84ac-41a2-a57c-c8299edcfdef\scratchpad"
PAN_TO=(3111.0,-6600.0)   # база (освещённая зона), чуть севернее старта
h=u.FindWindowW("Warcraft III",None)
pid=wt.DWORD(); u.GetWindowThreadProcessId(h,ctypes.byref(pid)); ph=k.OpenProcess(0x043A,False,pid.value)
def rdw(a):
    b=ctypes.create_string_buffer(4); g=ctypes.c_size_t(); k.ReadProcessMemory(ph,ctypes.c_void_p(a),b,4,ctypes.byref(g)); return struct.unpack('<I',b.raw)[0]
def wmem(a,d):
    n=ctypes.c_size_t(); k.WriteProcessMemory(ph,ctypes.c_void_p(a),d,len(d),ctypes.byref(n))
def force_fg():
    if u.IsIconic(h): u.ShowWindow(h,9); time.sleep(0.4)
    fg=u.GetForegroundWindow(); t=u.GetWindowThreadProcessId(fg,None); c=k.GetCurrentThreadId()
    u.AttachThreadInput(t,c,True); u.BringWindowToTop(h); u.SetForegroundWindow(h); u.AttachThreadInput(t,c,False)
def tap(vk):
    sc=u.MapVirtualKeyW(vk,0); u.keybd_event(vk,sc,1,0); time.sleep(0.015); u.keybd_event(vk,sc,3,0)
def rect():
    r=wt.RECT(); u.GetClientRect(h,ctypes.byref(r)); p=wt.POINT(0,0); u.ClientToScreen(h,ctypes.byref(p))
    return p.x,p.y,r.right,r.bottom
def setpos(cam,x,y):
    s=b"\x55\x8B\xEC"+b"\x68"+struct.pack("<f",y)+b"\x68"+struct.pack("<f",x)
    s+=b"\xB9"+struct.pack("<I",cam)+b"\xB8"+struct.pack("<I",0x6f000000+0x3078b0)+b"\xFF\xD0"+b"\x8B\xE5\x5D\xC2\x04\x00"
    mem=int(k.VirtualAllocEx(ph,None,0x100,0x3000,0x40)); wmem(mem,s)
    tid=wt.DWORD(); th=k.CreateRemoteThread(ph,None,0,ctypes.c_void_p(mem),ctypes.c_void_p(0),0,ctypes.byref(tid))
    if th: k.WaitForSingleObject(th,1000); k.CloseHandle(th)
def main():
    if not h: print("нет окна игры"); return
    force_fg(); time.sleep(0.4)
    cam=rdw(rdw(0x6f000000+0xab4f80)+0x254)
    setpos(cam,*PAN_TO); force_fg(); tap(0x2D); time.sleep(0.4)
    cs=CineCameraSync(); cs.enable()
    for _ in range(30):
        time.sleep(0.2)
        if cs.status().get("installed"): break
    st=cs.status(); print("status:",st)
    if not st.get("installed"): print("драйвер не установился:",st.get("error")); return
    x,y,ww,hh=rect()
    vw=cv2.VideoWriter(OUT,cv2.VideoWriter_fourcc(*"mp4v"),15,(ww,hh))
    sct=mss.mss(); saved={}
    def frame(yaw_deg,pitch_deg,label,key=None):
        cs.set_pose(math.radians(yaw_deg),math.radians(pitch_deg))
        time.sleep(0.055); force_fg(); tap(0x2D); time.sleep(0.04)
        sh=sct.grab({"left":x,"top":y,"width":ww,"height":hh})
        img=np.frombuffer(sh.bgra,np.uint8).reshape(sh.height,sh.width,4)[:,:,:3].copy()
        if label: cv2.putText(img,label,(30,hh-40),cv2.FONT_HERSHEY_SIMPLEX,1.1,(80,255,255),3)
        vw.write(img)
        if key and key not in saved:
            saved[key]=1; cv2.imwrite(KEY+"\\"+key,cv2.resize(img,(640,int(hh*640/ww))))
    # ФАЗА 1: ПОЛНЫЙ оборот 360 (глаз стоит, поворачивается направление взгляда)
    for i in range(73):
        a=i*5
        tag="head turn %d deg"%a + ("  <-- LOOKING BEHIND" if 160<=a<=200 else "")
        frame(a,0,tag,"be_%03d.png"%a if a in (0,90,180,270) else None)
    # ФАЗА 2: наклон вверх/вниз
    for i in range(13):  frame(0,-i*2.2,"head tilt up")
    for i in range(25):  frame(0,-26+i*2.2,"head tilt down","fe_down.png" if i==24 else None)
    for i in range(13):  frame(0,26-i*2.2,"back level")
    # ФАЗА 3: свободный осмотр (как живая голова)
    N=72
    for i in range(N):
        t=i/float(N)*2*math.pi
        frame(120*math.sin(t), 16*math.sin(2*t), "free look-around (eye fixed)")
    frame(0,0,"")
    vw.release()
    cs.set_pose(0,0); time.sleep(0.3); cs.disable()
    print("saved",OUT)
if __name__=="__main__": main()
