# -*- coding: utf-8 -*-
"""
1.26: резолвит объект камеры по статической цепочке из Ghidra:
   камера = [[game.dll+0xab4f80] + 0x254]
Дампит объект и мини-дифф-сканом (Insert/PageUp/Delete) находит смещения
поворота / наклона(AoA) / и т.д. прямо внутри объекта камеры.
"""
import ctypes, ctypes.wintypes as wt, struct, time
u=ctypes.windll.user32; k=ctypes.windll.kernel32
PROCESS_ALL=0x0010|0x0020|0x0008|0x0400; TH32=0x08|0x10
VK={"INS":0x2D,"DEL":0x2E,"PGUP":0x21,"PGDN":0x22}; EXT=set(VK.values())

class ME32(ctypes.Structure):
    _fields_=[("dwSize",wt.DWORD),("th32ModuleID",wt.DWORD),("th32ProcessID",wt.DWORD),
              ("GlblcntUsage",wt.DWORD),("ProccntUsage",wt.DWORD),
              ("modBaseAddr",ctypes.POINTER(ctypes.c_byte)),("modBaseSize",wt.DWORD),
              ("hModule",wt.HMODULE),("szModule",ctypes.c_char*256),("szExePath",ctypes.c_char*260)]

def attach():
    h=u.FindWindowW("Warcraft III",None)
    if not h: raise SystemExit("окно 1.26 не найдено")
    if u.IsIconic(h): u.ShowWindow(h,9); time.sleep(0.5)
    pid=wt.DWORD(); u.GetWindowThreadProcessId(h,ctypes.byref(pid))
    ph=k.OpenProcess(PROCESS_ALL,False,pid.value)
    snap=k.CreateToolhelp32Snapshot(TH32,pid.value); me=ME32(); me.dwSize=ctypes.sizeof(ME32); gb=None
    if k.Module32First(snap,ctypes.byref(me)):
        while True:
            if me.szModule.lower()==b"game.dll":
                gb=ctypes.cast(me.modBaseAddr,ctypes.c_void_p).value; break
            if not k.Module32Next(snap,ctypes.byref(me)): break
    k.CloseHandle(snap)
    return h,ph,gb
def rdw(ph,a):
    b=ctypes.create_string_buffer(4); g=ctypes.c_size_t()
    if not k.ReadProcessMemory(ph,ctypes.c_void_p(a),b,4,ctypes.byref(g)): return None
    return struct.unpack("<I",b.raw)[0]
def rmem(ph,a,n):
    b=ctypes.create_string_buffer(n); g=ctypes.c_size_t()
    if not k.ReadProcessMemory(ph,ctypes.c_void_p(a),b,n,ctypes.byref(g)): return None
    return b.raw[:g.value]
def press(vk,dur=0.5):
    sc=u.MapVirtualKeyW(vk,0); fl=0x0001 if vk in EXT else 0; t0=time.time()
    while time.time()-t0<dur:
        u.keybd_event(vk,sc,fl,0); time.sleep(0.03)
    u.keybd_event(vk,sc,fl|0x0002,0); time.sleep(0.35)

def floats(blk):
    return [struct.unpack_from("<f",blk,i)[0] for i in range(0,len(blk)-3,4)]

def main():
    h,ph,gb=attach()
    print("game.dll base = %#x" % gb)
    container_ptr = gb+0xab4f80
    container = rdw(ph, container_ptr)
    print("[game.dll+0xab4f80] = %#x" % (container or 0))
    if not container: raise SystemExit("контейнер пуст (не в матче?)")
    cam = rdw(ph, container+0x254)
    print("камера = [container+0x254] = %#x" % (cam or 0))
    if not cam or not (0x10000<cam<0x7fff0000):
        raise SystemExit("камера не резолвится")

    N=0x800
    def ensure_focus():
        if u.IsIconic(h): u.ShowWindow(h,9); time.sleep(0.4)
        u.SetForegroundWindow(h); time.sleep(0.2)
    ensure_focus(); time.sleep(0.3)
    base_blk=rmem(ph,cam,N)
    print("\n=== поля вокруг цели камеры (+0x590..+0x5d0) ===")
    for i in range(0x590,0x5d4,4):
        fv=struct.unpack_from("<f",base_blk,i)[0]
        print("  +%#05x: float=%12.4f"%(i,fv))
    def diff_after(keys, label):
        ensure_focus()
        before=rmem(ph,cam,N)
        for vk in keys: press(vk)
        after=rmem(ph,cam,N)
        changed=[]
        for i in range(0,min(len(before),len(after))-3,4):
            bi=struct.unpack_from("<I",before,i)[0]; ai=struct.unpack_from("<I",after,i)[0]
            if bi!=ai:
                bf=struct.unpack_from("<f",before,i)[0]; af=struct.unpack_from("<f",after,i)[0]
                changed.append((i,bi,ai,bf,af))
        print("\n--- изменения при %s: %d полей ---" % (label, len(changed)))
        for i,bi,ai,bf,af in changed:
            print("  +%#05x: float %.4f->%.4f (d=%+.4f)"%(i,bf,af,af-bf))
    print("\n=== дамп объекта камеры (ненулевые float) ===")
    bf=floats(base_blk)
    for i in range(len(bf)):
        if 1e-6<abs(bf[i])<1e7:
            note=""
            if 1500<abs(bf[i])<1800: note="  ~distance?"
            elif 250<abs(bf[i])<360: note="  ~AoA(deg)?"
            elif 80<abs(bf[i])<100: note="  ~rot(deg)?"
            elif 0.3<abs(bf[i])<6.5: note="  ~angle(rad)?"
            elif 2000<abs(bf[i])<1e5: note="  ~coord?"
            print("  +%#05x: %12.4f%s"%(i*4, bf[i], note))
    diff_after([VK["INS"]], "Insert (поворот влево)")
    diff_after([VK["DEL"]], "Delete (поворот вправо, возврат)")
    diff_after([VK["PGUP"]], "PageUp (наклон)")
    diff_after([VK["PGDN"]], "PageDown (наклон назад)")
    k.CloseHandle(ph)
    print("\nготово")

if __name__=="__main__":
    main()
