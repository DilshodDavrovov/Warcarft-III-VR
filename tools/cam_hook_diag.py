# -*- coding: utf-8 -*-
"""Диагностика код-хука: total-счётчик, write-счётчик, ESI(камера функции), readback +0x5b8."""
import ctypes, ctypes.wintypes as wt, struct, time, math, sys
u=ctypes.windll.user32; k=ctypes.windll.kernel32
k.VirtualAllocEx.restype=ctypes.c_void_p
k.VirtualAllocEx.argtypes=[wt.HANDLE,ctypes.c_void_p,ctypes.c_size_t,wt.DWORD,wt.DWORD]
k.OpenProcess.restype=wt.HANDLE
TH32=0x08|0x10; HOOK=0x3065a7; BACK=0x3065ad; ORIG=b"\x8d\xbe\xa4\x05\x00\x00"
class ME32(ctypes.Structure):
    _fields_=[("dwSize",wt.DWORD),("th32ModuleID",wt.DWORD),("th32ProcessID",wt.DWORD),
              ("GlblcntUsage",wt.DWORD),("ProccntUsage",wt.DWORD),
              ("modBaseAddr",ctypes.POINTER(ctypes.c_byte)),("modBaseSize",wt.DWORD),
              ("hModule",wt.HMODULE),("szModule",ctypes.c_char*256),("szExePath",ctypes.c_char*260)]
def attach():
    h=u.FindWindowW("Warcraft III",None)
    if u.IsIconic(h): u.ShowWindow(h,9); time.sleep(0.5)
    pid=wt.DWORD(); u.GetWindowThreadProcessId(h,ctypes.byref(pid))
    ph=k.OpenProcess(0x043A,False,pid.value)
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
    if not k.WriteProcessMemory(ph,ctypes.c_void_p(a),data,len(data),ctypes.byref(n)):
        old=wt.DWORD(); k.VirtualProtectEx(ph,ctypes.c_void_p(a),len(data),0x40,ctypes.byref(old))
        k.WriteProcessMemory(ph,ctypes.c_void_p(a),data,len(data),ctypes.byref(n))
def wf(ph,a,v): w(ph,a,struct.pack("<f",v))
def wdw(ph,a,v): w(ph,a,struct.pack("<I",v&0xffffffff))
def main():
    h,ph,gb=attach(); u.SetForegroundWindow(h); time.sleep(0.3)
    cont=rdw(ph,gb+0xab4f80); cam=rdw(ph,cont+0x254); neutral=rf(ph,cam+0x5b8)
    print("МОЯ камера(chain)=%#x neutral=%.4f"%(cam,neutral))
    if r(ph,gb+HOOK,1)[0]==0xE9: w(ph,gb+HOOK,ORIG); print("снял старый хук")
    cave=int(k.VirtualAllocEx(ph,None,0x1000,0x3000,0x40))
    VR=cave+0x100; ROT=cave+0x104; CNT=cave+0x108; CAMSEEN=cave+0x10c; WCNT=cave+0x110
    sc=b""
    sc+=b"\xFF\x05"+struct.pack("<I",CNT)      # inc [CNT]
    sc+=b"\x89\x35"+struct.pack("<I",CAMSEEN)  # mov [CAMSEEN],esi
    sc+=b"\xA1"+struct.pack("<I",VR)           # mov eax,[VR]
    sc+=b"\x85\xC0\x74\x0F"                     # test eax,eax; jz +0x0f
    sc+=b"\xA1"+struct.pack("<I",ROT)          # mov eax,[ROT]
    sc+=b"\x89\x44\x24\x3C"                     # mov [esp+0x3c],eax
    sc+=b"\xFF\x05"+struct.pack("<I",WCNT)     # inc [WCNT]
    sc+=ORIG
    jmp_src=cave+len(sc); sc+=b"\xE9"+struct.pack("<i",(gb+BACK)-(jmp_src+5))
    w(ph,cave,sc)
    for a in (VR,ROT,CNT,CAMSEEN,WCNT): wdw(ph,a,0)
    w(ph,gb+HOOK,b"\xE9"+struct.pack("<i",cave-(gb+HOOK+5))+b"\x90")
    print("cave=%#x установлен"%cave)
    time.sleep(0.5)
    wdw(ph,CNT,0); wdw(ph,WCNT,0); wf(ph,ROT,neutral+0.6); wdw(ph,VR,1)
    time.sleep(1.0)
    print("\nVR=1, ROT=neutral+0.6 (%.4f):"%(neutral+0.6))
    print("  total hits/сек =",rdw(ph,CNT))
    print("  WRITE hits/сек =",rdw(ph,WCNT))
    seen=rdw(ph,CAMSEEN); print("  ESI(камера функции)=%#x  == моя chain? %s"%(seen, seen==cam))
    print("  camera+0x5b8 сейчас=%.4f (ожид %.4f если хук пишет)"%(rf(ph,cam+0x5b8),neutral+0.6))
    if seen and seen!=cam:
        print("  ESI+0x5b8=%.4f  ESI режим+0x38=%s"%(rf(ph,seen+0x5b8),rdw(ph,seen+0x38)))
    wdw(ph,VR,0); w(ph,gb+HOOK,ORIG); print("\nхук снят (оригинал восстановлен)")
    k.CloseHandle(ph)
if __name__=="__main__": main()
