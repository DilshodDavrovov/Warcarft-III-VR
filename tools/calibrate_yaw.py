# -*- coding: utf-8 -*-
"""
Находит геометрию камеры для ЧТЕНИЯ реального угла (обратная связь):
  target(x,y) — крупные координаты, стоят при повороте, двигаются при панораме;
  eye(x,y)    — крупные координаты рядом, двигаются при повороте (орбита вокруг target).
Тогда yaw = atan2(eye_y-target_y, eye_x-target_x).
Замеряет реальную скорость вращения (град/сек) при зажатом Insert.
Сохраняет найденные адреса в vr/tools/yaw_sensor.json.
"""
import ctypes, ctypes.wintypes as wt, json, struct, time, math
from pathlib import Path
import numpy as np

u=ctypes.windll.user32; k=ctypes.windll.kernel32
try: ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception: pass
PROCESS_ALL=0x0010|0x0020|0x0008|0x0400; TH32=0x08|0x10; MEM_COMMIT=0x1000
WRITABLE={0x04,0x08,0x40,0x80}; VK={"INS":0x2D,"DEL":0x2E,"L":0x25,"R":0x27,"PGUP":0x21}; EXT={0x2D,0x2E,0x21,0x22,0x25,0x26,0x27,0x28}

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
def rfloat(ph,a):
    b=ctypes.create_string_buffer(4); g=ctypes.c_size_t()
    if not k.ReadProcessMemory(ph,ctypes.c_void_p(a),b,4,ctypes.byref(g)): return None
    return struct.unpack("<f",b.raw)[0]
def press(vk,dur):
    sc=u.MapVirtualKeyW(vk,0); fl=0x0001 if vk in EXT else 0; t0=time.time()
    while time.time()-t0<dur:
        u.keybd_event(vk,sc,fl,0); time.sleep(0.03)
    u.keybd_event(vk,sc,fl|0x0002,0); time.sleep(0.3)

def addr_of(regs_dict, base_map):
    pass

def main():
    h,ph,gb,gs=attach(); time.sleep(0.3)
    u.SetForegroundWindow(h); time.sleep(0.4)
    regs=regions(ph)
    print(f"регионов {len(regs)}")

    # снимки: baseline, после поворота, после ещё поворота, после панорамы
    s0=read_all(ph,regs); time.sleep(0.6); s0b=read_all(ph,regs)
    idle={}
    for b in s0:
        c=s0b.get(b)
        with np.errstate(all="ignore"):
            idle[b]=(np.isfinite(c)&np.isfinite(s0[b])&(np.abs(c.astype(np.float64)-s0[b].astype(np.float64))<1e-4)) if (c is not None and c.shape==s0[b].shape) else np.zeros(s0[b].shape,bool)
    base=s0b
    press(VK["INS"],0.4); rA=read_all(ph,regs)
    press(VK["INS"],0.4); rB=read_all(ph,regs)
    press(VK["L"],0.4);  press(VK["L"],0.4); rC=read_all(ph,regs)

    def d(x,y,bb):
        c=x.get(bb); p=y.get(bb)
        if c is None or p is None or c.shape!=p.shape: return None
        with np.errstate(all="ignore"): return c.astype(np.float64)-p.astype(np.float64)

    # eye: idle, крупная координата, двигается на обоих поворотах монотонно-ненулевая
    # target: idle, крупная координата, СТОИТ на поворотах, двигается на панораме
    eye_idx={}; tgt_idx={}
    for b in base:
        di1=d(rA,base,b); di2=d(rB,rA,b); dp=d(rC,rB,b)
        if di1 is None or di2 is None or dp is None: continue
        with np.errstate(all="ignore"):
            val=base[b]; coord=(np.abs(val)>1500)&(np.abs(val)<1e5)&idle[b]
            eye = coord&(np.abs(di1)>2)&(np.abs(di2)>2)&(np.abs(di1)<3000)&(np.abs(di2)<3000)
            tgt = coord&(np.abs(di1)<0.5)&(np.abs(di2)<0.5)&(np.abs(dp)>2)&(np.abs(dp)<5000)
        for i in np.where(eye)[0]: eye_idx[b+4*int(i)]=float(val[i])
        for i in np.where(tgt)[0]: tgt_idx[b+4*int(i)]=float(val[i])
    print(f"eye-координат: {len(eye_idx)}, target-координат: {len(tgt_idx)}")

    # ищем пару: target(x,y) по соседству (разница адресов 4) и eye(x,y) в пределах ±0x40
    tgt_addrs=sorted(tgt_idx); eye_addrs=set(eye_idx)
    best=None
    for ta in tgt_addrs:
        if ta+4 in tgt_idx:   # target x,y рядом
            tx,ty=ta,ta+4
            # ищем eye x,y рядом (в пределах 0x60), тоже соседние
            for ea in range(ta-0x60, ta+0x64, 4):
                if ea in eye_addrs and ea+4 in eye_addrs:
                    best=(tx,ty,ea,ea+4); break
        if best: break
    if not best:
        print("пару target+eye не нашли; target-адреса:", [hex(a) for a in tgt_addrs[:10]])
        print("eye-адреса:", [hex(a) for a in sorted(eye_addrs)[:10]])
        k.CloseHandle(ph); return
    tx,ty,ex,ey=best
    print(f"target=({tx:#x},{ty:#x}) eye=({ex:#x},{ey:#x})")

    def yaw_now():
        TX,TY,EX,EY=rfloat(ph,tx),rfloat(ph,ty),rfloat(ph,ex),rfloat(ph,ey)
        return math.degrees(math.atan2(EY-TY, EX-TX)), (TX,TY,EX,EY)

    y0,vals0=yaw_now()
    print(f"yaw сейчас={y0:.1f}°  target=({vals0[0]:.0f},{vals0[1]:.0f}) eye=({vals0[2]:.0f},{vals0[3]:.0f})")
    # калибровка скорости: держим Insert 1.0с
    t0=time.time(); press(VK["INS"],1.0); dt=1.0
    y1,_=yaw_now()
    dyaw=(y1-y0+540)%360-180
    rate=abs(dyaw)/dt
    print(f"yaw после Insert 1.0с={y1:.1f}°  -> поворот {dyaw:+.1f}°, СКОРОСТЬ ~{rate:.0f} град/сек")
    # вернём назад
    press(VK["DEL"],1.0)
    y2,_=yaw_now(); print(f"yaw после возврата={y2:.1f}°")

    out={"target_x":tx,"target_y":ty,"eye_x":ex,"eye_y":ey,
         "target_x_off":tx-gb if gb<=tx<gb+gs else None,
         "yaw_rate_deg_s":rate,"game_dll_base":gb}
    Path(r"d:\Games\Warcraft\vr\tools\yaw_sensor.json").write_text(json.dumps(out,indent=2),encoding="utf-8")
    print("сохранено yaw_sensor.json")
    k.CloseHandle(ph)

if __name__=="__main__":
    main()
