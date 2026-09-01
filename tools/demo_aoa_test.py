# -*- coding: utf-8 -*-
"""Эксперимент: подбор AoA/дистанции для вида от первого лица. Проверка клампинга."""
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
def tap(vk,dur=0.05):
    sc=u.MapVirtualKeyW(vk,0); t0=time.time()
    while time.time()-t0<dur: u.keybd_event(vk,sc,0x0001,0); time.sleep(0.015)
    u.keybd_event(vk,sc,0x0001|0x0002,0)
def grab(h,name):
    r_=wt.RECT(); u.GetClientRect(h,ctypes.byref(r_)); p=wt.POINT(0,0); u.ClientToScreen(h,ctypes.byref(p))
    with mss.mss() as s: sh=s.grab({"left":p.x,"top":p.y,"width":r_.right,"height":r_.bottom})
    cv2.imwrite(OUT+"\\"+name, np.frombuffer(sh.bgra,np.uint8).reshape(sh.height,sh.width,4)[:,:,:3])
def install(ph,gb):
    if r(ph,gb+HOOK,1)[0]==0xE9: w(ph,gb+HOOK,ORIG)
    cave=int(k.VirtualAllocEx(ph,None,0x1000,0x3000,0x40))
    VR=cave+0x100; ROT=cave+0x104; AOA=cave+0x108; DIST=cave+0x10c
    sc=b"\xA1"+struct.pack("<I",VR)+b"\x85\xC0\x74\x1B"
    sc+=b"\xA1"+struct.pack("<I",ROT)+b"\x89\x44\x24\x3C"
    sc+=b"\xA1"+struct.pack("<I",AOA)+b"\x89\x44\x24\x08"
    sc+=b"\xA1"+struct.pack("<I",DIST)+b"\x89\x44\x24\x48"
    sc+=ORIG+b"\xE9"+struct.pack("<i",(gb+BACK)-(cave+len(sc)+6+5-6))  # placeholder
    # пересчитаем jmp корректно
    sc=b"\xA1"+struct.pack("<I",VR)+b"\x85\xC0\x74\x1B"
    sc+=b"\xA1"+struct.pack("<I",ROT)+b"\x89\x44\x24\x3C"
    sc+=b"\xA1"+struct.pack("<I",AOA)+b"\x89\x44\x24\x08"
    sc+=b"\xA1"+struct.pack("<I",DIST)+b"\x89\x44\x24\x48"
    sc+=ORIG
    sc+=b"\xE9"+struct.pack("<i",(gb+BACK)-(cave+len(sc)+5))
    w(ph,cave,sc)
    w(ph,gb+HOOK,b"\xE9"+struct.pack("<i",cave-(gb+HOOK+5))+b"\x90")
    return cave,VR,ROT,AOA,DIST
def main():
    h,ph,gb=attach(); force_fg(h); time.sleep(0.4)
    cont=rdw(ph,gb+0xab4f80); cam=rdw(ph,cont+0x254)
    n_rot=rf(ph,cam+0x5b8); n_aoa=rf(ph,cam+0x5b4); n_dist=rf(ph,cam+0x5b0)
    print("neutral rot=%.3f aoa=%.3f dist=%.1f"%(n_rot,n_aoa,n_dist))
    cave,VR,ROT,AOA,DIST=install(ph,gb); wdw(ph,VR,1)
    combos=[(1.8,800,"b_aoa18_d800.png"),(2.1,700,"b_aoa21_d700.png"),
            (2.4,600,"b_aoa24_d600.png"),(2.6,500,"b_aoa26_d500.png"),
            (2.9,400,"b_aoa29_d400.png"),(2.4,300,"b_aoa24_d300.png")]
    for aoa,dist,name in combos:
        wf(ph,ROT,n_rot); wf(ph,AOA,aoa); wf(ph,DIST,dist)
        force_fg(h); tap(0x2D); time.sleep(0.08)
        got_aoa=rf(ph,cam+0x5b4); got_dist=rf(ph,cam+0x5b0)
        grab(h,name)
        print("set aoa=%.2f dist=%.0f -> readback aoa=%.3f dist=%.0f  (%s)"%(aoa,dist,got_aoa,got_dist,name))
    wf(ph,ROT,n_rot); wf(ph,AOA,n_aoa); wf(ph,DIST,n_dist); wdw(ph,VR,0); w(ph,gb+HOOK,ORIG)
    print("готово")
if __name__=="__main__": main()
