# -*- coding: utf-8 -*-
"""Чистый визуальный тест хука: проверяет активность рендера И эффект поворота."""
import ctypes, ctypes.wintypes as wt, struct, time, math
import mss, numpy as np, cv2
u=ctypes.windll.user32; k=ctypes.windll.kernel32
try: ctypes.windll.shcore.SetProcessDpiAwareness(2)
except: pass
k.VirtualAllocEx.restype=ctypes.c_void_p; k.VirtualAllocEx.argtypes=[wt.HANDLE,ctypes.c_void_p,ctypes.c_size_t,wt.DWORD,wt.DWORD]
k.OpenProcess.restype=wt.HANDLE
TH32=0x08|0x10; HOOK=0x3065a7; BACK=0x3065ad; ORIG=b"\x8d\xbe\xa4\x05\x00\x00"
OUT=r"C:\Users\User\AppData\Local\Temp\claude\d--Games-Warcraft\68b4b6b4-84ac-41a2-a57c-c8299edcfdef\scratchpad"
class ME32(ctypes.Structure):
    _fields_=[("dwSize",wt.DWORD),("th32ModuleID",wt.DWORD),("th32ProcessID",wt.DWORD),
              ("GlblcntUsage",wt.DWORD),("ProccntUsage",wt.DWORD),
              ("modBaseAddr",ctypes.POINTER(ctypes.c_byte)),("modBaseSize",wt.DWORD),
              ("hModule",wt.HMODULE),("szModule",ctypes.c_char*256),("szExePath",ctypes.c_char*260)]
def attach():
    h=u.FindWindowW("Warcraft III",None)
    if u.IsIconic(h): u.ShowWindow(h,9); time.sleep(0.5)
    pid=wt.DWORD(); u.GetWindowThreadProcessId(h,ctypes.byref(pid))
    ph=k.OpenProcess(0x043A,False,pid.value)
    snap=k.CreateToolhelp32Snapshot(TH32,pid.value); me=ME32(); me.dwSize=ctypes.sizeof(ME32); gb=None
    if k.Module32First(snap,ctypes.byref(me)):
        while True:
            if me.szModule.lower()==b"game.dll": gb=ctypes.cast(me.modBaseAddr,ctypes.c_void_p).value; break
            if not k.Module32Next(snap,ctypes.byref(me)): break
    k.CloseHandle(snap); return h,ph,gb
def force_fg(h):
    fg=u.GetForegroundWindow(); t=u.GetWindowThreadProcessId(fg,None); c=k.GetCurrentThreadId()
    u.AttachThreadInput(t,c,True); u.BringWindowToTop(h); u.SetForegroundWindow(h); u.AttachThreadInput(t,c,False)
def r(ph,a,n):
    b=ctypes.create_string_buffer(n); g=ctypes.c_size_t()
    return b.raw[:g.value] if k.ReadProcessMemory(ph,ctypes.c_void_p(a),b,n,ctypes.byref(g)) else None
def rdw(ph,a): d=r(ph,a,4); return struct.unpack("<I",d)[0] if d else None
def rf(ph,a): d=r(ph,a,4); return struct.unpack("<f",d)[0] if d else None
def w(ph,a,data):
    n=ctypes.c_size_t()
    if not k.WriteProcessMemory(ph,ctypes.c_void_p(a),data,len(data),ctypes.byref(n)):
        old=wt.DWORD(); k.VirtualProtectEx(ph,ctypes.c_void_p(a),len(data),0x40,ctypes.byref(old)); k.WriteProcessMemory(ph,ctypes.c_void_p(a),data,len(data),ctypes.byref(n))
def wf(ph,a,v): w(ph,a,struct.pack("<f",v))
def wdw(ph,a,v): w(ph,a,struct.pack("<I",v&0xffffffff))
def grab(h,save=None):
    r_=wt.RECT(); u.GetClientRect(h,ctypes.byref(r_)); p=wt.POINT(0,0); u.ClientToScreen(h,ctypes.byref(p))
    with mss.mss() as s: sh=s.grab({"left":p.x,"top":p.y,"width":r_.right,"height":r_.bottom})
    img=np.frombuffer(sh.bgra,np.uint8).reshape(sh.height,sh.width,4)[:,:,:3]
    if save: cv2.imwrite(OUT+"\\"+save,img)
    return cv2.cvtColor(cv2.resize(img,(320,180)),cv2.COLOR_BGR2GRAY).astype(np.int16)
def install(ph,gb):
    if r(ph,gb+HOOK,1)[0]==0xE9: w(ph,gb+HOOK,ORIG)
    cave=int(k.VirtualAllocEx(ph,None,0x1000,0x3000,0x40))
    VR=cave+0x100; ROT=cave+0x104
    sc=b"\xA1"+struct.pack("<I",VR)+b"\x85\xC0\x74\x09"+b"\xA1"+struct.pack("<I",ROT)+b"\x89\x44\x24\x3C"+ORIG
    sc+=b"\xE9"+struct.pack("<i",(gb+BACK)-(cave+len(sc)+5))
    w(ph,cave,sc); wdw(ph,VR,0); wf(ph,ROT,0.0)
    w(ph,gb+HOOK,b"\xE9"+struct.pack("<i",cave-(gb+HOOK+5))+b"\x90")
    return cave,VR,ROT
def main():
    h,ph,gb=attach(); force_fg(h); time.sleep(0.4)
    cont=rdw(ph,gb+0xab4f80); cam=rdw(ph,cont+0x254); neutral=rf(ph,cam+0x5b8)
    cave,VR,ROT=install(ph,gb); print("neutral=%.4f cave=%#x"%(neutral,cave))
    wdw(ph,VR,1); wf(ph,ROT,neutral)
    force_fg(h); time.sleep(0.5)
    a1=grab(h,"vis_neutral.png"); time.sleep(0.4); a2=grab(h)
    render_activity=float(np.abs(a2-a1).mean())
    print("активность рендера (2 кадра при neutral): %.2f -> %s"%(render_activity,"РЕНДЕРИТ" if render_activity>0.5 else "ЗАМОРОЖЕН"))
    wf(ph,ROT,neutral+math.radians(50)); force_fg(h); time.sleep(0.6)
    b=grab(h,"vis_plus50.png")
    print("эффект поворота (+50deg vs neutral): %.2f -> %s"%(float(np.abs(b-a1).mean()),"ПОВОРОТ РАБОТАЕТ" if float(np.abs(b-a1).mean())>4 else "нет"))
    wf(ph,ROT,neutral); wdw(ph,VR,0); w(ph,gb+HOOK,ORIG)
    print("хук снят")
    k.CloseHandle(ph)
if __name__=="__main__": main()
