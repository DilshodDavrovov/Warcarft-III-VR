# -*- coding: utf-8 -*-
"""
Кросс-селективный поиск камеры WC3 1.26.

Ключ: угол ПОВОРОТА камеры меняется при Insert/Delete, но остаётся
БАЙТ-в-БАЙТ неизменным при панорамировании (стрелки) и наклоне (PageUp/Dn).
Рендер-буферы и списки видимости меняются при ЛЮБОМ движении камеры —
поэтому «реагирует на поворот И стабилен при панораме/наклоне» их убивает.

Найдя угол поворота, выводим окрестность структуры камеры (там же лежат
дистанция ~1650, координаты цели и угол наклона).
"""
import ctypes, ctypes.wintypes as wt, json, struct, time
from pathlib import Path
import cv2, mss, numpy as np

u = ctypes.windll.user32
k = ctypes.windll.kernel32
try: ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception: pass
PROCESS_ALL=0x0010|0x0020|0x0008|0x0400; TH32=0x08|0x10; MEM_COMMIT=0x1000
WRITABLE={0x04,0x08,0x40,0x80}
VK={"INS":0x2D,"DEL":0x2E,"PGUP":0x21,"PGDN":0x22,"L":0x25,"U":0x26,"R":0x27,"D":0x28}
EXT=set(VK.values())

class MBI(ctypes.Structure):
    _fields_=[("BaseAddress",ctypes.c_size_t),("AllocationBase",ctypes.c_size_t),
              ("AllocationProtect",wt.DWORD),("PartitionId",wt.WORD),
              ("RegionSize",ctypes.c_size_t),("State",wt.DWORD),
              ("Protect",wt.DWORD),("Type",wt.DWORD)]
class ME32(ctypes.Structure):
    _fields_=[("dwSize",wt.DWORD),("th32ModuleID",wt.DWORD),("th32ProcessID",wt.DWORD),
              ("GlblcntUsage",wt.DWORD),("ProccntUsage",wt.DWORD),
              ("modBaseAddr",ctypes.POINTER(ctypes.c_byte)),("modBaseSize",wt.DWORD),
              ("hModule",wt.HMODULE),("szModule",ctypes.c_char*256),("szExePath",ctypes.c_char*260)]

def attach():
    h=u.FindWindowW("Warcraft III",None) or u.FindWindowW(None,"Warcraft III")
    if not h: raise SystemExit("NO_WINDOW")
    pid=wt.DWORD(); u.GetWindowThreadProcessId(h,ctypes.byref(pid))
    ph=k.OpenProcess(PROCESS_ALL,False,pid.value)
    snap=k.CreateToolhelp32Snapshot(TH32,pid.value); me=ME32(); me.dwSize=ctypes.sizeof(ME32)
    gb=gs=None
    if k.Module32First(snap,ctypes.byref(me)):
        while True:
            if me.szModule.lower()==b"game.dll":
                gb=ctypes.cast(me.modBaseAddr,ctypes.c_void_p).value; gs=me.modBaseSize; break
            if not k.Module32Next(snap,ctypes.byref(me)): break
    k.CloseHandle(snap)
    return h,ph,gb,gs

def regions(ph):
    a,out=0,[]; mbi=MBI()
    while a<0x7FFF0000:
        if not k.VirtualQueryEx(ph,ctypes.c_void_p(a),ctypes.byref(mbi),ctypes.sizeof(mbi)): break
        if mbi.State==MEM_COMMIT and (mbi.Protect&0xFF) in WRITABLE and mbi.RegionSize<0x8000000:
            out.append((mbi.BaseAddress,mbi.RegionSize))
        a=mbi.BaseAddress+mbi.RegionSize
    return out

def read_region(ph,b,s):
    buf=ctypes.create_string_buffer(s); g=ctypes.c_size_t()
    if not k.ReadProcessMemory(ph,ctypes.c_void_p(b),buf,s,ctypes.byref(g)): return None
    n=g.value&~3
    return np.frombuffer(buf.raw[:n],dtype=np.float32).copy()

def read_all(ph,regs):
    d={}
    for b,s in regs:
        a=read_region(ph,b,s)
        if a is not None: d[b]=a
    return d

def rmem(ph,a,n):
    b=ctypes.create_string_buffer(n); g=ctypes.c_size_t()
    if not k.ReadProcessMemory(ph,ctypes.c_void_p(a),b,n,ctypes.byref(g)): return None
    return b.raw[:g.value]
def rfloat(ph,a):
    d=rmem(ph,a,4); return struct.unpack("<f",d)[0] if d and len(d)==4 else None
def wfloat(ph,a,v):
    d=struct.pack("<f",v); n=ctypes.c_size_t()
    ok=k.WriteProcessMemory(ph,ctypes.c_void_p(a),d,4,ctypes.byref(n))
    if not ok:
        old=wt.DWORD(); k.VirtualProtectEx(ph,ctypes.c_void_p(a),4,0x40,ctypes.byref(old))
        ok=k.WriteProcessMemory(ph,ctypes.c_void_p(a),d,4,ctypes.byref(n))
    return bool(ok)

def press(vk,dur=0.45):
    sc=u.MapVirtualKeyW(vk,0); fl=0x0001 if vk in EXT else 0
    t0=time.time()
    while time.time()-t0<dur:
        u.keybd_event(vk,sc,fl,0); time.sleep(0.03)
    u.keybd_event(vk,sc,fl|0x0002,0); time.sleep(0.35)

class Screen:
    def __init__(s,h): s.h=h; s.sct=mss.mss()
    def rect(s):
        for _ in range(20):
            r=wt.RECT(); u.GetClientRect(s.h,ctypes.byref(r)); p=wt.POINT(0,0); u.ClientToScreen(s.h,ctypes.byref(p))
            if r.right-r.left>8 and r.bottom-r.top>8:
                return {"left":p.x,"top":p.y,"width":r.right-r.left,"height":r.bottom-r.top}
            time.sleep(0.1)
        raise SystemExit("no client rect")
    def gray(s):
        sh=s.sct.grab(s.rect()); img=np.frombuffer(sh.bgra,np.uint8).reshape(sh.height,sh.width,4)[:,:,:3]
        return cv2.cvtColor(cv2.resize(img,(320,180)),cv2.COLOR_BGR2GRAY).astype(np.int16)

def delta_mask(prev,cur,changed,eps,tol):
    """Возвращает (mask_changed, mask_stable, new_prev-dict) по регионам."""
    mc,ms={},{}
    for b in prev:
        c=cur.get(b)
        if c is None or c.shape!=prev[b].shape:
            mc[b]=np.zeros(prev[b].shape,bool); ms[b]=np.zeros(prev[b].shape,bool); continue
        with np.errstate(all="ignore"):
            d=c.astype(np.float64)-prev[b].astype(np.float64); ad=np.abs(d)
            fin=np.isfinite(d)
            mc[b]=fin&(ad>eps)&(ad<1000.0)
            ms[b]=fin&(ad<=tol)
    return mc,ms

def main():
    h,ph,gb,gs=attach(); time.sleep(0.3)
    screen=Screen(h)
    u.SetForegroundWindow(h); time.sleep(0.4)
    regs=regions(ph)
    print(f"game.dll {gb:#x}(+{gs:#x}); регионов {len(regs)}, {sum(s for _,s in regs)/1e6:.0f} МБ")

    # baseline + idle-стабильность
    print("idle...")
    s0=read_all(ph,regs); time.sleep(0.7); s1=read_all(ph,regs)
    idle={};
    for b in s0:
        c=s1.get(b)
        if c is None or c.shape!=s0[b].shape: idle[b]=np.zeros(s0[b].shape,bool)
        else:
            with np.errstate(all="ignore"):
                idle[b]=np.isfinite(c)&np.isfinite(s0[b])&(np.abs(c.astype(np.float64)-s0[b].astype(np.float64))<1e-4)
    prev=s1

    def step(action_keys, label):
        nonlocal prev
        for vk in action_keys: press(vk)
        cur=read_all(ph,regs)
        mc,ms=delta_mask(prev,cur,None,1e-3,2e-3)
        prev=cur
        return mc,ms

    print("rotate #1 (Insert)...");  rot1_c,_        = step([VK["INS"]],"rot1")
    print("rotate #2 (Insert)...");  rot2_c,_        = step([VK["INS"]],"rot2")
    print("pan (arrows)...");        _,     pan_s    = step([VK["R"],VK["U"]],"pan")
    print("tilt (PageUp/Dn)...");    _,     aoa_s    = step([VK["PGUP"]],"aoa")

    # YAW = idle & реагирует на оба поворота монотонно & стабилен при панораме и наклоне
    survivors=[]
    for b in prev:
        with np.errstate(all="ignore"):
            m = idle[b] & rot1_c[b] & rot2_c[b] & pan_s[b] & aoa_s[b]
        for i in np.where(m)[0]:
            survivors.append((b+4*int(i), float(prev[b][i])))
    print(f"\nYAW-кандидатов (кросс-селект): {len(survivors)}")

    # глобальный write-тест
    u.SetForegroundWindow(h); time.sleep(0.3)
    confirmed=[]
    for addr,val in survivors[:80]:
        v=rfloat(ph,addr)
        if v is None: continue
        d=0.5 if abs(v)<10 else 40.0
        b0=screen.gray(); wfloat(ph,addr,v+d); time.sleep(0.4); c0=screen.gray()
        back=rfloat(ph,addr); wfloat(ph,addr,v); time.sleep(0.25)
        dd=np.abs(c0-b0); frac=float((dd>8).mean())
        sticky=back is not None and abs(back-(v+d))<abs(d)*0.5+0.5
        glob=frac>0.25
        src=f"game.dll+{addr-gb:#x}" if gb<=addr<gb+gs else f"heap {addr:#x}"
        if frac>0.05:
            print(f"  {src:22s} val={v:9.4f} frac={frac:.2f} sticky={sticky} {'★КАМЕРА' if (glob and sticky) else ''}")
        if glob and sticky:
            confirmed.append((addr,v))

    print(f"\n=== подтверждённых камер-полей (глобальный поворот): {len(confirmed)} ===")
    out={"game_dll_base":gb,"game_dll_size":gs,"yaw":[]}
    for addr,v in confirmed:
        in_gd=gb<=addr<gb+gs
        print(f"\n-- YAW {addr:#x} (val={v:.4f}) --  окрестность:")
        blk=rmem(ph,addr-0x40,0xA0)
        neigh=[]
        if blk:
            for i in range(0,len(blk)-3,4):
                (f,)=struct.unpack_from("<f",blk,i); off=i-0x40
                if 1e-6<abs(f)<1e9:
                    note=""
                    if 1200<abs(f)<3200: note="  ? дистанция"
                    elif 3200<=abs(f)<1e5: note="  ? координата цели"
                    elif 0.5<abs(f)<6.5 and off!=0: note="  ? угол(рад)"
                    elif 30<abs(f)<360 and off!=0: note="  ? угол(град)"
                    tag=" <== YAW" if off==0 else ""
                    print(f"     +{off:+#05x}  {f:12.3f}{tag}{note}")
                    neigh.append({"offset":off,"value":f})
        out["yaw"].append({"addr":addr,"offset_from_gamedll":(addr-gb) if in_gd else None,
                           "in_game_dll":in_gd,"value":v,"neighbors":neigh})
    Path(r"d:\Games\Warcraft\vr\tools\camera_addrs.json").write_text(json.dumps(out,indent=2),encoding="utf-8")
    print("\nсохранено camera_addrs.json")
    k.CloseHandle(ph)

if __name__=="__main__":
    main()
