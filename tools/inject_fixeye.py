# -*- coding: utf-8 -*-
"""
Тест концепции ФИКСИРОВАННЫЙ ГЛАЗ: удерживаем позицию глаза, двигаем цель по
кругу при повороте (SetPos FUN_6f3078b0 + SetField rotation FUN_6f305a60).
Снимаем кадры на нескольких yaw — глаз должен стоять, а взгляд поворачиваться.
"""
import ctypes, ctypes.wintypes as wt, struct, time, math
import mss, numpy as np, cv2
u=ctypes.windll.user32; k=ctypes.windll.kernel32
try: ctypes.windll.shcore.SetProcessDpiAwareness(2)
except: pass
k.VirtualAllocEx.restype=ctypes.c_void_p; k.VirtualAllocEx.argtypes=[wt.HANDLE,ctypes.c_void_p,ctypes.c_size_t,wt.DWORD,wt.DWORD]
k.OpenProcess.restype=wt.HANDLE; k.CreateRemoteThread.restype=wt.HANDLE
k.CreateRemoteThread.argtypes=[wt.HANDLE,ctypes.c_void_p,ctypes.c_size_t,ctypes.c_void_p,ctypes.c_void_p,wt.DWORD,ctypes.POINTER(wt.DWORD)]
TH32=0x08|0x10; SETFIELD=0x305a60; SETPOS=0x3078b0
OUT=r"C:\Users\User\AppData\Local\Temp\claude\d--Games-Warcraft\68b4b6b4-84ac-41a2-a57c-c8299edcfdef\scratchpad"
class M(ctypes.Structure):
    _fields_=[('s',wt.DWORD),('a',wt.DWORD),('b',wt.DWORD),('c',wt.DWORD),('d',wt.DWORD),('mba',ctypes.POINTER(ctypes.c_byte)),('sz',wt.DWORD),('hm',wt.HMODULE),('nm',ctypes.c_char*256),('pp',ctypes.c_char*260)]
def attach():
    h=u.FindWindowW("Warcraft III",None)
    if u.IsIconic(h): u.ShowWindow(h,9); time.sleep(0.5)
    pid=wt.DWORD(); u.GetWindowThreadProcessId(h,ctypes.byref(pid)); ph=k.OpenProcess(0x043A,False,pid.value)
    sn=k.CreateToolhelp32Snapshot(TH32,pid.value); me=M(); me.s=ctypes.sizeof(M); gb=None
    if k.Module32First(sn,ctypes.byref(me)):
        while True:
            if me.nm.lower()==b'game.dll': gb=ctypes.cast(me.mba,ctypes.c_void_p).value; break
            if not k.Module32Next(sn,ctypes.byref(me)): break
    return h,ph,gb
def force_fg(h):
    if u.IsIconic(h): u.ShowWindow(h,9); time.sleep(0.4)
    fg=u.GetForegroundWindow(); t=u.GetWindowThreadProcessId(fg,None); c=k.GetCurrentThreadId()
    u.AttachThreadInput(t,c,True); u.BringWindowToTop(h); u.SetForegroundWindow(h); u.AttachThreadInput(t,c,False)
def tap(vk):
    sc=u.MapVirtualKeyW(vk,0); u.keybd_event(vk,sc,1,0); time.sleep(0.04); u.keybd_event(vk,sc,3,0)
def rf(ph,a):
    b=ctypes.create_string_buffer(4); g=ctypes.c_size_t(); k.ReadProcessMemory(ph,ctypes.c_void_p(a),b,4,ctypes.byref(g)); return struct.unpack('<f',b.raw)[0]
def rdw(ph,a):
    b=ctypes.create_string_buffer(4); g=ctypes.c_size_t(); k.ReadProcessMemory(ph,ctypes.c_void_p(a),b,4,ctypes.byref(g)); return struct.unpack('<I',b.raw)[0]
def w(ph,a,d):
    n=ctypes.c_size_t(); k.WriteProcessMemory(ph,ctypes.c_void_p(a),d,len(d),ctypes.byref(n))
def cam(ph,gb): return rdw(ph,rdw(ph,gb+0xab4f80)+0x254)
def grab(h,name):
    for _ in range(12):
        r=wt.RECT(); u.GetClientRect(h,ctypes.byref(r))
        if r.right>8: break
        u.ShowWindow(h,9); time.sleep(0.25)
    p=wt.POINT(0,0); u.ClientToScreen(h,ctypes.byref(p))
    with mss.mss() as s: sh=s.grab({"left":p.x,"top":p.y,"width":r.right,"height":r.bottom})
    cv2.imwrite(OUT+"\\"+name, cv2.resize(np.frombuffer(sh.bgra,np.uint8).reshape(sh.height,sh.width,4)[:,:,:3],(600,304)))
def run_stub(ph,stub):
    mem=int(k.VirtualAllocEx(ph,None,0x100,0x3000,0x40)); w(ph,mem,stub)
    tid=wt.DWORD(); th=k.CreateRemoteThread(ph,None,0,ctypes.c_void_p(mem),ctypes.c_void_p(0),0,ctypes.byref(tid))
    if th: k.WaitForSingleObject(th,1500); k.CloseHandle(th)
def setfield(ph,gb,cam,field,val,dur,flag):
    s=b"\x55\x8B\xEC"
    s+=b"\x6A"+struct.pack("<b",flag)+b"\x68"+struct.pack("<f",dur)+b"\x68"+struct.pack("<f",val)+b"\x6A"+struct.pack("<b",field)
    s+=b"\xB9"+struct.pack("<I",cam)+b"\xB8"+struct.pack("<I",gb+SETFIELD)+b"\xFF\xD0"
    s+=b"\x8B\xE5\x5D\xC2\x04\x00"; run_stub(ph,s)
def setpos(ph,gb,cam,x,y):
    s=b"\x55\x8B\xEC"
    s+=b"\x68"+struct.pack("<f",y)+b"\x68"+struct.pack("<f",x)   # push y, x
    s+=b"\xB9"+struct.pack("<I",cam)+b"\xB8"+struct.pack("<I",gb+SETPOS)+b"\xFF\xD0"
    s+=b"\x8B\xE5\x5D\xC2\x04\x00"; run_stub(ph,s)
def main():
    h,ph,gb=attach(); force_fg(h); time.sleep(0.4)
    c=cam(ph,gb)
    tx,ty=rf(ph,c+0x5a4),rf(ph,c+0x5a8); D=rf(ph,c+0x5b0); rot0=rf(ph,c+0x5b8)
    print("target0=(%.0f,%.0f) D=%.0f rot0=%.4f(%.0f deg)"%(tx,ty,D,rot0,math.degrees(rot0)))
    R=D*0.55   # горизонтальный радиус глаз-цель (подбор)
    # глаз считаем из текущего: eye = target + R*(cos(rot0),sin(rot0))
    ex=tx+R*math.cos(rot0); ey=ty+R*math.sin(rot0)
    print("EYE=(%.0f,%.0f) R=%.0f"%(ex,ey,R))
    for yaw in [0,40,80,-40]:
        Rr=rot0+math.radians(yaw)
        newtx=ex-R*math.cos(Rr); newty=ey-R*math.sin(Rr)
        setfield(ph,gb,c,5,math.degrees(Rr),0.0,1)   # rotation
        setpos(ph,gb,c,newtx,newty)                   # target -> держит глаз
        time.sleep(0.15); force_fg(h); tap(0x2D); time.sleep(0.15)
        grab(h,"fe_yaw_%d.png"%yaw)
        print("yaw=%+d rot=%.0f target=(%.0f,%.0f)"%(yaw,math.degrees(Rr),newtx,newty))
    # вернуть
    setfield(ph,gb,c,5,math.degrees(rot0),0.0,1); setpos(ph,gb,c,tx,ty)
    print("готово")
if __name__=="__main__": main()
