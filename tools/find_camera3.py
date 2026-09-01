# -*- coding: utf-8 -*-
"""
Поиск структуры камеры WC3 1.26 через её ЦЕЛЬ (target x/y).

Цель камеры (точка, на которую смотрит камера) меняется ТОЛЬКО при
панорамировании (стрелки) и стоит на месте при повороте (Insert) и
наклоне (PageUp). Позиции юнитов при панораме не двигаются, рендер-буферы
меняются при любом движении — поэтому «двигается при панораме И замерла
при повороте/наклоне И это крупная мировая координата» = только камера.

Найдя цель, выводим всю структуру камеры (поворот/наклон/дистанция —
соседи по фикс. смещениям) и ищем СТАТИЧЕСКИЙ указатель на неё в game.dll,
чтобы драйвер находил камеру в любой партии.
"""
import ctypes, ctypes.wintypes as wt, json, struct, time
from pathlib import Path
import cv2, mss, numpy as np

u=ctypes.windll.user32; k=ctypes.windll.kernel32
try: ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception: pass
PROCESS_ALL=0x0010|0x0020|0x0008|0x0400; TH32=0x08|0x10; MEM_COMMIT=0x1000
WRITABLE={0x04,0x08,0x40,0x80}
VK={"INS":0x2D,"PGUP":0x21,"R":0x27,"D":0x28,"L":0x25}
EXT=set(VK.values())

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

def press(vk,dur=0.45):
    sc=u.MapVirtualKeyW(vk,0); fl=0x0001 if vk in EXT else 0; t0=time.time()
    while time.time()-t0<dur:
        u.keybd_event(vk,sc,fl,0); time.sleep(0.03)
    u.keybd_event(vk,sc,fl|0x0002,0); time.sleep(0.35)

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

    print("idle..."); s0=read_all(ph,regs); time.sleep(0.7); s1=read_all(ph,regs)
    prev=s1
    idle={}
    for b in s0:
        c=s1.get(b)
        idle[b]=(np.isfinite(c)&np.isfinite(s0[b])&(np.abs(c.astype(np.float64)-s0[b].astype(np.float64))<1e-4)) \
                if (c is not None and c.shape==s0[b].shape) else np.zeros(s0[b].shape,bool)

    def act(keys):
        nonlocal prev
        for vk in keys: press(vk)
        cur=read_all(ph,regs)
        out={}
        for b in prev:
            c=cur.get(b)
            if c is None or c.shape!=prev[b].shape: out[b]=(None,None); continue
            with np.errstate(all="ignore"):
                d=c.astype(np.float64)-prev[b].astype(np.float64)
            out[b]=(d,c)
        prev=cur
        return out

    print("pan #1 (Right)..."); p1=act([VK["R"]])
    print("pan #2 (Right)..."); p2=act([VK["R"]])
    print("rotate (Insert)..."); r1=act([VK["INS"]])
    print("tilt (PageUp)...");   t1=act([VK["PGUP"]])

    survivors=[]
    for b in prev:
        d1,_=p1[b]; d2,_=p2[b]; dr,_=r1[b]; dt,_=t1[b]
        if d1 is None or d2 is None or dr is None or dt is None: continue
        with np.errstate(all="ignore"):
            ad1,ad2=np.abs(d1),np.abs(d2)
            pan = (ad1>3)&(ad2>3)&(np.sign(d1)==np.sign(d2))&(ad1<5000)&(ad2<5000)
            rot_stable=np.abs(dr)<0.5
            tilt_stable=np.abs(dt)<0.5
            val=prev[b]
            coordish=(np.abs(val)>512)&(np.abs(val)<1e5)
            m=idle[b]&pan&rot_stable&tilt_stable&coordish
        for i in np.where(m)[0]:
            survivors.append((b+4*int(i), float(prev[b][i])))
    print(f"\nЦЕЛЬ-камеры кандидатов: {len(survivors)}")

    # write-тест: сдвиг цели -> глобальная панорама (тестируем все, крупный сдвиг)
    u.SetForegroundWindow(h); time.sleep(0.3)
    scored=[]
    for addr,val in survivors[:250]:
        v=rfloat(ph,addr)
        if v is None: continue
        b0=screen.gray(); wfloat(ph,addr,v+1000.0); time.sleep(0.55); c0=screen.gray()
        back=rfloat(ph,addr); wfloat(ph,addr,v); time.sleep(0.2)
        frac=float((np.abs(c0-b0)>8).mean())
        sticky=back is not None and abs(back-(v+1000.0))<700
        scored.append((frac,sticky,addr,v))
    scored.sort(reverse=True)
    print("\nтоп по глобальности:")
    confirmed=[]
    for frac,sticky,addr,v in scored[:15]:
        src=f"game.dll+{addr-gb:#x}" if gb<=addr<gb+gs else f"heap {addr:#x}"
        star="★ЦЕЛЬ" if frac>0.25 and sticky else ""
        print(f"  {src:22s} val={v:11.2f} frac={frac:.2f} sticky={sticky} {star}")
        if frac>0.25 and sticky:
            confirmed.append((addr,v))
    if not confirmed:   # всё равно разберём 3 самых «глобальных»
        confirmed=[(a,v) for _,_,a,v in scored[:3]]

    print(f"\n=== подтверждено целей: {len(confirmed)} ===")
    result={"game_dll_base":gb,"game_dll_size":gs,"cameras":[]}
    gdata=rmem(ph,gb,gs)
    garr=np.frombuffer(gdata[:len(gdata)&~3],dtype=np.uint32) if gdata else None

    seen=set()
    for addr,v in confirmed:
        # цель — это x или y; структура камеры начинается чуть раньше. Печатаем широкую окрестность.
        struct_base=addr-0x20
        if struct_base in seen: continue
        seen.add(struct_base)
        print(f"\n-- цель {addr:#x} (val={v:.1f}); структура камеры вокруг --")
        blk=rmem(ph,addr-0x30,0x80)
        fields=[]
        if blk:
            for i in range(0,len(blk)-3,4):
                (f,)=struct.unpack_from("<f",blk,i); off=i-0x30
                note=""
                if 1200<abs(f)<3300: note="  ? ДИСТАНЦИЯ"
                elif 3300<=abs(f)<1e5: note="  ? координата"
                elif 0.3<abs(f)<7.0: note="  ? угол(рад)"
                elif 30<abs(f)<360: note="  ? угол(град)"
                mk=" <== цель" if off==0 else ""
                if abs(f)>1e-6:
                    print(f"     +{off:+#05x}  {f:12.3f}{mk}{note}")
                fields.append({"offset":off,"value":f})
        # статический указатель в game.dll на структуру камеры
        ptrs=[]
        if garr is not None:
            lo,hi=addr-0x60, addr+0x8
            idx=np.where((garr>=lo)&(garr<=hi))[0]
            for i in idx[:12]:
                p=int(garr[i])
                print(f"     статич.указатель: game.dll+{4*int(i):#x} -> {p:#x} (цель = ptr+{addr-p:#x})")
                ptrs.append({"gamedll_off":4*int(i),"points_to":p,"target_delta":addr-p})
        result["cameras"].append({"target_addr":addr,"target_value":v,"fields":fields,"static_ptrs":ptrs})

    Path(r"d:\Games\Warcraft\vr\tools\camera_addrs.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    print("\nсохранено camera_addrs.json")
    k.CloseHandle(ph)

if __name__=="__main__":
    main()
