# -*- coding: utf-8 -*-
"""
МОМЕНТ ИСТИНЫ (1.26): пишем в поля камеры по цепочке
  камера = [[game.dll+0xab4f80] + 0x254]
  rotation=+0x5b8, AoA=+0x5b4, distance=+0x5b0, target=+0x5a4/5a8/5ac
и проверяем скриншотом: поворачивается ли вид И держится ли.
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
    if not h: raise SystemExit("нет окна 1.26")
    if u.IsIconic(h): u.ShowWindow(h,9); time.sleep(0.5)
    pid=wt.DWORD(); u.GetWindowThreadProcessId(h,ctypes.byref(pid))
    ph=k.OpenProcess(0x0438,False,pid.value)  # VM read/write/op/qi
    snap=k.CreateToolhelp32Snapshot(TH32,pid.value); me=ME32(); me.dwSize=ctypes.sizeof(ME32); gb=None
    if k.Module32First(snap,ctypes.byref(me)):
        while True:
            if me.szModule.lower()==b"game.dll":
                gb=ctypes.cast(me.modBaseAddr,ctypes.c_void_p).value; break
            if not k.Module32Next(snap,ctypes.byref(me)): break
    k.CloseHandle(snap)
    return h,ph,gb
def rdw(ph,a):
    b=ctypes.create_string_buffer(4); g=ctypes.c_size_t()
    if not k.ReadProcessMemory(ph,ctypes.c_void_p(a),b,4,ctypes.byref(g)): return None
    return struct.unpack("<I",b.raw)[0]
def rf(ph,a):
    b=ctypes.create_string_buffer(4); g=ctypes.c_size_t()
    if not k.ReadProcessMemory(ph,ctypes.c_void_p(a),b,4,ctypes.byref(g)): return None
    return struct.unpack("<f",b.raw)[0]
def wf(ph,a,v):
    d=struct.pack("<f",v); n=ctypes.c_size_t()
    return bool(k.WriteProcessMemory(ph,ctypes.c_void_p(a),d,4,ctypes.byref(n)))
def cam_addr(ph,gb):
    cont=rdw(ph,gb+0xab4f80)
    if not cont: return None
    return rdw(ph,cont+0x254)
def grab(h):
    if u.IsIconic(h): u.ShowWindow(h,9); time.sleep(0.4)
    r=wt.RECT(); u.GetClientRect(h,ctypes.byref(r)); p=wt.POINT(0,0); u.ClientToScreen(h,ctypes.byref(p))
    if r.right<8: return None
    with mss.mss() as s: sh=s.grab({"left":p.x,"top":p.y,"width":r.right,"height":r.bottom})
    return cv2.cvtColor(cv2.resize(np.frombuffer(sh.bgra,np.uint8).reshape(sh.height,sh.width,4)[:,:,:3],(320,180)),cv2.COLOR_BGR2GRAY).astype(np.int16)

def test(h,ph,gb,off,newval,label):
    cam=cam_addr(ph,gb)
    addr=cam+off
    cur=rf(ph,addr)
    a=grab(h)
    wf(ph,addr,newval)
    time.sleep(0.5)
    b=grab(h)
    back=rf(ph,addr)
    frac=float((np.abs(b-a)>8).mean()) if a is not None and b is not None else -1
    held = back is not None and abs(back-newval)<abs(newval-cur)*0.3+0.05
    print("  %-10s +%#05x: %.4f->%.4f  frac=%.2f held=%s %s"%(label,off,cur,newval,frac,held,
          ">>> УПРАВЛЯЕТ!" if frac>0.25 else ("держится, но вид не изменился" if held else "")))
    # вернуть
    wf(ph,addr,cur); time.sleep(0.3)
    return frac>0.25

def main():
    h,ph,gb=attach()
    u.SetForegroundWindow(h); time.sleep(0.4)
    cam=cam_addr(ph,gb)
    print("камера = %#x" % (cam or 0))
    rot=rf(ph,cam+0x5b8); aoa=rf(ph,cam+0x5b4); dist=rf(ph,cam+0x5b0)
    print("текущие: rotation=%.4f rad (%.1f deg)  AoA=%.4f rad  distance=%.1f" % (rot,math.degrees(rot),aoa,dist))
    print("\n=== write-тесты ===")
    test(h,ph,gb,0x5b8, rot+math.radians(45), "rotation")   # повернуть на 45
    test(h,ph,gb,0x5b8, rot-math.radians(45), "rotation-")
    test(h,ph,gb,0x5b4, aoa+math.radians(20), "AoA")
    test(h,ph,gb,0x5b0, dist-500, "distance")
    test(h,ph,gb,0x5a4, rf(ph,cam+0x5a4)+512, "target_x")
    k.CloseHandle(ph)
    print("готово")

if __name__=="__main__":
    main()
