# -*- coding: utf-8 -*-
"""
Истинное 1:1 head-tracking для Warcraft III 1.26 через КОД-ХУК в game.dll.

Механизм (найден реверсом в Ghidra):
  Покадровая функция камеры FUN_6f3063d0 читает ЦЕЛЬ поворота/наклона в стек-
  локали [ESP+0x3c]=rotation, [ESP+0x8]=AoA (из которых строится матрица вида).
  Хук в 0x6f3065a7 каждый кадр вписывает туда мой угол -> камера следует за
  головой 1:1 и держится (вид строится из моего значения каждый кадр).

Камера-объект (для нейтрали): [[game.dll+0xab4f80]+0x254], rotation=+0x5b8, AoA=+0x5b4.
Base game.dll=0x6f000000 (ASLR нет). API как camera_sync: set_pose/enable/disable/status.
"""
import ctypes, ctypes.wintypes as wt, struct, threading, time, math

user32=ctypes.windll.user32; kernel32=ctypes.windll.kernel32
kernel32.VirtualAllocEx.restype=ctypes.c_void_p
kernel32.VirtualAllocEx.argtypes=[wt.HANDLE,ctypes.c_void_p,ctypes.c_size_t,wt.DWORD,wt.DWORD]
kernel32.OpenProcess.restype=wt.HANDLE
TH32=0x08|0x10
GDLL_BASE=0x6f000000
OFF_CONTAINER=0xab4f80    # [game.dll+это] -> container; camera=[container+0x254]
OFF_CAM=0x254
OFF_ROT=0x5b8; OFF_AOA=0x5b4
HOOK_RVA=0x3065a7; BACK_RVA=0x3065ad
ORIG=b"\x8d\xbe\xa4\x05\x00\x00"   # lea edi,[esi+0x5a4]

# ------------------------- настройки -------------------------
INVERT_YAW=False
INVERT_PITCH=False
ENABLE_PITCH=True
MAX_PITCH_DEG=40.0       # ограничение наклона от нейтрали
WRITE_HZ=90
# --------------------------------------------------------------

class ME32(ctypes.Structure):
    _fields_=[("dwSize",wt.DWORD),("th32ModuleID",wt.DWORD),("th32ProcessID",wt.DWORD),
              ("GlblcntUsage",wt.DWORD),("ProccntUsage",wt.DWORD),
              ("modBaseAddr",ctypes.POINTER(ctypes.c_byte)),("modBaseSize",wt.DWORD),
              ("hModule",wt.HMODULE),("szModule",ctypes.c_char*256),("szExePath",ctypes.c_char*260)]


class HookCameraSync:
    """Драйвер камеры 1.26 через код-хук (истинное 1:1). API совместим с camera_sync."""

    def __init__(self, log=print):
        self.log=log
        self._pose=(0.0,0.0); self._pose_time=0.0
        self._enabled=False
        self._ph=None; self._gb=None
        self._cave=None; self._VR=None; self._ROT=None; self._AOA=None
        self._neutral_rot=None; self._neutral_aoa=None
        self._last_error=""
        threading.Thread(target=self._loop,daemon=True).start()

    # ---------- API ----------
    def set_pose(self, yaw, pitch):
        self._pose=(float(yaw),float(pitch)); self._pose_time=time.time()

    def recenter(self):
        # нейтраль = текущий угол камеры игры
        if self._ph:
            cam=self._camera()
            if cam:
                self._neutral_rot=self._rf(cam+OFF_ROT)
                self._neutral_aoa=self._rf(cam+OFF_AOA)

    def enable(self):
        self._enabled=True

    def disable(self):
        self._enabled=False
        if self._ph and self._VR: self._wdw(self._VR,0)

    def status(self):
        return {"enabled":self._enabled,"attached":self._ph is not None,
                "mode":"code-hook 1:1","installed":self._cave is not None,
                "error":self._last_error}

    # ---------- процесс/память ----------
    def _find_proc(self):
        h=user32.FindWindowW("Warcraft III",None)
        if not h: return None
        pid=wt.DWORD(); user32.GetWindowThreadProcessId(h,ctypes.byref(pid))
        return pid.value
    def _module_base(self,pid,name=b"game.dll"):
        snap=kernel32.CreateToolhelp32Snapshot(TH32,pid); me=ME32(); me.dwSize=ctypes.sizeof(ME32); base=None
        if kernel32.Module32First(snap,ctypes.byref(me)):
            while True:
                if me.szModule.lower()==name: base=ctypes.cast(me.modBaseAddr,ctypes.c_void_p).value; break
                if not kernel32.Module32Next(snap,ctypes.byref(me)): break
        kernel32.CloseHandle(snap); return base
    def _r(self,a,n):
        b=ctypes.create_string_buffer(n); g=ctypes.c_size_t()
        return b.raw[:g.value] if kernel32.ReadProcessMemory(self._ph,ctypes.c_void_p(a),b,n,ctypes.byref(g)) else None
    def _rdw(self,a): d=self._r(a,4); return struct.unpack("<I",d)[0] if d else None
    def _rf(self,a): d=self._r(a,4); return struct.unpack("<f",d)[0] if d else None
    def _w(self,a,data):
        n=ctypes.c_size_t()
        if not kernel32.WriteProcessMemory(self._ph,ctypes.c_void_p(a),data,len(data),ctypes.byref(n)):
            old=wt.DWORD(); kernel32.VirtualProtectEx(self._ph,ctypes.c_void_p(a),len(data),0x40,ctypes.byref(old))
            kernel32.WriteProcessMemory(self._ph,ctypes.c_void_p(a),data,len(data),ctypes.byref(n))
    def _wf(self,a,v): self._w(a,struct.pack("<f",v))
    def _wdw(self,a,v): self._w(a,struct.pack("<I",v&0xffffffff))
    def _camera(self):
        cont=self._rdw(self._gb+OFF_CONTAINER)
        if not cont: return None
        cam=self._rdw(cont+OFF_CAM)
        return cam if cam and 0x10000<cam<0x7fff0000 else None

    def _attach(self):
        pid=self._find_proc()
        if not pid: self._last_error="окно 1.26 не найдено"; return False
        ph=kernel32.OpenProcess(0x043A,False,pid)  # vm op/read/write + qi (+ create thread)
        if not ph: self._last_error="OpenProcess fail"; return False
        gb=self._module_base(pid)
        if not gb: kernel32.CloseHandle(ph); self._last_error="game.dll не найден"; return False
        self._ph=ph; self._gb=gb; self._last_error=""
        return True

    def _install(self):
        gb=self._gb
        cur=self._r(gb+HOOK_RVA,6)
        if cur is None: self._last_error="не читается код хука"; return False
        if cur[0]==0xE9:
            self._w(gb+HOOK_RVA,ORIG)   # снять старый хук перед новым
        cave=kernel32.VirtualAllocEx(self._ph,None,0x1000,0x3000,0x40)
        if not cave: self._last_error="VirtualAllocEx fail"; return False
        cave=int(cave)
        VR=cave+0x100; ROT=cave+0x104; AOA=cave+0x108
        sc=b"\xA1"+struct.pack("<I",VR)        # mov eax,[VR]
        sc+=b"\x85\xC0\x74\x12"                 # test eax,eax; jz +0x12
        sc+=b"\xA1"+struct.pack("<I",ROT)       # mov eax,[ROT]
        sc+=b"\x89\x44\x24\x3C"                 # mov [esp+0x3c],eax
        sc+=b"\xA1"+struct.pack("<I",AOA)       # mov eax,[AOA]
        sc+=b"\x89\x44\x24\x08"                 # mov [esp+0x08],eax
        sc+=ORIG                                # lea edi,[esi+0x5a4]
        sc+=b"\xE9"+struct.pack("<i",(gb+BACK_RVA)-(cave+len(sc)+5))
        self._w(cave,sc)
        cam=self._camera()
        self._neutral_rot=self._rf(cam+OFF_ROT); self._neutral_aoa=self._rf(cam+OFF_AOA)
        self._wdw(VR,0); self._wf(ROT,self._neutral_rot or 1.5708); self._wf(AOA,self._neutral_aoa or 1.48)
        self._w(gb+HOOK_RVA,b"\xE9"+struct.pack("<i",cave-(gb+HOOK_RVA+5))+b"\x90")
        self._cave,self._VR,self._ROT,self._AOA=cave,VR,ROT,AOA
        self.log("[hook] установлен cave=%#x neutral_rot=%.3f neutral_aoa=%.3f"%(cave,self._neutral_rot or 0,self._neutral_aoa or 0))
        return True

    def _uninstall(self):
        try:
            if self._ph and self._gb: self._w(self._gb+HOOK_RVA,ORIG)
        except Exception: pass
        self._cave=None

    # ---------- цикл ----------
    def _loop(self):
        period=1.0/WRITE_HZ
        while True:
            time.sleep(period)
            if not self._enabled:
                if self._cave: self._wdw(self._VR,0)
                continue
            if self._ph is None:
                if not self._attach(): time.sleep(1.0); continue
            # процесс жив?
            if self._find_proc() is None:
                self._uninstall()
                try: kernel32.CloseHandle(self._ph)
                except Exception: pass
                self._ph=None; continue
            if self._cave is None:
                if not self._install(): time.sleep(1.0); continue
            if self._neutral_rot is None:
                self.recenter()
            yaw,pitch=self._pose
            if time.time()-self._pose_time>1.0:
                # нет данных — держим нейтраль, но не выключаем
                self._wf(self._ROT,self._neutral_rot); self._wf(self._AOA,self._neutral_aoa); self._wdw(self._VR,1)
                continue
            sy=-1.0 if INVERT_YAW else 1.0
            sp=-1.0 if INVERT_PITCH else 1.0
            rot=self._neutral_rot + sy*yaw
            self._wf(self._ROT,rot)
            if ENABLE_PITCH:
                pmax=math.radians(MAX_PITCH_DEG)
                dp=max(-pmax,min(pmax,sp*pitch))
                self._wf(self._AOA,self._neutral_aoa+dp)
            self._wdw(self._VR,1)
