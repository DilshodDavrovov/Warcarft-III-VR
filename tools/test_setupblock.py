# -*- coding: utf-8 -*-
"""
Проверка «прямого» управления камерой как в кат-сценах:
запись в БЛОК НАСТРОЕК камеры (game.dll+0x9364xx) + рефреш-триггер.
Аналогично рабочему хаку дистанции (пишет 0x93645C + клавиша).

Тестируем распространение на ПОВОРОТ (0x936444) и НАКЛОН (0x936438),
с разными способами «рефреша», и смотрим: меняется ли вид и ДЕРЖИТСЯ ли.
"""
import ctypes, ctypes.wintypes as wt, struct, time
import cv2, mss, numpy as np

u=ctypes.windll.user32; k=ctypes.windll.kernel32
try: ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception: pass
PROCESS_ALL=0x0010|0x0020|0x0008|0x0400; TH32=0x08|0x10
VK={"INS":0x2D,"DEL":0x2E,"PGUP":0x21,"PGDN":0x22,"HOME":0x24,"END":0x23}; EXT=set(VK.values())

class ME32(ctypes.Structure):
    _fields_=[("dwSize",wt.DWORD),("th32ModuleID",wt.DWORD),("th32ProcessID",wt.DWORD),
              ("GlblcntUsage",wt.DWORD),("ProccntUsage",wt.DWORD),
              ("modBaseAddr",ctypes.POINTER(ctypes.c_byte)),("modBaseSize",wt.DWORD),
              ("hModule",wt.HMODULE),("szModule",ctypes.c_char*256),("szExePath",ctypes.c_char*260)]

def attach():
    h=u.FindWindowW("Warcraft III",None) or u.FindWindowW(None,"Warcraft III")
    if not h: raise SystemExit("NO_WINDOW")
    if u.IsIconic(h): u.ShowWindow(h,9); time.sleep(0.4)
    pid=wt.DWORD(); u.GetWindowThreadProcessId(h,ctypes.byref(pid))
    ph=k.OpenProcess(PROCESS_ALL,False,pid.value)
    snap=k.CreateToolhelp32Snapshot(TH32,pid.value); me=ME32(); me.dwSize=ctypes.sizeof(ME32); gb=None
    if k.Module32First(snap,ctypes.byref(me)):
        while True:
            if me.szModule.lower()==b"game.dll":
                gb=ctypes.cast(me.modBaseAddr,ctypes.c_void_p).value; break
            if not k.Module32Next(snap,ctypes.byref(me)): break
    k.CloseHandle(snap)
    return h,ph,gb
def rfloat(ph,a):
    b=ctypes.create_string_buffer(4); g=ctypes.c_size_t()
    if not k.ReadProcessMemory(ph,ctypes.c_void_p(a),b,4,ctypes.byref(g)): return None
    return struct.unpack("<f",b.raw)[0]
def wfloat(ph,a,v):
    d=struct.pack("<f",v); n=ctypes.c_size_t()
    ok=k.WriteProcessMemory(ph,ctypes.c_void_p(a),d,4,ctypes.byref(n))
    if not ok:
        old=wt.DWORD(); k.VirtualProtectEx(ph,ctypes.c_void_p(a),4,0x40,ctypes.byref(old))
        ok=k.WriteProcessMemory(ph,ctypes.c_void_p(a),d,4,ctypes.byref(n))
    return bool(ok)
def tap(name):
    vk=VK[name]; sc=u.MapVirtualKeyW(vk,0); fl=0x0001 if vk in EXT else 0
    u.keybd_event(vk,sc,fl,0); time.sleep(0.02); u.keybd_event(vk,sc,fl|0x0002,0)
def postkey(h,name):
    # как Xenon: PostMessage WM_SYSKEYDOWN
    u.PostMessageW(h,0x0104,VK[name],0)  # WM_SYSKEYDOWN

class Screen:
    def __init__(s,h): s.h=h; s.sct=mss.mss()
    def rect(s):
        for _ in range(20):
            r=wt.RECT(); u.GetClientRect(s.h,ctypes.byref(r)); p=wt.POINT(0,0); u.ClientToScreen(s.h,ctypes.byref(p))
            if r.right-r.left>8: return {"left":p.x,"top":p.y,"width":r.right-r.left,"height":r.bottom-r.top}
            time.sleep(0.1)
        raise SystemExit("no rect")
    def gray(s):
        sh=s.sct.grab(s.rect()); img=np.frombuffer(sh.bgra,np.uint8).reshape(sh.height,sh.width,4)[:,:,:3]
        return cv2.cvtColor(cv2.resize(img,(320,180)),cv2.COLOR_BGR2GRAY).astype(np.int16)

def main():
    h,ph,gb=attach(); time.sleep(0.3); screen=Screen(h)
    u.SetForegroundWindow(h); time.sleep(0.4)
    print(f"game.dll={gb:#x}")
    OFF={"AoA":0x936438,"rotation":0x936444,"distance":0x93645C}
    print("текущий блок настроек:")
    for name,off in OFF.items():
        print(f"  {name:9s} game.dll+{off:#x} = {rfloat(ph,gb+off):.3f}")

    def trial(name, off, delta, refresh):
        addr=gb+off; cur=rfloat(ph,addr)
        if cur is None: return
        b0=screen.gray()
        wfloat(ph,addr,cur+delta)
        # рефреш
        if refresh=="pgtap": tap("PGDN"); tap("PGUP")
        elif refresh=="post": postkey(h,"PGUP"); postkey(h,"PGDN")
        elif refresh=="instap": tap("INS"); tap("DEL")
        elif refresh=="none": pass
        time.sleep(0.5)
        c0=screen.gray(); after=rfloat(ph,addr)
        frac=float((np.abs(c0-b0)>8).mean())
        held=after is not None and abs(after-(cur+delta))<abs(delta)*0.5+0.5
        wfloat(ph,addr,cur)
        if refresh=="pgtap": tap("PGDN"); tap("PGUP")
        time.sleep(0.4)
        print(f"  {name:9s} +{delta:+6.1f} refresh={refresh:7s}: frac={frac:.2f} held={held} "
              f"{'>>> РАБОТАЕТ' if frac>0.2 and held else ''}")

    print("\nэксперименты (запись в блок настроек + рефреш):")
    for rf in ("none","pgtap","post","instap"):
        trial("distance", OFF["distance"], -600.0, rf)
    print()
    for rf in ("none","pgtap","post","instap"):
        trial("rotation", OFF["rotation"], +45.0, rf)
    print()
    for rf in ("none","pgtap","post"):
        trial("AoA", OFF["AoA"], -20.0, rf)
    k.CloseHandle(ph)
    print("\nготово")

if __name__=="__main__":
    main()
