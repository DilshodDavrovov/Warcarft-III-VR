# -*- coding: utf-8 -*-
"""
Диагностика: почему запись угла не поворачивает вид?
Берём чистые yaw-датчики (idle+монотонные, значение похоже на угол),
и ТЩАТЕЛЬНО тестируем запись: замер на 0.15/0.4/0.7с, «прилипание»,
и вариант «запись + рефреш-тап». Печатаем всё, чтобы понять механику.
"""
import ctypes, ctypes.wintypes as wt, struct, time
import cv2, mss, numpy as np

u=ctypes.windll.user32; k=ctypes.windll.kernel32
try: ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception: pass
PROCESS_ALL=0x0010|0x0020|0x0008|0x0400; TH32=0x08|0x10; MEM_COMMIT=0x1000
WRITABLE={0x04,0x08,0x40,0x80}; VK={"INS":0x2D,"DEL":0x2E,"PGUP":0x21,"PGDN":0x22}; EXT=set(VK.values())

class MBI(ctypes.Structure):
    _fields_=[("BaseAddress",ctypes.c_size_t),("AllocationBase",ctypes.c_size_t),
              ("AllocationProtect",wt.DWORD),("PartitionId",wt.WORD),
              ("RegionSize",ctypes.c_size_t),("State",wt.DWORD),("Protect",wt.DWORD),("Type",wt.DWORD)]

def attach():
    h=u.FindWindowW("Warcraft III",None) or u.FindWindowW(None,"Warcraft III")
    if not h: raise SystemExit("NO_WINDOW")
    if u.IsIconic(h): u.ShowWindow(h,9); time.sleep(0.4)
    pid=wt.DWORD(); u.GetWindowThreadProcessId(h,ctypes.byref(pid))
    return h, k.OpenProcess(PROCESS_ALL,False,pid.value)

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
    return np.frombuffer(buf.raw[:g.value&~3],dtype=np.float32).copy()
def read_all(ph,regs):
    d={}
    for b,s in regs:
        a=read_region(ph,b,s)
        if a is not None: d[b]=a
    return d
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
def press(vk,dur=0.4):
    sc=u.MapVirtualKeyW(vk,0); fl=0x0001 if vk in EXT else 0; t0=time.time()
    while time.time()-t0<dur:
        u.keybd_event(vk,sc,fl,0); time.sleep(0.03)
    u.keybd_event(vk,sc,fl|0x0002,0); time.sleep(0.3)
def tap(vk):
    sc=u.MapVirtualKeyW(vk,0); fl=0x0001 if vk in EXT else 0
    u.keybd_event(vk,sc,fl,0); time.sleep(0.02); u.keybd_event(vk,sc,fl|0x0002,0)

class Screen:
    def __init__(s,h): s.h=h; s.sct=mss.mss()
    def rect(s):
        for _ in range(20):
            r=wt.RECT(); u.GetClientRect(s.h,ctypes.byref(r)); p=wt.POINT(0,0); u.ClientToScreen(s.h,ctypes.byref(p))
            if r.right-r.left>8 and r.bottom-r.top>8: return {"left":p.x,"top":p.y,"width":r.right-r.left,"height":r.bottom-r.top}
            time.sleep(0.1)
        raise SystemExit("no rect")
    def gray(s):
        sh=s.sct.grab(s.rect()); img=np.frombuffer(sh.bgra,np.uint8).reshape(sh.height,sh.width,4)[:,:,:3]
        return cv2.cvtColor(cv2.resize(img,(320,180)),cv2.COLOR_BGR2GRAY).astype(np.int16)

def main():
    h,ph=attach(); time.sleep(0.3); screen=Screen(h)
    u.SetForegroundWindow(h); time.sleep(0.4)
    regs=regions(ph)
    print(f"регионов {len(regs)}; ищу чистые yaw-датчики...")

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
            out[b]=None if (c is None or c.shape!=prev[b].shape) else (c.astype(np.float64)-prev[b].astype(np.float64))
        prev=cur; return out
    d1=act(VK["INS"]); d2=act(VK["INS"]); d3=act(VK["DEL"])

    cands=[]
    for b in prev:
        if any(x[b] is None for x in (d1,d2,d3)): continue
        with np.errstate(all="ignore"):
            a1,a2,a3=np.abs(d1[b]),np.abs(d2[b]),np.abs(d3[b])
            mx=np.maximum.reduce([a1,a2,a3]); mn=np.minimum.reduce([a1,a2,a3])
            val=prev[b]; av=np.abs(val)
            mono = idle[b]&(np.sign(d1[b])==np.sign(d2[b]))&(np.sign(d3[b])==-np.sign(d1[b]))&(mn>0.6*mx)
            # диапазон скорости вращения: радианы ~0.15..0.9 /нажатие, ИЛИ градусы ~8..50
            rad = mono&(a1>0.12)&(a1<0.95)&(av>0.03)&(av<7.0)
            deg = mono&(a1>7.0)&(a1<55.0)&(av>2.0)&(av<360.0)
            m = rad|deg
        for i in np.where(m)[0]:
            inc=float((a1[i]+a2[i]+a3[i])/3)
            unit="deg" if inc>7 else "rad"
            cands.append((b+4*int(i), float(prev[b][i]), inc, unit))
    # приоритет: значение похоже на реальный угол; тестируем разнообразно
    cands.sort(key=lambda t:t[2])   # меньший инкремент — ближе к плавному вращению камеры
    print(f"угловых датчиков (реалистичная скорость): {len(cands)}; тестирую до 60\n")

    hits=[]
    for addr,val,inc,unit in cands[:60]:
        cur=rfloat(ph,addr)
        if cur is None: continue
        dv = 0.8 if unit=="rad" else 45.0    # заметный, но валидный сдвиг угла
        b0=screen.gray()
        wfloat(ph,addr,cur+dv)
        time.sleep(0.15); f1=float((np.abs(screen.gray()-b0)>8).mean())
        time.sleep(0.30); f2=float((np.abs(screen.gray()-b0)>8).mean())
        s_end=rfloat(ph,addr)
        time.sleep(0.25); f3=float((np.abs(screen.gray()-b0)>8).mean())
        wfloat(ph,addr,cur); time.sleep(0.12)
        held = s_end is not None and abs(s_end-(cur+dv))<abs(dv)*0.5
        glob = max(f1,f2,f3)>0.25
        star = "★" if (glob and held) else ""
        line=(f" {addr:#011x} {unit} val={val:7.3f} inc={inc:.3f} | f@.15/.45/.7={f1:.2f}/{f2:.2f}/{f3:.2f} "
              f"held={held} {star}")
        if glob or held:
            print(line)
        if glob and held:
            hits.append((addr,val,unit))
    print(f"\n>>> НАСТОЯЩИХ управляющих (глобально + держится): {len(hits)}")
    for a,v,unit in hits:
        print(f"    {a:#x}  val={v}  ({unit})")
    k.CloseHandle(ph)
    print("\nдиагностика завершена")

if __name__=="__main__":
    main()
