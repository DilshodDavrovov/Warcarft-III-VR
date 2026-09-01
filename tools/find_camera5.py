# -*- coding: utf-8 -*-
"""
Решающий поиск структуры камеры WC3 1.26.

Опознаём структуру перекрёстно:
  ЦЕЛЬ камеры  = крупная координата, двигается при панораме (стрелки),
                 замирает при повороте(Insert) и наклоне(PageUp).
  УГОЛ поворота= сосед этой цели (в ±0x40), который реагирует на Insert,
                 но замирает при панораме.
Совпало и то и другое рядом => это камера. Пишем угол -> весь кадр
поворачивается. Затем ищем статический указатель в game.dll.

Панорамируем в обе стороны (LL и RR), чтобы не застрять у края карты.
"""
import ctypes, ctypes.wintypes as wt, json, struct, time
from pathlib import Path
import cv2, mss, numpy as np

u=ctypes.windll.user32; k=ctypes.windll.kernel32
try: ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception: pass
PROCESS_ALL=0x0010|0x0020|0x0008|0x0400; TH32=0x08|0x10; MEM_COMMIT=0x1000
WRITABLE={0x04,0x08,0x40,0x80}
VK={"INS":0x2D,"DEL":0x2E,"PGUP":0x21,"L":0x25,"R":0x27}; EXT={0x2D,0x2E,0x21,0x22,0x25,0x26,0x27,0x28}

class MBI(ctypes.Structure):
    _fields_=[("BaseAddress",ctypes.c_size_t),("AllocationBase",ctypes.c_size_t),
              ("AllocationProtect",wt.DWORD),("PartitionId",wt.WORD),
              ("RegionSize",ctypes.c_size_t),("State",wt.DWORD),("Protect",wt.DWORD),("Type",wt.DWORD)]
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
    snap=k.CreateToolhelp32Snapshot(TH32,pid.value); me=ME32(); me.dwSize=ctypes.sizeof(ME32); gb=gs=None
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
    return np.frombuffer(buf.raw[:g.value&~3],dtype=np.float32).copy()
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

def press(vk,dur=0.4):
    sc=u.MapVirtualKeyW(vk,0); fl=0x0001 if vk in EXT else 0; t0=time.time()
    while time.time()-t0<dur:
        u.keybd_event(vk,sc,fl,0); time.sleep(0.03)
    u.keybd_event(vk,sc,fl|0x0002,0); time.sleep(0.3)

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
    h,ph,gb,gs=attach(); time.sleep(0.3); screen=Screen(h)
    u.SetForegroundWindow(h); time.sleep(0.4)
    regs=regions(ph)
    print(f"game.dll {gb:#x}(+{gs:#x}); регионов {len(regs)}")

    s1=read_all(ph,regs); time.sleep(0.7); s1b=read_all(ph,regs)
    idle={}
    for b in s1:
        c=s1b.get(b)
        with np.errstate(all="ignore"):
            idle[b]=(np.isfinite(c)&np.isfinite(s1[b])&(np.abs(c.astype(np.float64)-s1[b].astype(np.float64))<1e-4)) \
                    if (c is not None and c.shape==s1[b].shape) else np.zeros(s1[b].shape,bool)
    prev=s1b
    def act(keys):
        nonlocal prev
        for vk in keys: press(vk)
        cur=read_all(ph,regs); out={}
        for b in prev:
            c=cur.get(b)
            if c is None or c.shape!=prev[b].shape: out[b]=None
            else:
                with np.errstate(all="ignore"): out[b]=c.astype(np.float64)-prev[b].astype(np.float64)
        prev=cur; return out
    print("LL..."); dL1=act([VK["L"]]); dL2=act([VK["L"]])
    print("RR..."); dR1=act([VK["R"]]); dR2=act([VK["R"]])
    print("rotate II..."); dI1=act([VK["INS"]]); dI2=act([VK["INS"]])
    print("tilt T...");    dT =act([VK["PGUP"]])
    last=prev

    def mono(a,b_):
        with np.errstate(all="ignore"):
            return (np.abs(a)>3)&(np.abs(b_)>3)&(np.sign(a)==np.sign(b_))&(np.abs(a)<6000)&(np.abs(b_)<6000)

    target_mask={}; rot_mask={}
    for b in last:
        if any(x[b] is None for x in (dL1,dL2,dR1,dR2,dI1,dI2,dT)):
            target_mask[b]=np.zeros(last[b].shape,bool); rot_mask[b]=target_mask[b]; continue
        with np.errstate(all="ignore"):
            val=last[b]
            pan_moved = mono(dL1[b],dL2[b]) | mono(dR1[b],dR2[b])
            rot_still = (np.abs(dI1[b])<0.5)&(np.abs(dI2[b])<0.5)
            tilt_still= np.abs(dT[b])<0.5
            coordish=(np.abs(val)>1000)&(np.abs(val)<1e5)
            target_mask[b]= idle[b]&pan_moved&rot_still&tilt_still&coordish
            # угол: реагирует на поворот монотонно, замер при панораме
            pan_still=(np.abs(dL1[b])<0.5)&(np.abs(dL2[b])<0.5)&(np.abs(dR1[b])<0.5)&(np.abs(dR2[b])<0.5)
            rot_resp=(np.abs(dI1[b])>1e-3)&(np.abs(dI2[b])>1e-3)&(np.sign(dI1[b])==np.sign(dI2[b]))&(np.abs(dI1[b])<50)
            rot_mask[b]= idle[b]&rot_resp&pan_still

    targets=[]
    for b in last:
        for i in np.where(target_mask[b])[0]:
            targets.append(b+4*int(i))
    print(f"кандидатов-целей: {len(targets)}")

    # для каждой цели ищем рядом угол (rot_mask) => структура камеры
    def is_rot(addr):
        b=(addr)&~3
        # найти регион
        for base in last:
            n=last[base].shape[0]
            if base<=addr<base+4*n:
                idx=(addr-base)//4
                return bool(rot_mask[base][idx]), float(last[base][idx])
        return False,None

    structs=[]
    for taddr in targets:
        for off in range(-0x40,0x44,4):
            a=taddr+off
            if a==taddr: continue
            ok,val=is_rot(a)
            if ok and val is not None and abs(val)<7.5:   # угол в радианах
                structs.append((taddr,a,val)); break
    # уникализируем по адресу угла
    uniq={}
    for t,a,v in structs: uniq[a]=(t,v)
    print(f"структур (цель+угол рядом): {len(uniq)}")

    # write-тест угла -> глобальный поворот
    u.SetForegroundWindow(h); time.sleep(0.3)
    confirmed=[]
    for a,(t,v) in list(uniq.items())[:40]:
        cur=rfloat(ph,a)
        if cur is None: continue
        b0=screen.gray(); wfloat(ph,a,cur+0.6); time.sleep(0.45); c0=screen.gray()
        back=rfloat(ph,a); wfloat(ph,a,cur); time.sleep(0.2)
        frac=float((np.abs(c0-b0)>8).mean())
        sticky=back is not None and abs(back-(cur+0.6))<0.4
        src=f"game.dll+{a-gb:#x}" if gb<=a<gb+gs else f"heap {a:#x}"
        print(f"  угол {src:20s} val={v:7.4f} цель@{t:#x} frac={frac:.2f} sticky={sticky} {'★КАМЕРА' if frac>0.25 and sticky else ''}")
        if frac>0.25 and sticky:
            confirmed.append((a,t,v))

    result={"game_dll_base":gb,"game_dll_size":gs,"cameras":[]}
    gdata=rmem(ph,gb,gs); garr=np.frombuffer(gdata[:len(gdata)&~3],dtype=np.uint32) if gdata else None
    print(f"\n=== подтверждено камер: {len(confirmed)} ===")
    for a,t,v in confirmed:
        base_struct=min(a,t)-0x20
        print(f"\n-- КАМЕРА: угол@{a:#x}={v:.4f}, цель@{t:#x}. Структура: --")
        blk=rmem(ph,base_struct,0x80)
        if blk:
            for i in range(0,len(blk)-3,4):
                (f,)=struct.unpack_from("<f",blk,i); ad=base_struct+i
                tag=""
                if ad==a: tag=" <== УГОЛ поворота"
                elif ad==t: tag=" <== ЦЕЛЬ"
                elif 1200<abs(f)<3300: tag="  ? дистанция"
                elif 3000<abs(f)<1e5: tag="  ? координата"
                elif 0.3<abs(f)<7 and abs(f)>1e-3: tag="  ? угол(рад)"
                if abs(f)>1e-7: print(f"   {ad:#x} (+{i-0x20:+#05x})  {f:12.3f}{tag}")
        # статический указатель
        ptrs=[]
        if garr is not None:
            lo,hi=base_struct-0x10, base_struct+0x60
            idx=np.where((garr>=lo)&(garr<=hi))[0]
            for i in idx[:16]:
                p=int(garr[i]); print(f"   статич.ptr game.dll+{4*int(i):#x} -> {p:#x} (угол=ptr+{a-p:#x})")
                ptrs.append({"gamedll_off":4*int(i),"points_to":p,"angle_delta":a-p})
        result["cameras"].append({"angle_addr":a,"target_addr":t,"angle_value":v,"static_ptrs":ptrs})
    Path(r"d:\Games\Warcraft\vr\tools\camera_addrs.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    print("\nсохранено camera_addrs.json")
    k.CloseHandle(ph)

if __name__=="__main__":
    main()
