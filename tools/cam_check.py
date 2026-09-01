# -*- coding: utf-8 -*-
"""Быстрая проверка: работают ли клавиши (camera+0x5b8 меняется на Insert), режим (+0x38)."""
import ctypes, ctypes.wintypes as wt, struct, time, math
u=ctypes.windll.user32; k=ctypes.windll.kernel32
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
def press(vk,dur=0.6):
    sc=u.MapVirtualKeyW(vk,0); fl=0x0001; t0=time.time()
    while time.time()-t0<dur: u.keybd_event(vk,sc,fl,0); time.sleep(0.03)
    u.keybd_event(vk,sc,fl|0x0002,0); time.sleep(0.35)
def main():
    h,ph,gb=attach(); u.SetForegroundWindow(h); time.sleep(0.5)
    cont=rdw(ph,gb+0xab4f80); cam=rdw(ph,cont+0x254)
    mode=rdw(ph,cam+0x38)
    r0=rf(ph,cam+0x5b8); print("камера=%#x  режим[+0x38]=%d  rotation[+0x5b8]=%.4f (%.0f deg)"%(cam,mode,r0,math.degrees(r0)))
    print("жму Insert 0.6с...")
    press(0x2D)
    r1=rf(ph,cam+0x5b8); print("после Insert: rotation=%.4f (%.0f deg)  d=%+.4f  -> клавиши %s"%(r1,math.degrees(r1),r1-r0,"РАБОТАЮТ" if abs(r1-r0)>0.01 else "НЕ работают (фокус?)"))
    press(0x2E)
    k.CloseHandle(ph)
if __name__=="__main__": main()
