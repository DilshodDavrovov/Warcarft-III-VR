# -*- coding: utf-8 -*-
"""
Поиск структуры камеры WC3 1.26 по СТРУКТУРНОЙ сигнатуре.

1) idle-стабильные float, реагирующие монотонно на поворот (Insert/Delete).
2) СТРУКТУРНЫЙ фильтр: рядом (в ±0x60) должна лежать дистанция камеры
   (~1650 по умолчанию) И крупная мировая координата цели (>3000).
   Только у структуры камеры такое соседство; матрицы/рендер-буферы отпадают.
3) write-тест: запись угла поворачивает ВЕСЬ кадр (frac>0.25).
4) поиск статического указателя в game.dll на структуру.
"""
import ctypes, ctypes.wintypes as wt, json, struct, time
from pathlib import Path
import cv2, mss, numpy as np

u=ctypes.windll.user32; k=ctypes.windll.kernel32
try: ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception: pass
PROCESS_ALL=0x0010|0x0020|0x0008|0x0400; TH32=0x08|0x10; MEM_COMMIT=0x1000
WRITABLE={0x04,0x08,0x40,0x80}
VK={"INS":0x2D,"DEL":0x2E}; EXT={0x2D,0x2E,0x21,0x22}

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
    idle={}
    for b in s0:
        c=s1.get(b)
        with np.errstate(all="ignore"):
            idle[b]=(np.isfinite(c)&np.isfinite(s0[b])&(np.abs(c.astype(np.float64)-s0[b].astype(np.float64))<1e-4)) \
                    if (c is not None and c.shape==s0[b].shape) else np.zeros(s0[b].shape,bool)
    prev=s1
    def rotate(vk):
        nonlocal prev
        press(vk); cur=read_all(ph,regs); out={}
        for b in prev:
            c=cur.get(b)
            if c is None or c.shape!=prev[b].shape: out[b]=None
            else:
                with np.errstate(all="ignore"): out[b]=c.astype(np.float64)-prev[b].astype(np.float64)
        prev=cur; return out
    print("rot Insert #1..."); d1=rotate(VK["INS"])
    print("rot Insert #2..."); d2=rotate(VK["INS"])
    print("rot Delete   ..."); d3=rotate(VK["DEL"])

    # yaw-кандидаты: idle & монотонно на Insert & разворот на Delete & ПОСТОЯННЫЙ инкремент
    cands=[]   # (addr, v, a1,a2,a3)
    for b in prev:
        if d1[b] is None or d2[b] is None or d3[b] is None: continue
        with np.errstate(all="ignore"):
            a1,a2,a3=np.abs(d1[b]),np.abs(d2[b]),np.abs(d3[b])
            mono = idle[b] & (a1>1e-3)&(a1<1000)&(a2>1e-3)&(a2<1000)&(a3>1e-3)&(a3<1000) \
                & (np.sign(d1[b])==np.sign(d2[b])) & (np.sign(d3[b])==-np.sign(d1[b]))
            mx=np.maximum.reduce([a1,a2,a3]); mn=np.minimum.reduce([a1,a2,a3])
            consistent = mono & (mn > 0.6*mx)   # три инкремента близки (постоянная скорость)
        for i in np.where(consistent)[0]:
            cands.append((b+4*int(i), float(prev[b][i]), float(a1[i]), float(a2[i]), float(a3[i])))
    print(f"yaw-кандидатов (постоянный инкремент): {len(cands)}")

    # write-тест угла -> глобальный поворот (печатаем дельты, чтобы понять единицы)
    u.SetForegroundWindow(h); time.sleep(0.3)
    confirmed=[]
    tested=0
    for addr,v,a1,a2,a3 in cands[:120]:
        d=0.5 if abs(v)<12 else 40.0
        b0=screen.gray(); wfloat(ph,addr,v+d); time.sleep(0.45); c0=screen.gray()
        back=rfloat(ph,addr); wfloat(ph,addr,v); time.sleep(0.15)
        frac=float((np.abs(c0-b0)>8).mean())
        sticky=back is not None and abs(back-(v+d))<abs(d)*0.6+0.5
        tested+=1
        if frac>0.15 or (frac>0.25 and sticky):
            src=f"game.dll+{addr-gb:#x}" if gb<=addr<gb+gs else f"heap {addr:#x}"
            print(f"  {src:22s} v={v:9.3f} d/press~{(a1+a2+a3)/3:.3f} frac={frac:.2f} sticky={sticky} {'★КАМЕРА' if frac>0.25 and sticky else ''}")
        if frac>0.25 and sticky:
            confirmed.append((addr,v))
    print(f"протестировано {tested}")

    result={"game_dll_base":gb,"game_dll_size":gs,"cameras":[]}
    gdata=rmem(ph,gb,gs); garr=np.frombuffer(gdata[:len(gdata)&~3],dtype=np.uint32) if gdata else None
    print(f"\n=== подтверждённых камер: {len(confirmed)} ===")
    for addr,v in confirmed:
        print(f"\n-- КАМЕРА yaw@{addr:#x} val={v:.4f}; структура: --")
        blk=rmem(ph,addr-0x60,0xC0); fields=[]
        if blk:
            for i in range(0,len(blk)-3,4):
                (f,)=struct.unpack_from("<f",blk,i); off=i-0x60
                note=""
                if 1560<abs(f)<1740: note="  <== ДИСТАНЦИЯ"
                elif 3000<abs(f)<1e5: note="  ? координата цели"
                elif 0.3<abs(f)<7 and off!=0: note="  ? угол(рад)"
                elif 30<abs(f)<360 and off!=0: note="  ? угол(град)"
                mk=" <== YAW" if off==0 else ""
                if abs(f)>1e-7: print(f"     +{off:+#05x}  {f:12.3f}{mk}{note}")
                fields.append({"offset":off,"value":float(f)})
        ptrs=[]
        if garr is not None:
            base_lo=addr-0x60
            idx=np.where((garr>=base_lo)&(garr<=addr+0x8))[0]
            for i in idx[:16]:
                p=int(garr[i]); print(f"     статич.ptr game.dll+{4*int(i):#x} -> {p:#x} (yaw=ptr+{addr-p:#x})")
                ptrs.append({"gamedll_off":4*int(i),"points_to":p,"yaw_delta":addr-p})
        result["cameras"].append({"yaw_addr":addr,"yaw_value":v,"fields":fields,"static_ptrs":ptrs})
    Path(r"d:\Games\Warcraft\vr\tools\camera_addrs.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    print("\nсохранено camera_addrs.json")
    k.CloseHandle(ph)

if __name__=="__main__":
    main()
