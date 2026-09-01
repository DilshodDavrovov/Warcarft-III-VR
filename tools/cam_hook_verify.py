# -*- coding: utf-8 -*-
"""Визуальная проверка код-хука: снимает кадры при rot = neutral-50/0/+50 (VR on, без клавиш)."""
import ctypes, ctypes.wintypes as wt, struct, time, math
import mss, numpy as np, cv2
u=ctypes.windll.user32; k=ctypes.windll.kernel32
try: ctypes.windll.shcore.SetProcessDpiAwareness(2)
except: pass
k.OpenProcess.restype=wt.HANDLE
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
    ph=k.OpenProcess(0x043A,False,pid.value)
    snap=k.CreateToolhelp32Snapshot(TH32,pid.value); me=ME32(); me.dwSize=ctypes.sizeof(ME32); gb=None
    if k.Module32First(snap,ctypes.byref(me)):
        while True:
            if me.szModule.lower()==b"game.dll": gb=ctypes.cast(me.modBaseAddr,ctypes.c_void_p).value; break
            if not k.Module32Next(snap,ctypes.byref(me)): break
    k.CloseHandle(snap); return h,ph,gb
def force_fg(h):
    fg=u.GetForegroundWindow(); t_fg=u.GetWindowThreadProcessId(fg,None); t_cur=k.GetCurrentThreadId()
    u.AttachThreadInput(t_fg,t_cur,True); u.BringWindowToTop(h); u.SetForegroundWindow(h)
    u.AttachThreadInput(t_fg,t_cur,False); time.sleep(0.2)
def rdw(ph,a):
    b=ctypes.create_string_buffer(4); g=ctypes.c_size_t()
    return struct.unpack("<I",b.raw)[0] if k.ReadProcessMemory(ph,ctypes.c_void_p(a),b,4,ctypes.byref(g)) else None
def rf(ph,a):
    b=ctypes.create_string_buffer(4); g=ctypes.c_size_t()
    return struct.unpack("<f",b.raw)[0] if k.ReadProcessMemory(ph,ctypes.c_void_p(a),b,4,ctypes.byref(g)) else None
def wf(ph,a,v):
    n=ctypes.c_size_t(); k.WriteProcessMemory(ph,ctypes.c_void_p(a),struct.pack("<f",v),4,ctypes.byref(n))
def wdw(ph,a,v):
    n=ctypes.c_size_t(); k.WriteProcessMemory(ph,ctypes.c_void_p(a),struct.pack("<I",v&0xffffffff),4,ctypes.byref(n))
def find_cave(ph):
    # ищем VR/ROT: cave выделен как 0x1000 RWX; но проще — пересчитать нельзя, читаем из аргумента?
    # Мы знаем схему: VR=cave+0x100, ROT=cave+0x104. cave неизвестен здесь.
    return None
OUT=r"C:\Users\User\AppData\Local\Temp\claude\d--Games-Warcraft\68b4b6b4-84ac-41a2-a57c-c8299edcfdef\scratchpad"
def grab(h,name):
    r_=wt.RECT(); u.GetClientRect(h,ctypes.byref(r_)); p=wt.POINT(0,0); u.ClientToScreen(h,ctypes.byref(p))
    with mss.mss() as s: sh=s.grab({"left":p.x,"top":p.y,"width":r_.right,"height":r_.bottom})
    img=np.frombuffer(sh.bgra,np.uint8).reshape(sh.height,sh.width,4)[:,:,:3]
    cv2.imwrite(OUT+"\\"+name, img); return img
def main():
    import sys
    VR=int(sys.argv[1],16); ROT=int(sys.argv[2],16)  # адреса из cam_hook (cave+0x100/+0x104)
    h,ph,gb=attach(); force_fg(h)
    cont=rdw(ph,gb+0xab4f80); cam=rdw(ph,cont+0x254); neutral=rf(ph,cam+0x5b8)
    print("neutral=%.4f VR=%#x ROT=%#x"%(neutral,VR,ROT))
    wdw(ph,VR,1)
    for deg,name in [(-50,"hook_left.png"),(0,"hook_center.png"),(50,"hook_right.png")]:
        wf(ph,ROT,neutral+math.radians(deg)); time.sleep(0.5); force_fg(h); time.sleep(0.2)
        grab(h,name); print("снял rot=%+d -> %s"%(deg,name))
    wf(ph,ROT,neutral); wdw(ph,VR,0)
    k.CloseHandle(ph)
if __name__=="__main__": main()
