# -*- coding: utf-8 -*-
"""
Надёжный фокус (AttachThreadInput) + дифф широкого окна вокруг rotation-цели
camera+0x15c на Insert, затем write-тест изменившихся полей (держится+поворот).
"""
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
def force_fg(h):
    fg=u.GetForegroundWindow()
    t_fg=u.GetWindowThreadProcessId(fg,None); t_cur=k.GetCurrentThreadId()
    u.AttachThreadInput(t_fg,t_cur,True)
    u.ShowWindow(h,5); u.BringWindowToTop(h); u.SetForegroundWindow(h)
    u.AttachThreadInput(t_fg,t_cur,False)
    time.sleep(0.2)
    return u.GetForegroundWindow()==h
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
def press(vk,dur=0.6):
    sc=u.MapVirtualKeyW(vk,0); fl=0x0001; t0=time.time()
    while time.time()-t0<dur: u.keybd_event(vk,sc,fl,0); time.sleep(0.03)
    u.keybd_event(vk,sc,fl|0x0002,0); time.sleep(0.35)
def grab(h):
    r=wt.RECT(); u.GetClientRect(h,ctypes.byref(r)); p=wt.POINT(0,0); u.ClientToScreen(h,ctypes.byref(p))
    with mss.mss() as s: sh=s.grab({"left":p.x,"top":p.y,"width":r.right,"height":r.bottom})
    return cv2.cvtColor(cv2.resize(np.frombuffer(sh.bgra,np.uint8).reshape(sh.height,sh.width,4)[:,:,:3],(320,180)),cv2.COLOR_BGR2GRAY).astype(np.int16)
def main():
    h,ph,gb=attach()
    ok=force_fg(h); print("фокус на игре:",ok)
    cont=rdw(ph,gb+0xab4f80); cam=rdw(ph,cont+0x254)
    # проверка клавиш
    r0=rf(ph,cam+0x5b8); press(0x2D); r1=rf(ph,cam+0x5b8); press(0x2E)
    print("камера=%#x  Insert d(rot+0x5b8)=%+.4f -> клавиши %s"%(cam,r1-r0,"OK" if abs(r1-r0)>0.01 else "НЕ работают"))
    if abs(r1-r0)<0.01:
        print("клавиши всё ещё не работают — прекращаю"); return
    # дифф широкого окна camera+0x100..+0x200 на Insert
    A=cam+0x100; N=0x120
    force_fg(h); before=rmem(ph,A,N); press(0x2D); after=rmem(ph,A,N); press(0x2E)
    changed=[]
    for i in range(0,N-3,4):
        bf=struct.unpack_from("<f",before,i)[0]; af=struct.unpack_from("<f",after,i)[0]
        if abs(bf-af)>1e-4 and abs(bf)<1e7 and abs(af)<1e7:
            changed.append((A+i, i, bf, af))
    print("\nизменилось на Insert в camera+0x100..0x220: %d полей"%len(changed))
    for addr,i,bf,af in changed:
        print("  camera+%#05x: %.4f -> %.4f"%(0x100+i,bf,af))
    # write-тест
    print("\n=== write-тест (держится+поворот) ===")
    for addr,i,bf,af in changed:
        force_fg(h)
        cur=rf(ph,addr); a=grab(h); wf(ph,addr,cur+math.radians(50)); time.sleep(0.6); b=grab(h)
        back=rf(ph,addr); wf(ph,addr,cur); time.sleep(0.3)
        frac=float((np.abs(b-a)>8).mean()); held=back is not None and abs(back-(cur+math.radians(50)))<0.1
        if frac>0.1 or held:
            print("  camera+%#05x val=%.4f frac=%.2f held=%s %s"%(0x100+i,cur,frac,held,
                  ">>> 1:1!" if frac>0.25 and held else (">>> крутит(не держ)" if frac>0.25 else "")))
    k.CloseHandle(ph); print("готово")
if __name__=="__main__": main()
