# -*- coding: utf-8 -*-
"""
Поиск структуры камеры WC3 1.29 по ДОСТИЖИМОСТИ из статического указателя exe.

Настоящая камера — синглтон, на неё есть глобальный указатель в Warcraft III.exe.
Крипы/билборды лежат в динамических массивах и из статики не адресуются.
Пересечение «крупная координата, реагирует на поворот/панораму, idle-стабильна,
достижима из статического указателя exe (1-2 уровня)» = камера.

Затем write-тест: двигаем eye по орбите -> вид поворачивается и ДЕРЖИТСЯ.
"""
import ctypes, ctypes.wintypes as wt, struct, time, math, json
from pathlib import Path
import cv2, mss, numpy as np

u=ctypes.windll.user32; k=ctypes.windll.kernel32
try: ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception: pass
PROCESS_ALL=0x0010|0x0020|0x0008|0x0400; TH32=0x08|0x10; MEM_COMMIT=0x1000
RW={0x04,0x08,0x40,0x80}; READABLE={0x02,0x04,0x08,0x20,0x40,0x80}
VK={"INS":0x2D,"DEL":0x2E,"L":0x25,"R":0x27,"PGUP":0x21}; EXT=set(VK.values())

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
    h=u.FindWindowW("Warcraft III",None)
    if not h: raise SystemExit("NO_WINDOW")
    if u.IsIconic(h): u.ShowWindow(h,9); time.sleep(0.4)
    pid=wt.DWORD(); u.GetWindowThreadProcessId(h,ctypes.byref(pid))
    ph=k.OpenProcess(PROCESS_ALL,False,pid.value)
    snap=k.CreateToolhelp32Snapshot(TH32,pid.value); me=ME32(); me.dwSize=ctypes.sizeof(ME32); eb=es=None
    if k.Module32First(snap,ctypes.byref(me)):
        while True:
            if me.szModule.lower()==b"warcraft iii.exe":
                eb=ctypes.cast(me.modBaseAddr,ctypes.c_void_p).value; es=me.modBaseSize; break
            if not k.Module32Next(snap,ctypes.byref(me)): break
    k.CloseHandle(snap)
    if not eb: raise SystemExit("exe модуль не найден")
    return h,ph,eb,es

def regions(ph,prot_set):
    a,out=0,[]; mbi=MBI()
    while a<0x7FFF0000:
        if not k.VirtualQueryEx(ph,ctypes.c_void_p(a),ctypes.byref(mbi),ctypes.sizeof(mbi)): break
        if mbi.State==MEM_COMMIT and (mbi.Protect&0xFF) in prot_set and mbi.RegionSize<0x8000000:
            out.append((mbi.BaseAddress,mbi.RegionSize))
        a=mbi.BaseAddress+mbi.RegionSize
    return out
def read_region(ph,b,s):
    buf=ctypes.create_string_buffer(s); g=ctypes.c_size_t()
    if not k.ReadProcessMemory(ph,ctypes.c_void_p(b),buf,s,ctypes.byref(g)): return None
    return np.frombuffer(buf.raw[:g.value&~3],dtype=np.uint32).copy()
def read_all_u32(ph,regs):
    d={}
    for b,s in regs:
        a=read_region(ph,b,s)
        if a is not None: d[b]=a
    return d
def rmem(ph,a,n):
    b=ctypes.create_string_buffer(n); g=ctypes.c_size_t()
    if not k.ReadProcessMemory(ph,ctypes.c_void_p(a),b,n,ctypes.byref(g)): return None
    return b.raw[:g.value]
def rf(ph,a):
    d=rmem(ph,a,4); return struct.unpack("<f",d)[0] if d and len(d)==4 else None
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
    def rect(s):
        for _ in range(20):
            r=wt.RECT(); u.GetClientRect(s.h,ctypes.byref(r)); p=wt.POINT(0,0); u.ClientToScreen(s.h,ctypes.byref(p))
            if r.right-r.left>8: return {"left":p.x,"top":p.y,"width":r.right-r.left,"height":r.bottom-r.top}
            time.sleep(0.1)
        raise SystemExit("no rect")
    def gray(s):
        sh=s.sct.grab(s.rect()); img=np.frombuffer(sh.bgra,np.uint8).reshape(sh.height,sh.width,4)[:,:,:3]
        return cv2.cvtColor(cv2.resize(img,(320,180)),cv2.COLOR_BGR2GRAY).astype(np.int16)

def main():
    h,ph,eb,es=attach(); time.sleep(0.3); screen=Screen(h)
    u.SetForegroundWindow(h); time.sleep(0.4)
    print(f"Warcraft III.exe база {eb:#x} (+{es:#x})")
    rw=regions(ph,RW)
    print(f"RW-регионов: {len(rw)}")

    def snap_f():   # float-снимок RW
        d={}
        for b,s in rw:
            a=read_region(ph,b,s)
            if a is not None: d[b]=a.view(np.float32)
        return d
    s0=snap_f(); time.sleep(0.6); s0b=snap_f()
    idle={}
    for b in s0:
        c=s0b.get(b)
        with np.errstate(all="ignore"):
            idle[b]=(np.isfinite(c)&np.isfinite(s0[b])&(np.abs(c.astype(np.float64)-s0[b].astype(np.float64))<1e-4)) if (c is not None and c.shape==s0[b].shape) else np.zeros(s0[b].shape,bool)
    prev=s0b
    def act(keys):
        nonlocal prev
        for vk in keys: press(vk)
        cur=snap_f(); out={}
        for b in prev:
            c=cur.get(b)
            out[b]=None if (c is None or c.shape!=prev[b].shape) else (c.astype(np.float64)-prev[b].astype(np.float64))
        prev=cur; return out,cur
    (dR1,_)=act([VK["INS"]]); (dR2,cur)=act([VK["INS"]])

    # eye-кандидаты: idle, крупная координата, монотонно меняется на обоих Insert
    eye=[]
    for b in cur:
        d1=dR1.get(b); d2=dR2.get(b)
        if d1 is None or d2 is None: continue
        with np.errstate(all="ignore"):
            val=cur[b]
            m= idle[b]&(np.abs(val)>800)&(np.abs(val)<1e5)&(np.abs(d1)>1)&(np.abs(d2)>1)&(np.abs(d1)<3000)&(np.abs(d2)<3000)&(np.sign(d1)==np.sign(d2))
        for i in np.where(m)[0]:
            eye.append(b+4*int(i))
    print(f"eye-кандидатов (крупн.коорд+вращение): {len(eye)}")
    if not eye:
        print("нет кандидатов"); k.CloseHandle(ph); return

    # индекс всех указателей в памяти -> ищем указатели, попадающие в [A-0x300, A+4] кандидатов
    eye_arr=np.array(sorted(set(eye)),dtype=np.uint64)
    lo=eye_arr-0x300; hi=eye_arr+8
    # объединяем в интервалы поиска: для каждого dword проверяем принадлежность любому [lo,hi]
    starts=lo.astype(np.uint64); ends=hi.astype(np.uint64)
    order=np.argsort(starts); starts=starts[order]; ends=ends[order]

    allregs=regions(ph,READABLE)
    static_hits={}   # eye_addr -> список статических указателей
    exe_lo,exe_hi=eb,eb+es
    def in_range(ptrs):
        idx=np.searchsorted(starts,ptrs,side="right")-1
        ok=(idx>=0)
        res=np.zeros(len(ptrs),bool)
        vi=idx[ok]
        res[ok]=ptrs[ok]<=ends[vi]
        return res, idx
    for b,s in allregs:
        arr=read_region(ph,b,s)
        if arr is None: continue
        ptrs=arr.astype(np.uint64)
        hit,idx=in_range(ptrs)
        if not hit.any(): continue
        locs=np.where(hit)[0]
        for li in locs:
            ptr_loc=b+4*int(li)
            target=int(ptrs[li])
            # какой eye-диапазон
            j=int(idx[li]); struct_base=int(starts[j])+0x300-8  # приблизительно A
            is_static = exe_lo<=ptr_loc<exe_hi
            # интересуют статические указатели exe (1 уровень)
            if is_static:
                # найдём ближайший eye-адрес в этом диапазоне
                for ea in eye_arr:
                    if int(ea)-0x300<=target<=int(ea)+8:
                        static_hits.setdefault(int(ea),[]).append((ptr_loc,target))
                        break
    print(f"eye-кандидатов, достижимых из СТАТИКИ exe (1 уровень): {len(static_hits)}")
    for ea,ptrs in list(static_hits.items())[:20]:
        v=rf(ph,ea)
        pl=ptrs[0]
        print(f"  eye@{ea:#x} val={v:.1f}  <- static [exe+{pl[0]-eb:#x}]->{pl[1]:#x} (eye=ptr+{ea-pl[1]:#x})")

    # write-тест: у каждого статического кандидата двигаем значение -> вид меняется и держится?
    print("\nwrite-тест (сдвиг координаты -> глобальное изменение вида + держится):")
    confirmed=[]
    for ea in list(static_hits)[:20]:
        v=rf(ph,ea)
        if v is None: continue
        b0=screen.gray(); wf(ph,ea,v+300.0); time.sleep(0.5); c0=screen.gray()
        back=rf(ph,ea); wf(ph,ea,v); time.sleep(0.2)
        frac=float((np.abs(c0-b0)>8).mean()); held=back is not None and abs(back-(v+300))<200
        print(f"  {ea:#x} v={v:.1f} frac={frac:.2f} held={held} {'★' if frac>0.25 and held else ''}")
        if frac>0.25 and held: confirmed.append(ea)

    out={"exe_base":eb,"exe_size":es,"static_eye":{hex(ea):[(hex(a),hex(t)) for a,t in static_hits[ea]] for ea in static_hits},"confirmed":[hex(x) for x in confirmed]}
    Path(r"d:\Games\Warcraft\vr\tools\cam129.json").write_text(json.dumps(out,indent=2),encoding="utf-8")
    print("\nсохранено cam129.json")
    k.CloseHandle(ph)

if __name__=="__main__":
    main()
