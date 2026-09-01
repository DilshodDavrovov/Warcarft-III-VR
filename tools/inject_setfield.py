# -*- coding: utf-8 -*-
"""
Решающий тест: вызов кинематографического сеттера FUN_6f305a60 через CreateRemoteThread.
FUN_6f305a60(this=camera)(int field, float value_deg, float duration, int flag)
field 5 = ROTATION. Если камера свободно повернётся -> это истинный метод (без клампа).
"""
import ctypes, ctypes.wintypes as wt, struct, time, math, sys
import mss, numpy as np, cv2
u=ctypes.windll.user32; k=ctypes.windll.kernel32
try: ctypes.windll.shcore.SetProcessDpiAwareness(2)
except: pass
k.VirtualAllocEx.restype=ctypes.c_void_p; k.VirtualAllocEx.argtypes=[wt.HANDLE,ctypes.c_void_p,ctypes.c_size_t,wt.DWORD,wt.DWORD]
k.OpenProcess.restype=wt.HANDLE
k.CreateRemoteThread.restype=wt.HANDLE
k.CreateRemoteThread.argtypes=[wt.HANDLE,ctypes.c_void_p,ctypes.c_size_t,ctypes.c_void_p,ctypes.c_void_p,wt.DWORD,ctypes.POINTER(wt.DWORD)]
TH32=0x08|0x10; SETFIELD=0x305a60
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
    n=ctypes.c_size_t(); k.WriteProcessMemory(ph,ctypes.c_void_p(a),data,len(data),ctypes.byref(n))
def grab(h,name):
    r_=wt.RECT(); u.GetClientRect(h,ctypes.byref(r_)); p=wt.POINT(0,0); u.ClientToScreen(h,ctypes.byref(p))
    with mss.mss() as s: sh=s.grab({"left":p.x,"top":p.y,"width":r_.right,"height":r_.bottom})
    cv2.imwrite(OUT+"\\"+name, np.frombuffer(sh.bgra,np.uint8).reshape(sh.height,sh.width,4)[:,:,:3])
def call_setfield(ph,gb,cam,field,value_deg,duration,flag):
    stub=b""
    stub+=b"\x55"                                   # push ebp
    stub+=b"\x8B\xEC"                                # mov ebp,esp
    stub+=b"\x6A"+struct.pack("<b",flag)             # push flag
    stub+=b"\x68"+struct.pack("<f",duration)         # push duration(float)
    stub+=b"\x68"+struct.pack("<f",value_deg)        # push value(float)
    stub+=b"\x6A"+struct.pack("<b",field)            # push field
    stub+=b"\xB9"+struct.pack("<I",cam)              # mov ecx,camera
    stub+=b"\xB8"+struct.pack("<I",gb+SETFIELD)      # mov eax,FUN_6f305a60
    stub+=b"\xFF\xD0"                                # call eax
    stub+=b"\x8B\xE5"                                # mov esp,ebp
    stub+=b"\x5D"                                    # pop ebp
    stub+=b"\xC2\x04\x00"                            # ret 4
    mem=k.VirtualAllocEx(ph,None,0x100,0x3000,0x40); mem=int(mem)
    w(ph,mem,stub)
    tid=wt.DWORD()
    th=k.CreateRemoteThread(ph,None,0,ctypes.c_void_p(mem),ctypes.c_void_p(0),0,ctypes.byref(tid))
    if th: k.WaitForSingleObject(th,2000); k.CloseHandle(th)
    return th
def main():
    h,ph,gb=attach(); force_fg(h); time.sleep(0.4)
    cont=rdw(ph,gb+0xab4f80); cam=rdw(ph,cont+0x254)
    n=rf(ph,cam+0x5b8)
    print("camera=%#x neutral rot=%.4f (%.0f deg)"%(cam,n,math.degrees(n)))
    force_fg(h); time.sleep(0.3); grab(h,"cine_before.png")
    print("вызываю FUN_6f305a60(cam, field=5 ROTATION, value=270deg, dur=0, flag=1)...")
    th=call_setfield(ph,gb,cam,5,270.0,0.0,1)
    print("  thread:",th)
    time.sleep(0.6); force_fg(h); time.sleep(0.3)
    print("  camera+0x5b8 после =%.4f (%.0f deg)"%(rf(ph,cam+0x5b8),math.degrees(rf(ph,cam+0x5b8))))
    grab(h,"cine_after270.png")
    # ещё углы
    for deg in [0,120,200]:
        call_setfield(ph,gb,cam,5,float(deg),0.0,1); time.sleep(0.5); force_fg(h); time.sleep(0.2)
        grab(h,"cine_%d.png"%deg); print("  set %d deg -> +0x5b8=%.4f"%(deg,rf(ph,cam+0x5b8)))
    k.CloseHandle(ph); print("готово")
if __name__=="__main__": main()
