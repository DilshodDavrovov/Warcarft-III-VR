# -*- coding: utf-8 -*-
"""
Ищет ЦЕЛЕВОЙ угол камеры (goal), из которого игра пишет current(+0x5b8) каждый кадр.
Сканирует контейнер [game.dll+0xab4f80] и его под-объекты (по указателям),
находит float, что (а) ~= текущему повороту, (б) меняется на Insert,
и проверяет записью: держится ли + поворачивает ли вид.
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
    cont=rdw(ph,gb+0xab4f80); camobj=rdw(ph,cont+0x254)
    currot=rf(ph,camobj+0x5b8)
    print("контейнер=%#x камера=%#x current_rot=%.4f"%(cont,camobj,currot))

    # регионы для скана: контейнер и все его указатели (1 уровень), + сам объект камеры
    regions=[(cont,0x600),(camobj,0x800)]
    cblk=rmem(ph,cont,0x600)
    if cblk:
        for i in range(0,len(cblk)-3,4):
            p=struct.unpack_from("<I",cblk,i)[0]
            if 0x100000<p<0x7fff0000:
                regions.append((p,0x400))
    # снимок до
    def snap():
        d={}
        for base,size in regions:
            m=rmem(ph,base,size)
            if m: d[base]=m
        return d
    before=snap()
    press(0x2D)  # Insert
    after=snap()
    # кандидаты: float, изменился на Insert, и его прежнее значение близко к current_rot (это goal)
    cands=[]
    for base,size in regions:
        b=before.get(base); a=after.get(base)
        if not b or not a: continue
        for i in range(0,min(len(a),len(b))-3,4):
            bf=struct.unpack_from("<f",b,i)[0]; af=struct.unpack_from("<f",a,i)[0]
            if abs(bf-af)>0.02 and abs(bf-af)<3 and 0.3<abs(bf)<6.5:
                # похоже на угол, изменившийся на поворот
                near = abs(bf-currot)<0.3
                cands.append((base+i, bf, af, near))
    cands.sort(key=lambda t:(not t[3], abs(t[1]-currot)))
    press(0x2E)  # Delete вернуть
    print("угловых кандидатов (изм. на Insert): %d"%len(cands))
    # write-тест лучших
    print("\n=== write-тест кандидатов (держится + поворот вида) ===")
    hits=[]
    for addr,bf,af,near in cands[:30]:
        cur=rf(ph,addr)
        if cur is None: continue
        a=grab(h); wf(ph,addr,cur+math.radians(50)); time.sleep(0.5); bb=grab(h)
        back=rf(ph,addr); wf(ph,addr,cur); time.sleep(0.25)
        frac=float((np.abs(bb-a)>8).mean())
        held=back is not None and abs(back-(cur+math.radians(50)))<0.2
        tag="near_current" if near else ""
        if frac>0.1 or held:
            print("  %#x val=%.4f frac=%.2f held=%s %s %s"%(addr,cur,frac,held,tag,">>> ЦЕЛЬ УПРАВЛЯЕТ!" if frac>0.25 else ""))
        if frac>0.25: hits.append((addr,cur))
    print("\n>>> управляющих целей: %d"%len(hits))
    for a,v in hits:
        off_c=a-cont; off_cam=a-camobj
        print("   %#x (контейнер+%#x, камера+%#x) val=%.4f"%(a,off_c&0xffffffff,off_cam&0xffffffff,v))
    k.CloseHandle(ph); print("готово")
if __name__=="__main__": main()
