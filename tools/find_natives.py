# -*- coding: utf-8 -*-
"""
Извлекает адреса камерных JASS-нативов из таблицы регистрации game.dll 1.26.

WC3 регистрирует нативы структурами вида {const char* name, void* func}
(иногда с прототипом-строкой между ними). Находим ASCII-имя натива в памяти
game.dll, ищем указатель на него, рядом — указатель в .text (это функция).
"""
import ctypes, ctypes.wintypes as wt, struct
import numpy as np

u=ctypes.windll.user32; k=ctypes.windll.kernel32
PROCESS_QI_VM=0x0400|0x0010; TH32=0x08|0x10
MEM_COMMIT=0x1000; EXEC={0x10,0x20,0x40,0x80}   # PAGE_EXECUTE*

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
    if not h: raise SystemExit("NO_WINDOW — запусти игру и зайди в матч")
    pid=wt.DWORD(); u.GetWindowThreadProcessId(h,ctypes.byref(pid))
    ph=k.OpenProcess(PROCESS_QI_VM,False,pid.value)
    snap=k.CreateToolhelp32Snapshot(TH32,pid.value); me=ME32(); me.dwSize=ctypes.sizeof(ME32); gb=gs=None
    if k.Module32First(snap,ctypes.byref(me)):
        while True:
            if me.szModule.lower()==b"game.dll":
                gb=ctypes.cast(me.modBaseAddr,ctypes.c_void_p).value; gs=me.modBaseSize; break
            if not k.Module32Next(snap,ctypes.byref(me)): break
    k.CloseHandle(snap)
    if not gb: raise SystemExit("game.dll не найден")
    return ph,gb,gs

def read(ph,a,n):
    b=ctypes.create_string_buffer(n); g=ctypes.c_size_t()
    if not k.ReadProcessMemory(ph,ctypes.c_void_p(a),b,n,ctypes.byref(g)): return None
    return b.raw[:g.value]

def exec_ranges(ph,gb,gs):
    out=[]; a=gb; mbi=MBI()
    while a<gb+gs:
        if not k.VirtualQueryEx(ph,ctypes.c_void_p(a),ctypes.byref(mbi),ctypes.sizeof(mbi)): break
        if mbi.State==MEM_COMMIT and (mbi.Protect&0xFF) in EXEC:
            out.append((mbi.BaseAddress,mbi.BaseAddress+mbi.RegionSize))
        a=mbi.BaseAddress+mbi.RegionSize
    return out

def main():
    ph,gb,gs=attach()
    print(f"game.dll {gb:#x} (+{gs:#x})")
    data=read(ph,gb,gs)
    if not data: raise SystemExit("не прочитать game.dll")
    ex=exec_ranges(ph,gb,gs)
    print("исполняемые диапазоны:", [(hex(a),hex(b)) for a,b in ex])
    def is_code(p): return any(a<=p<b for a,b in ex)

    names=[b"SetCameraField",b"SetCameraPosition",b"SetCameraTargetController",
           b"CameraSetupApplyForceDuration",b"SetCameraRotateMode",b"CameraSetupSetField",
           b"SetCameraQuickPosition",b"SetCameraBounds",b"PanCameraTo",
           b"SetCameraFieldForPlayer",b"CameraSetupApplyForceDurationSmooth"]

    def find_all(sub):
        out=[]; i=data.find(sub)
        while i>=0:
            out.append(i); i=data.find(sub,i+1)
        return out

    for nm in names[:6]:
        pos=data.find(nm+b"\x00")
        if pos<0:
            print(f"\n{nm.decode()}: строка не найдена"); continue
        str_va=gb+pos
        packed=struct.pack("<I",str_va)
        refs=find_all(packed)
        print(f"\n{nm.decode()}  строка@{str_va:#x}  ссылок:{len(refs)}")
        for r in refs:
            ref_va=gb+r
            aligned = (r%4==0)
            # контекст: 8 dword до и после места ссылки (если выровнено — это запись таблицы)
            lo=(r//4)*4-16
            ctx=[]
            for off in range(lo, lo+48, 4):
                if 0<=off<len(data)-3:
                    val=struct.unpack_from("<I",data,off)[0]
                    tag=""
                    if off==r: tag="<-имя"
                    elif is_code(val): tag="(код!)"
                    elif gb<=val<gb+gs: tag="(->gamedll)"
                    ctx.append(f"    +{off-r:+03d} {val:#010x} {tag}")
            print(f"  ссылка@{ref_va:#x} aligned={aligned}")
            print("\n".join(ctx))
    k.CloseHandle(ph)

if __name__=="__main__":
    main()
