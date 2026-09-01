# -*- coding: utf-8 -*-
"""
КОД-ХУК камеры WC3 1.26 (истинное 1:1, без клавиш).
Перехватывает FUN_6f3063d0 @ 0x6f3065a7 и вписывает мой угол поворота в
[ESP+0x3c] (rotation goal), из которого строится матрица вида.

Cave (rot-only):
  A1 [vr]         mov eax,[vr_enabled]
  85 C0           test eax,eax
  74 09           jz +9 -> lea
  A1 [rot]        mov eax,[rot_global]
  89 44 24 3C     mov [esp+0x3c],eax
  8D BE A4 05 00 00  lea edi,[esi+0x5a4]   (оригинал)
  E9 rel32        jmp 0x6f3065ad
Глобали: vr_enabled @ cave+0x100, rot_global @ cave+0x104.
Патч @0x6f3065a7: E9 rel32(cave) + 90.

Тест: включаем vr, ставим rot=neutral+45°, скрин; neutral; проверяем поворот+держится.
"""
import ctypes, ctypes.wintypes as wt, struct, time, math, sys
import mss, numpy as np, cv2
u=ctypes.windll.user32; k=ctypes.windll.kernel32
try: ctypes.windll.shcore.SetProcessDpiAwareness(2)
except: pass
k.VirtualAllocEx.restype=ctypes.c_void_p
k.VirtualAllocEx.argtypes=[wt.HANDLE,ctypes.c_void_p,ctypes.c_size_t,wt.DWORD,wt.DWORD]
k.OpenProcess.restype=wt.HANDLE
TH32=0x08|0x10
HOOK=0x3065a7; BACK=0x3065ad; ORIG=b"\x8d\xbe\xa4\x05\x00\x00"  # lea edi,[esi+0x5a4]
class ME32(ctypes.Structure):
    _fields_=[("dwSize",wt.DWORD),("th32ModuleID",wt.DWORD),("th32ProcessID",wt.DWORD),
              ("GlblcntUsage",wt.DWORD),("ProccntUsage",wt.DWORD),
              ("modBaseAddr",ctypes.POINTER(ctypes.c_byte)),("modBaseSize",wt.DWORD),
              ("hModule",wt.HMODULE),("szModule",ctypes.c_char*256),("szExePath",ctypes.c_char*260)]
def attach():
    h=u.FindWindowW("Warcraft III",None)
    if not h: raise SystemExit("нет окна 1.26")
    if u.IsIconic(h): u.ShowWindow(h,9); time.sleep(0.5)
    pid=wt.DWORD(); u.GetWindowThreadProcessId(h,ctypes.byref(pid))
    ph=k.OpenProcess(0x043A,False,pid.value)  # VM op/read/write + create thread + qi
    snap=k.CreateToolhelp32Snapshot(TH32,pid.value); me=ME32(); me.dwSize=ctypes.sizeof(ME32); gb=None
    if k.Module32First(snap,ctypes.byref(me)):
        while True:
            if me.szModule.lower()==b"game.dll": gb=ctypes.cast(me.modBaseAddr,ctypes.c_void_p).value; break
            if not k.Module32Next(snap,ctypes.byref(me)): break
    k.CloseHandle(snap); return h,ph,gb
def r(ph,a,n):
    b=ctypes.create_string_buffer(n); g=ctypes.c_size_t()
    return b.raw[:g.value] if k.ReadProcessMemory(ph,ctypes.c_void_p(a),b,n,ctypes.byref(g)) else None
def rdw(ph,a): d=r(ph,a,4); return struct.unpack("<I",d)[0] if d else None
def rf(ph,a): d=r(ph,a,4); return struct.unpack("<f",d)[0] if d else None
def w(ph,a,data):
    n=ctypes.c_size_t()
    ok=k.WriteProcessMemory(ph,ctypes.c_void_p(a),data,len(data),ctypes.byref(n))
    if not ok:
        old=wt.DWORD(); k.VirtualProtectEx(ph,ctypes.c_void_p(a),len(data),0x40,ctypes.byref(old))
        ok=k.WriteProcessMemory(ph,ctypes.c_void_p(a),data,len(data),ctypes.byref(n))
    return bool(ok)
def wf(ph,a,v): w(ph,a,struct.pack("<f",v))
def wdw(ph,a,v): w(ph,a,struct.pack("<I",v&0xffffffff))
def grab(h):
    r_=wt.RECT(); u.GetClientRect(h,ctypes.byref(r_)); p=wt.POINT(0,0); u.ClientToScreen(h,ctypes.byref(p))
    with mss.mss() as s: sh=s.grab({"left":p.x,"top":p.y,"width":r_.right,"height":r_.bottom})
    return cv2.cvtColor(cv2.resize(np.frombuffer(sh.bgra,np.uint8).reshape(sh.height,sh.width,4)[:,:,:3],(320,180)),cv2.COLOR_BGR2GRAY).astype(np.int16)

def install_hook(ph, gb):
    # если уже пропатчено (E9) — восстановим оригинал перед новым хуком
    cur=r(ph,gb+HOOK,6)
    if cur[0]==0xE9:
        w(ph,gb+HOOK,ORIG); print("восстановил старый хук -> оригинал")
    cave=k.VirtualAllocEx(ph,None,0x1000,0x3000,0x40)  # MEM_COMMIT|RESERVE, RWX
    if not cave: raise SystemExit("VirtualAllocEx fail")
    cave=int(cave)
    VR=cave+0x100; ROT=cave+0x104; CNT=cave+0x108
    sc=b""
    sc+=b"\xFF\x05"+struct.pack("<I",CNT)     # inc dword [counter]
    sc+=b"\xA1"+struct.pack("<I",VR)          # mov eax,[vr]
    sc+=b"\x85\xC0"                            # test eax,eax
    sc+=b"\x74\x09"                            # jz +9
    sc+=b"\xA1"+struct.pack("<I",ROT)          # mov eax,[rot]
    sc+=b"\x89\x44\x24\x3C"                    # mov [esp+0x3c],eax
    sc+=ORIG                                   # lea edi,[esi+0x5a4]
    jmp_src=cave+len(sc)
    rel_back=(gb+BACK)-(jmp_src+5)
    sc+=b"\xE9"+struct.pack("<i",rel_back)     # jmp back
    w(ph,cave,sc)
    wdw(ph,VR,0); wf(ph,ROT,0.0); wdw(ph,CNT,0)
    rel_hook=cave-(gb+HOOK+5)
    patch=b"\xE9"+struct.pack("<i",rel_hook)+b"\x90"
    w(ph,gb+HOOK,patch)
    print("cave=%#x VR=%#x ROT=%#x CNT=%#x патч@%#x"%(cave,VR,ROT,CNT,gb+HOOK))
    return cave,VR,ROT,CNT

def press(vk,dur):
    sc=u.MapVirtualKeyW(vk,0); fl=0x0001; t0=time.time()
    while time.time()-t0<dur: u.keybd_event(vk,sc,fl,0); time.sleep(0.03)
    u.keybd_event(vk,sc,fl|0x0002,0)
def main():
    h,ph,gb=attach(); u.SetForegroundWindow(h); time.sleep(0.4)
    cont=rdw(ph,gb+0xab4f80); cam=rdw(ph,cont+0x254)
    neutral=rf(ph,cam+0x5b8)
    print("камера=%#x neutral_rot=%.4f (%.0f deg)"%(cam,neutral,math.degrees(neutral)))
    cave,VR,ROT,CNT=install_hook(ph,gb)
    time.sleep(0.3)
    # 1) частота вызова хука в ПОКОЕ
    wdw(ph,CNT,0); time.sleep(1.0); idle_hits=rdw(ph,CNT)
    print("\nхук-попаданий за 1с В ПОКОЕ: %d"%idle_hits)
    # 2) частота при движении камеры (Insert)
    wdw(ph,CNT,0); press(0x2D,1.0); move_hits=rdw(ph,CNT)
    print("хук-попаданий за 1с при Insert: %d"%move_hits)
    press(0x2E,0.6)
    # 3) тест: VR on, rot=+45, + короткий Insert чтобы форсировать перестройку
    print("\n=== тест: VR on rot=+45 (+тычок Insert для перестройки) ===")
    a=grab(h)
    wf(ph,ROT,neutral+math.radians(45)); wdw(ph,VR,1)
    press(0x2D,0.15)   # форсируем вызов FUN_6f3063d0
    time.sleep(0.4); b=grab(h)
    print("frac=%.2f -> %s"%(float((np.abs(b-a)>8).mean()),"ПОВЕРНУЛСЯ" if float((np.abs(b-a)>8).mean())>0.2 else "нет"))
    wf(ph,ROT,neutral); wdw(ph,VR,0)
    press(0x2D,0.15)
    print("\nхук оставлен установленным, VR off. Откат: запусти с restore.")
    if len(sys.argv)>1 and sys.argv[1]=="restore":
        w(ph,gb+HOOK,ORIG); print("хук СНЯТ (оригинал восстановлен)")
    k.CloseHandle(ph)
if __name__=="__main__": main()
