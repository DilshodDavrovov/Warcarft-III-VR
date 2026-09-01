# -*- coding: utf-8 -*-
"""
Идём по цепочке к объекту камеры CGameCamera:
  из натива: camera = [ jass_context + 0x254 ],  jass_context ~ [0x6faae140].
Дампим поля объекта (ищем текущие rotation/AoA/distance/target) и печатаем,
как значения меняются при повороте (Insert), чтобы опознать живые поля.
"""
import ctypes, ctypes.wintypes as wt, struct, time
u=ctypes.windll.user32; k=ctypes.windll.kernel32
def attach():
    h=u.FindWindowW("Warcraft III",None) or u.FindWindowW(None,"Warcraft III")
    pid=wt.DWORD(); u.GetWindowThreadProcessId(h,ctypes.byref(pid))
    return h,k.OpenProcess(0x0410|0x0020|0x0008,False,pid.value)
def rdw(ph,a):
    b=ctypes.create_string_buffer(4); g=ctypes.c_size_t()
    if not k.ReadProcessMemory(ph,ctypes.c_void_p(a),b,4,ctypes.byref(g)): return None
    return struct.unpack("<I",b.raw)[0]
def rf(ph,a):
    b=ctypes.create_string_buffer(4); g=ctypes.c_size_t()
    if not k.ReadProcessMemory(ph,ctypes.c_void_p(a),b,4,ctypes.byref(g)): return None
    return struct.unpack("<f",b.raw)[0]
def rmem(ph,a,n):
    b=ctypes.create_string_buffer(n); g=ctypes.c_size_t()
    if not k.ReadProcessMemory(ph,ctypes.c_void_p(a),b,n,ctypes.byref(g)): return None
    return b.raw[:g.value]
def press(vk,dur=0.5):
    sc=u.MapVirtualKeyW(vk,0); fl=0x0001
    t0=time.time()
    while time.time()-t0<dur:
        u.keybd_event(vk,sc,fl,0); time.sleep(0.03)
    u.keybd_event(vk,sc,fl|2,0); time.sleep(0.3)

def dump_struct(ph, base, label):
    print(f"\n{label}: {base:#x}")
    blk=rmem(ph,base,0x120)
    if not blk:
        print("  не читается"); return
    for i in range(0,len(blk)-3,4):
        (fv,)=struct.unpack_from("<f",blk,i); (iv,)=struct.unpack_from("<I",blk,i)
        note=""
        if 1500<abs(fv)<1800: note="  ~distance?"
        elif 250<abs(fv)<360: note="  ~AoA(град)?"
        elif 80<abs(fv)<100: note="  ~rotation(град)?"
        elif 2000<abs(fv)<1e5: note="  ~координата?"
        if 1e-6<abs(fv)<1e9:
            print(f"  +{i:#05x}  float={fv:11.3f}  u32={iv:#010x}{note}")

def main():
    h,ph=attach()
    u.SetForegroundWindow(h); time.sleep(0.3)
    for gaddr in (0x6faae140,0x6fab4f80):
        p1=rdw(ph,gaddr)
        print(f"[{gaddr:#x}] = {p1:#x}" if p1 else f"[{gaddr:#x}] = null")
        if not p1: continue
        # camera = [p1 + 0x254]
        cam=rdw(ph,p1+0x254)
        print(f"  [+0x254] = {cam:#x}" if cam else "  [+0x254] null")
        if cam and 0x10000<cam<0x7fff0000:
            dump_struct(ph,cam,f"кандидат камеры (из {gaddr:#x})")
            # проверим живость: поле, что меняется при Insert
            before=rmem(ph,cam,0x120)
            press(0x2D,0.6)  # Insert
            after=rmem(ph,cam,0x120)
            if before and after:
                print("  поля, изменившиеся при Insert:")
                for i in range(0,min(len(before),len(after))-3,4):
                    (a,)=struct.unpack_from("<f",before,i); (b,)=struct.unpack_from("<f",after,i)
                    if abs(a-b)>1e-3 and abs(a)<1e7 and abs(b)<1e7:
                        print(f"    +{i:#05x}: {a:.3f} -> {b:.3f}")
            press(0x2E,0.6)  # Delete вернуть
    k.CloseHandle(ph)

if __name__=="__main__":
    main()
