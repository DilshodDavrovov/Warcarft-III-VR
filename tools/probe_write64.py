# -*- coding: utf-8 -*-
"""
64-битный write-тест камеры для Reforged 1.32.
Ищет yaw-датчики (idle + монотонно на Insert/Delete, значение ~угол),
и проверяет запись: поворачивает ли вид И держится ли (held).
Память читается/пишется в 64-битном процессе.
"""
import ctypes, ctypes.wintypes as wt, struct, time, math
import cv2, mss, numpy as np

u=ctypes.windll.user32; k=ctypes.windll.kernel32
try: ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception: pass

# 64-битные сигнатуры
k.OpenProcess.restype=wt.HANDLE; k.OpenProcess.argtypes=[wt.DWORD,wt.BOOL,wt.DWORD]
k.ReadProcessMemory.argtypes=[wt.HANDLE,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_size_t,ctypes.POINTER(ctypes.c_size_t)]
k.WriteProcessMemory.argtypes=[wt.HANDLE,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_size_t,ctypes.POINTER(ctypes.c_size_t)]
k.VirtualQueryEx.restype=ctypes.c_size_t
k.VirtualProtectEx.argtypes=[wt.HANDLE,ctypes.c_void_p,ctypes.c_size_t,wt.DWORD,ctypes.POINTER(wt.DWORD)]

PROCESS_ALL=0x0010|0x0020|0x0008|0x0400
MEM_COMMIT=0x1000; RW={0x04,0x08,0x40,0x80}
VK={"INS":0x2D,"DEL":0x2E}; EXT=set(VK.values())

class MBI(ctypes.Structure):
    _fields_=[("BaseAddress",ctypes.c_void_p),("AllocationBase",ctypes.c_void_p),
              ("AllocationProtect",wt.DWORD),("__a",wt.DWORD),
              ("RegionSize",ctypes.c_size_t),("State",wt.DWORD),
              ("Protect",wt.DWORD),("Type",wt.DWORD)]

def attach():
    h=u.FindWindowW("OsWindow",None) or u.FindWindowW(None,"Warcraft III")
    if not h: raise SystemExit("NO_WINDOW")
    if u.IsIconic(h): u.ShowWindow(h,9); time.sleep(0.6)
    pid=wt.DWORD(); u.GetWindowThreadProcessId(h,ctypes.byref(pid))
    ph=k.OpenProcess(PROCESS_ALL,False,pid.value)
    if not ph: raise SystemExit(f"OpenProcess fail {ctypes.get_last_error()}")
    return h,ph

def regions(ph):
    addr=0; out=[]; mbi=MBI()
    while addr < 0x7FFFFFFF0000:
        if not k.VirtualQueryEx(ph,ctypes.c_void_p(addr),ctypes.byref(mbi),ctypes.sizeof(mbi)):
            addr+=0x1000;
            if addr>0x7FFFFFFF0000: break
            continue
        base=mbi.BaseAddress or 0; size=mbi.RegionSize or 0x1000
        # только небольшие RW-регионы: камера в обычной куче, не в текстурных буферах
        if mbi.State==MEM_COMMIT and (mbi.Protect&0xFF) in RW and 0x1000<=size<=0x200000:
            out.append((base,size))
        addr=base+size
    return out

def read_f(ph,b,s):
    buf=ctypes.create_string_buffer(s); got=ctypes.c_size_t()
    if not k.ReadProcessMemory(ph,ctypes.c_void_p(b),buf,s,ctypes.byref(got)): return None
    n=got.value&~3
    return np.frombuffer(buf.raw[:n],dtype=np.float32).copy()
def read_all(ph,regs):
    d={}
    for b,s in regs:
        a=read_f(ph,b,s)
        if a is not None and a.size: d[b]=a
    return d
def rf(ph,a):
    buf=ctypes.create_string_buffer(4); got=ctypes.c_size_t()
    if not k.ReadProcessMemory(ph,ctypes.c_void_p(a),buf,4,ctypes.byref(got)): return None
    return struct.unpack("<f",buf.raw)[0]
def wf(ph,a,v):
    d=struct.pack("<f",v); n=ctypes.c_size_t()
    ok=k.WriteProcessMemory(ph,ctypes.c_void_p(a),d,4,ctypes.byref(n))
    if not ok:
        old=wt.DWORD(); k.VirtualProtectEx(ph,ctypes.c_void_p(a),4,0x40,ctypes.byref(old))
        ok=k.WriteProcessMemory(ph,ctypes.c_void_p(a),d,4,ctypes.byref(n))
    return bool(ok)
def press(vk,dur=0.4):
    sc=u.MapVirtualKeyW(vk,0); fl=0x0001 if vk in EXT else 0; t0=time.time()
    while time.time()-t0<dur:
        u.keybd_event(vk,sc,fl,0); time.sleep(0.03)
    u.keybd_event(vk,sc,fl|0x0002,0); time.sleep(0.3)

class Screen:
    def __init__(s,h): s.h=h; s.sct=mss.mss()
    def gray(s):
        r=wt.RECT(); u.GetClientRect(s.h,ctypes.byref(r)); p=wt.POINT(0,0); u.ClientToScreen(s.h,ctypes.byref(p))
        sh=s.sct.grab({"left":p.x,"top":p.y,"width":r.right,"height":r.bottom})
        return cv2.cvtColor(cv2.resize(np.frombuffer(sh.bgra,np.uint8).reshape(sh.height,sh.width,4)[:,:,:3],(320,180)),cv2.COLOR_BGR2GRAY).astype(np.int16)

def main():
    h,ph=attach(); time.sleep(0.3); screen=Screen(h)
    u.SetForegroundWindow(h); time.sleep(0.4)
    regs=regions(ph)
    print(f"RW-регионов (64-бит): {len(regs)}, всего {sum(s for _,s in regs)/1e6:.0f} МБ")
    s0=read_all(ph,regs); time.sleep(0.6); s0b=read_all(ph,regs)
    idle={}
    for b in s0:
        c=s0b.get(b)
        with np.errstate(all="ignore"):
            idle[b]=(np.isfinite(c)&np.isfinite(s0[b])&(np.abs(c.astype(np.float64)-s0[b].astype(np.float64))<1e-5)) if (c is not None and c.shape==s0[b].shape) else np.zeros(s0[b].shape,bool)
    prev=s0b
    def act(vk):
        nonlocal prev
        press(vk); cur=read_all(ph,regs); out={}
        for b in prev:
            c=cur.get(b)
            if c is None or c.shape!=prev[b].shape:
                out[b]=None
            else:
                with np.errstate(all="ignore"):
                    dd=(c-prev[b]); dd[~np.isfinite(dd)]=0.0   # float32 разность
                    out[b]=dd
        prev=cur; return out
    d1=act(VK["INS"]); d2=act(VK["INS"]); d3=act(VK["DEL"])
    cands=[]
    for b in prev:
        if any(x[b] is None for x in (d1,d2,d3)): continue
        with np.errstate(all="ignore"):
            a1,a2,a3=np.abs(d1[b]),np.abs(d2[b]),np.abs(d3[b]); val=prev[b]; av=np.abs(val)
            mono=idle[b]&(np.sign(d1[b])==np.sign(d2[b]))&(np.sign(d3[b])==-np.sign(d1[b]))
            mx=np.maximum.reduce([a1,a2,a3]); mn=np.minimum.reduce([a1,a2,a3])
            rad=mono&(a1>0.1)&(a1<1.0)&(av>0.02)&(av<7.0)&(mn>0.5*mx)
            deg=mono&(a1>5)&(a1<60)&(av>2)&(av<360)&(mn>0.5*mx)
        for i in np.where(rad|deg)[0]:
            inc=float((a1[i]+a2[i]+a3[i])/3); cands.append((b+4*int(i),float(val[i]),inc,"deg" if inc>5 else "rad"))
    print(f"yaw-датчиков: {len(cands)}; write-тест (держится+поворот всего кадра):")
    hits=[]
    for addr,val,inc,unit in cands[:80]:
        cur=rf(ph,addr)
        if cur is None: continue
        dv=0.8 if unit=="rad" else 45.0
        b0=screen.gray(); wf(ph,addr,cur+dv); time.sleep(0.15); f1=float((np.abs(screen.gray()-b0)>8).mean())
        time.sleep(0.35); f2=float((np.abs(screen.gray()-b0)>8).mean()); end=rf(ph,addr)
        wf(ph,addr,cur); time.sleep(0.12)
        held=end is not None and abs(end-(cur+dv))<abs(dv)*0.5; glob=max(f1,f2)>0.25
        if glob or held:
            print(f"  {addr:#x} {unit} v={val:.3f} f={f1:.2f}/{f2:.2f} held={held} {'★УПРАВЛЯЕТ' if glob and held else ''}")
        if glob and held: hits.append((addr,val,unit))
    print(f"\n>>> прямо управляющих (держится+глобальный поворот): {len(hits)}")
    for a,v,unit in hits: print(f"   {a:#x} val={v} ({unit})")
    k.CloseHandle(ph)

if __name__=="__main__":
    main()
