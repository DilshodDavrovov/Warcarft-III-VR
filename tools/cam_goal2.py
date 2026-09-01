# -*- coding: utf-8 -*-
"""
1.26: цель поворота = Angle-объект по camera+0x15c (из дизасма FUN_6f3063d0).
Дампит его, diff на Insert (находит target-поле), и write-тест: держится ли + поворот.
camera = [[game.dll+0xab4f80]+0x254]; rotation goal=+0x15c, AoA=+0xe4, dist=+0xcc.
"""
import ctypes, ctypes.wintypes as wt, struct, time, math
import mss, numpy as np, cv2
u=ctypes.windll.user32; k=ctypes.windll.kernel32
try: ctypes.windll.shcore.SetProcessDpiAwareness(2)
except: pass
TH32=0x08|0x10; EXT={0x2D,0x2E,0x21,0x22}
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
def rmem(ph,a,n):
    b=ctypes.create_string_buffer(n); g=ctypes.c_size_t()
    return b.raw[:g.value] if k.ReadProcessMemory(ph,ctypes.c_void_p(a),b,n,ctypes.byref(g)) else None
def wf(ph,a,v):
    d=struct.pack("<f",v); n=ctypes.c_size_t(); k.WriteProcessMemory(ph,ctypes.c_void_p(a),d,4,ctypes.byref(n))
def press(vk,dur=0.5):
    sc=u.MapVirtualKeyW(vk,0); fl=0x0001 if vk in EXT else 0; t0=time.time()
    while time.time()-t0<dur: u.keybd_event(vk,sc,fl,0); time.sleep(0.03)
    u.keybd_event(vk,sc,fl|0x0002,0); time.sleep(0.35)
def grab(h):
    r=wt.RECT(); u.GetClientRect(h,ctypes.byref(r)); p=wt.POINT(0,0); u.ClientToScreen(h,ctypes.byref(p))
    with mss.mss() as s: sh=s.grab({"left":p.x,"top":p.y,"width":r.right,"height":r.bottom})
    return cv2.cvtColor(cv2.resize(np.frombuffer(sh.bgra,np.uint8).reshape(sh.height,sh.width,4)[:,:,:3],(320,180)),cv2.COLOR_BGR2GRAY).astype(np.int16)
def main():
    h,ph,gb=attach(); u.SetForegroundWindow(h); time.sleep(0.4)
    cont=rdw(ph,gb+0xab4f80); cam=rdw(ph,cont+0x254)
    rot_obj=cam+0x15c
    print("камера=%#x  rotation-Angle=%#x"%(cam,rot_obj))
    blk=rmem(ph,rot_obj,0x40)
    print("=== дамп Angle-объекта поворота (camera+0x15c) ===")
    for i in range(0,0x40,4):
        iv=struct.unpack_from("<I",blk,i)[0]; fv=struct.unpack_from("<f",blk,i)[0]
        note=""
        if 0.3<abs(fv)<6.5: note="  angle(rad)?"
        elif 0x6f000000<=iv<0x70000000: note="  vftable/ptr"
        print("  +%#04x: int %#010x  float %.4f%s"%(i,iv,fv,note))
    # diff на Insert
    before=rmem(ph,rot_obj,0x40); press(0x2D); after=rmem(ph,rot_obj,0x40)
    print("\n=== изменилось на Insert ===")
    changed=[]
    for i in range(0,0x40,4):
        bf=struct.unpack_from("<f",before,i)[0]; af=struct.unpack_from("<f",after,i)[0]
        if abs(bf-af)>1e-4:
            print("  +%#04x: %.4f -> %.4f (d=%+.4f)"%(i,bf,af,af-bf)); changed.append(i)
    press(0x2E)
    # write-тест каждого изменившегося поля
    print("\n=== write-тест полей (держится+поворот вида) ===")
    for off in changed:
        addr=rot_obj+off; cur=rf(ph,addr)
        a=grab(h); wf(ph,addr,cur+math.radians(50)); time.sleep(0.6); b=grab(h)
        back=rf(ph,addr); wf(ph,addr,cur); time.sleep(0.3)
        frac=float((np.abs(b-a)>8).mean()); held=back is not None and abs(back-(cur+math.radians(50)))<0.1
        print("  +%#04x val=%.4f frac=%.2f held=%s %s"%(off,cur,frac,held,">>> 1:1 УПРАВЛЕНИЕ!" if frac>0.25 and held else (">>> поворачивает (не держится)" if frac>0.25 else "")))
    k.CloseHandle(ph); print("готово")
if __name__=="__main__": main()
