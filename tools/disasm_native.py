# -*- coding: utf-8 -*-
"""
Мини-разбор тела JASS-натива камеры: дамп байт + извлечение call-целей (E8 rel32),
чтобы найти ВНУТРЕННЮЮ камерную функцию (её и можно попытаться вызвать).
"""
import ctypes, ctypes.wintypes as wt, struct
u=ctypes.windll.user32; k=ctypes.windll.kernel32
class ME32(ctypes.Structure):
    _fields_=[("dwSize",wt.DWORD),("th32ModuleID",wt.DWORD),("th32ProcessID",wt.DWORD),
              ("GlblcntUsage",wt.DWORD),("ProccntUsage",wt.DWORD),
              ("modBaseAddr",ctypes.POINTER(ctypes.c_byte)),("modBaseSize",wt.DWORD),
              ("hModule",wt.HMODULE),("szModule",ctypes.c_char*256),("szExePath",ctypes.c_char*260)]
def attach():
    h=u.FindWindowW("Warcraft III",None) or u.FindWindowW(None,"Warcraft III")
    pid=wt.DWORD(); u.GetWindowThreadProcessId(h,ctypes.byref(pid))
    ph=k.OpenProcess(0x0410,False,pid.value)
    snap=k.CreateToolhelp32Snapshot(0x18,pid.value); me=ME32(); me.dwSize=ctypes.sizeof(ME32); gb=gs=None
    if k.Module32First(snap,ctypes.byref(me)):
        while True:
            if me.szModule.lower()==b"game.dll":
                gb=ctypes.cast(me.modBaseAddr,ctypes.c_void_p).value; gs=me.modBaseSize; break
            if not k.Module32Next(snap,ctypes.byref(me)): break
    k.CloseHandle(snap); return ph,gb,gs
def read(ph,a,n):
    b=ctypes.create_string_buffer(n); g=ctypes.c_size_t()
    if not k.ReadProcessMemory(ph,ctypes.c_void_p(a),b,n,ctypes.byref(g)): return None
    return b.raw[:g.value]

def calls_in(ph,gb,gs,func,n=200,depth=0,seen=None):
    if seen is None: seen=set()
    if func in seen or depth>2: return
    seen.add(func)
    b=read(ph,func,n)
    if not b: return
    indent="  "*depth
    print(f"{indent}функция {func:#x} (RVA +{func-gb:#x}):")
    print(f"{indent}  байты: {b[:48].hex(' ')}")
    targets=[]
    i=0
    while i<len(b)-5:
        if b[i]==0xE8:  # call rel32
            rel=struct.unpack_from("<i",b,i+1)[0]
            tgt=(func+i+5+rel)&0xffffffff
            if gb<=tgt<gb+gs:
                targets.append((func+i,tgt))
            i+=5; continue
        if b[i]==0xC3 or b[i]==0xC2:  # ret
            break
        i+=1
    for site,t in targets:
        print(f"{indent}  call @{site:#x} -> {t:#x} (+{t-gb:#x})")
    return targets

def main():
    ph,gb,gs=attach()
    print(f"game.dll {gb:#x}")
    # адреса из find_natives (RVA)
    for name,rva in [("SetCameraField",0x3b4820),("SetCameraPosition",0x3b86f0)]:
        print(f"\n===== {name} =====")
        calls_in(ph,gb,gs,gb+rva,n=160)
    # для SetCameraField разберём вызываемые функции на глубину
    print("\n===== углубление SetCameraField =====")
    tg=calls_in(ph,gb,gs,gb+0x3b4820,n=160)
    if tg:
        for site,t in tg:
            calls_in(ph,gb,gs,t,n=120,depth=1)
    k.CloseHandle(ph)
if __name__=="__main__":
    main()
