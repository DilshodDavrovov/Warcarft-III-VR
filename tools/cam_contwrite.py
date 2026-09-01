# -*- coding: utf-8 -*-
"""Проверка непрерывной записи поворота камеры (обгон кадрового обновления)."""
import ctypes, ctypes.wintypes as wt, struct, time, math
import mss, numpy as np, cv2
u=ctypes.windll.user32; k=ctypes.windll.kernel32
try: ctypes.windll.shcore.SetProcessDpiAwareness(2)
except: pass
TH32=0x08|0x10
class ME32(ctypes.Structure):
    _fields_=[("dwSize",wt.DWORD),("th32ModuleID",wt.DWORD),("th32ProcessID",wt.DWORD),
              ("GlblcntUsage",wt.DWORD),("ProccntUsage",wt.DWORD),
              ("modBaseAddr",ctypes.POINTER(ctypes.c_byte)),("modBaseSize",wt.DWORD),
              ("hModule",wt.HMODULE),("szModule",ctypes.c_char*256),("szExePath",ctypes.c_char*260)]
def attach():
    h=u.FindWindowW("Warcraft III",None)
    if u.IsIconic(h): u.ShowWindow(h,9); time.sleep(0.5)
    pid=wt.DWORD(); u.GetWindowThreadProcessId(h,ctypes.byref(pid))
    ph=k.OpenProcess(0x0438,False,pid.value)
    snap=k.CreateToolhelp32Snapshot(TH32,pid.value); me=ME32(); me.dwSize=ctypes.sizeof(ME32); gb=None
    if k.Module32First(snap,ctypes.byref(me)):
        while True:
            if me.szModule.lower()==b"game.dll": gb=ctypes.cast(me.modBaseAddr,ctypes.c_void_p).value; break
            if not k.Module32Next(snap,ctypes.byref(me)): break
    k.CloseHandle(snap); return h,ph,gb
def rdw(ph,a):
    b=ctypes.create_string_buffer(4); g=ctypes.c_size_t()
    return struct.unpack("<I",b.raw)[0] if k.ReadProcessMemory(ph,ctypes.c_void_p(a),b,4,ctypes.byref(g)) else None
def rf(ph,a):
    b=ctypes.create_string_buffer(4); g=ctypes.c_size_t()
    return struct.unpack("<f",b.raw)[0] if k.ReadProcessMemory(ph,ctypes.c_void_p(a),b,4,ctypes.byref(g)) else None
def wf(ph,a,v):
    d=struct.pack("<f",v); n=ctypes.c_size_t(); k.WriteProcessMemory(ph,ctypes.c_void_p(a),d,4,ctypes.byref(n))
def cam(ph,gb):
    c=rdw(ph,gb+0xab4f80); return rdw(ph,c+0x254) if c else None
def grab(h):
    r=wt.RECT(); u.GetClientRect(h,ctypes.byref(r)); p=wt.POINT(0,0); u.ClientToScreen(h,ctypes.byref(p))
    with mss.mss() as s: sh=s.grab({"left":p.x,"top":p.y,"width":r.right,"height":r.bottom})
    return cv2.cvtColor(cv2.resize(np.frombuffer(sh.bgra,np.uint8).reshape(sh.height,sh.width,4)[:,:,:3],(320,180)),cv2.COLOR_BGR2GRAY).astype(np.int16)
def main():
    h,ph,gb=attach(); u.SetForegroundWindow(h); time.sleep(0.4)
    c=cam(ph,gb); ROT=c+0x5b8
    rot0=rf(ph,ROT); print("камера %#x rotation0=%.4f (%.0f deg)"%(c,rot0,math.degrees(rot0)))
    a=grab(h)
    target=rot0+math.radians(60)   # цель: повернуть на 60 град
    # непрерывная запись 1.5с
    t0=time.time(); n=0; overwrites=0
    while time.time()-t0<1.5:
        cur=cam(ph,gb)         # объект может переехать? перечитываем
        if cur:
            r=rf(ph,cur+0x5b8)
            if abs(r-target)>0.01: overwrites+=1
            wf(ph,cur+0x5b8,target)
        n+=1; time.sleep(0.002)
    b=grab(h)
    frac=float((np.abs(b-a)>8).mean())
    rot_end=rf(ph,cam(ph,gb)+0x5b8)
    print("итераций=%d, перезаписей игрой=%d"%(n,overwrites))
    print("frac=%.2f  rot_end=%.4f  => %s"%(frac,rot_end,"НЕПРЕРЫВНАЯ ЗАПИСЬ РАБОТАЕТ!" if frac>0.25 else "не помогло (игра держит своё)"))
    # вернуть
    for _ in range(30):
        cc=cam(ph,gb); wf(ph,cc+0x5b8,rot0); time.sleep(0.005)
    k.CloseHandle(ph); print("готово")
if __name__=="__main__": main()
