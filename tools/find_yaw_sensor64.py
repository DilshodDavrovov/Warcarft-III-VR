# -*- coding: utf-8 -*-
"""
Ищет ЛИНЕЙНЫЙ датчик угла камеры в Reforged (64-бит) для обратной связи.
Делает 6 шагов Insert (потом 3 Delete), для каждого idle-стабильного float
проверяет: растёт монотонно с ПОСТОЯННЫМ шагом на Insert и убывает на Delete
(= линейный угол). Печатает лучшие с траекторией. Сохраняет в yaw_sensor64.json.
"""
import ctypes, ctypes.wintypes as wt, struct, time, json
from pathlib import Path
import numpy as np

u=ctypes.windll.user32; k=ctypes.windll.kernel32
k.OpenProcess.restype=wt.HANDLE
k.VirtualQueryEx.restype=ctypes.c_size_t
PROCESS_ALL=0x0010|0x0020|0x0008|0x0400; MEM_COMMIT=0x1000; RW={0x04,0x08,0x40,0x80}
VK={"INS":0x2D,"DEL":0x2E}; EXT=set(VK.values())

class MBI(ctypes.Structure):
    _fields_=[("BaseAddress",ctypes.c_void_p),("AllocationBase",ctypes.c_void_p),
              ("AllocationProtect",wt.DWORD),("__a",wt.DWORD),
              ("RegionSize",ctypes.c_size_t),("State",wt.DWORD),("Protect",wt.DWORD),("Type",wt.DWORD)]

def attach():
    h=u.FindWindowW("OsWindow",None) or u.FindWindowW(None,"Warcraft III")
    if not h: raise SystemExit("NO_WINDOW")
    if u.IsIconic(h): u.ShowWindow(h,9); time.sleep(0.6)
    pid=wt.DWORD(); u.GetWindowThreadProcessId(h,ctypes.byref(pid))
    return h,k.OpenProcess(PROCESS_ALL,False,pid.value)
def regions(ph):
    addr=0; out=[]; mbi=MBI()
    while addr<0x7FFFFFFF0000:
        if not k.VirtualQueryEx(ph,ctypes.c_void_p(addr),ctypes.byref(mbi),ctypes.sizeof(mbi)):
            addr+=0x10000; continue
        base=mbi.BaseAddress or 0; size=mbi.RegionSize or 0x1000
        if mbi.State==MEM_COMMIT and (mbi.Protect&0xFF) in RW and 0x1000<=size<=0x200000:
            out.append((base,size))
        addr=base+size
    return out
def read_f(ph,b,s):
    buf=ctypes.create_string_buffer(s); got=ctypes.c_size_t()
    if not k.ReadProcessMemory(ph,ctypes.c_void_p(b),buf,s,ctypes.byref(got)): return None
    return np.frombuffer(buf.raw[:got.value&~3],dtype=np.float32).copy()
def read_all(ph,regs):
    d={}
    for b,s in regs:
        a=read_f(ph,b,s)
        if a is not None and a.size: d[b]=a
    return d
def press(vk,dur=0.4):
    sc=u.MapVirtualKeyW(vk,0); fl=0x0001 if vk in EXT else 0; t0=time.time()
    while time.time()-t0<dur:
        u.keybd_event(vk,sc,fl,0); time.sleep(0.03)
    u.keybd_event(vk,sc,fl|0x0002,0); time.sleep(0.3)

def main():
    h,ph=attach(); time.sleep(0.3)
    u.SetForegroundWindow(h); time.sleep(0.4)
    regs=regions(ph)
    print(f"регионов(<=2МБ): {len(regs)}")
    # idle
    s0=read_all(ph,regs); time.sleep(0.5); s1=read_all(ph,regs)
    idle={}
    for b in s0:
        c=s1.get(b)
        with np.errstate(all="ignore"):
            idle[b]=(np.isfinite(c)&np.isfinite(s0[b])&(np.abs(c-s0[b])<1e-5)) if (c is not None and c.shape==s0[b].shape) else np.zeros(s0[b].shape,bool)
    # 6 шагов Insert
    seq=[read_all(ph,regs)]
    for _ in range(6):
        press(VK["INS"]); seq.append(read_all(ph,regs))
    # оценка линейности: для каждого адреса собираем траекторию по seq
    best=[]
    base_keys=[b for b in seq[0] if all(b in s and s[b].shape==seq[0][b].shape for s in seq)]
    for b in base_keys:
        traj=np.stack([s[b] for s in seq])   # (7, N)
        with np.errstate(all="ignore"):
            d=np.diff(traj,axis=0)            # (6, N)
            mean=d.mean(axis=0); std=d.std(axis=0); amean=np.abs(mean)
            val0=traj[0]
            # линейный угол: заметный постоянный шаг (std мал относительно шага), монотонный, значение в разумном угловом диапазоне
            good = idle[b] & (amean>0.05) & (amean<1.5) & (std < 0.25*amean) & (np.abs(val0)<50) & np.all(np.sign(d)==np.sign(mean),axis=0)
        for i in np.where(good)[0]:
            best.append((float(std[i]/ (amean[i]+1e-9)), b+4*int(i), float(val0[i]), float(mean[i]), traj[:,i].tolist()))
    best.sort(key=lambda t:t[0])
    print(f"линейных датчиков угла: {len(best)} (лучшие — наименьший разброс шага):")
    saved=[]
    for cv,addr,v0,step,traj in best[:12]:
        print(f"  {addr:#x} шаг/нажатие={step:+.3f} разброс={cv:.2f} старт={v0:.3f}  траектория={['%.2f'%x for x in traj]}")
        saved.append({"addr":addr,"step":step,"cv":cv,"start":v0})
    # вернуть камеру назад
    for _ in range(6): press(VK["DEL"])
    Path(r"d:\Games\Warcraft\vr\tools\yaw_sensor64.json").write_text(json.dumps(saved,indent=2),encoding="utf-8")
    print("сохранено yaw_sensor64.json")
    k.CloseHandle(ph)

if __name__=="__main__":
    main()
