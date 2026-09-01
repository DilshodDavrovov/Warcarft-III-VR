# -*- coding: utf-8 -*-
"""
Истинная СВОБОДНАЯ камера для Warcraft III 1.26 через кинематографический
сеттер FUN_6f305a60 (то, чем кат-сцены двигают камеру без мелейного клампа).

Найдено реверсом (Ghidra): SetCameraField native (FUN_6f3b48b0) вызывает
  FUN_6f305a60(this=camera)(int field, float value_deg, float duration, int flag)
Поля: 0=distance, 2=angle_of_attack, 5=rotation. Значения в ГРАДУСАХ (flag=1 -> рад).
Это НЕ клампится (в отличие от геймплейной камеры) — поворот на все 360°.

Реализация: инжектим в игру РЕЗИДЕНТНЫЙ поток, который ~90/сек читает мои
глобали (rotation/aoa/distance/enable) и вызывает FUN_6f305a60. Сервер пишет
глобали из позы головы. Камера = [[game.dll+0xab4f80]+0x254].

ВНИМАНИЕ: патчит/инжектит код -> ТОЛЬКО ОФЛАЙН, чистый war3.exe (1.26).
"""
import ctypes, ctypes.wintypes as wt, struct, threading, time, math

user32=ctypes.windll.user32; kernel32=ctypes.windll.kernel32
kernel32.VirtualAllocEx.restype=ctypes.c_void_p
kernel32.VirtualAllocEx.argtypes=[wt.HANDLE,ctypes.c_void_p,ctypes.c_size_t,wt.DWORD,wt.DWORD]
kernel32.OpenProcess.restype=wt.HANDLE
kernel32.CreateRemoteThread.restype=wt.HANDLE
kernel32.CreateRemoteThread.argtypes=[wt.HANDLE,ctypes.c_void_p,ctypes.c_size_t,ctypes.c_void_p,ctypes.c_void_p,wt.DWORD,ctypes.POINTER(wt.DWORD)]
TH32=0x08|0x10
GDLL_BASE=0x6f000000
CONTAINER_ADDR=GDLL_BASE+0xab4f80      # [это] -> container; camera=[container+0x254]
CAM_OFF=0x254
SETFIELD=GDLL_BASE+0x305a60            # FUN_6f305a60 (поле камеры)
SETPOS=GDLL_BASE+0x3078b0              # FUN_6f3078b0 (позиция цели камеры x,y)
OFF_ROT=0x5b8; OFF_AOA=0x5b4; OFF_DIST=0x5b0
OFF_TGTX=0x5a4; OFF_TGTY=0x5a8
# границы цели камеры (прямоугольник карты), заполняются игрой:
OFF_BND_MINX=0x4cc; OFF_BND_MINY=0x4d0; OFF_BND_MAXX=0x4d4; OFF_BND_MAXY=0x4d8
BND_MARGIN=128.0                 # отступ от границы, чтобы не крашить

# ------------------------- настройки -------------------------
INVERT_YAW=False
INVERT_PITCH=True                # если наклон головы работает наоборот — True
ENABLE_PITCH=True
NEUTRAL_AOA=300.0                # нейтральный угол наклона (град, для режима орбиты)
PITCH_GAIN=1.6                   # чувствительность наклона (град на град головы)
AOA_MIN=180.0; AOA_MAX=344.0     # рабочий диапазон наклона (град, режим орбиты)
DIST_DEFAULT=1650.0
FIXED_EYE=True                   # True = глаз неподвижен, меняется направление взгляда
                                 # False = орбита вокруг точки (старое поведение)
# --- геометрия фиксированного глаза ---
# Глаз стоит на высоте EYE_HEIGHT над землёй. Направление взгляда задаётся
# азимутом (yaw головы) и углом вниз e (pitch головы). Каждый кадр:
#   dist = H/sin(e); цель = глаз + (H/tan(e))*dir(азимут); aoa = -(e)
# => игра ставит глаз ровно в ту же точку, меняется только направление.
EYE_HEIGHT=1400.0                # высота глаза над землёй (= «зум»: больше -> дальше;
                                 # нейтральная дистанция = EYE_HEIGHT/sin(NEUTRAL_E) ~2180)
NEUTRAL_E=40.0                   # нейтральный угол взгляда вниз (град)
E_MIN=-45.0; E_MAX=84.0          # угол взгляда вниз; <0 = выше горизонта (в WC3 там
                                 # пусто/чёрно — движок не рисует небо в melee-картах)
FARZ_VALUE=10000.0               # дальность прорисовки (горизонт дальше)
MOVE_SPEED=1600.0                # перемещение джойстиком (юниты/сек)
MOVE_DEADZONE=0.15               # мёртвая зона стика
TICK_MS=8                        # период потока в игре (мс)
WRITE_HZ=90
# --------------------------------------------------------------

class ME32(ctypes.Structure):
    _fields_=[("dwSize",wt.DWORD),("th32ModuleID",wt.DWORD),("th32ProcessID",wt.DWORD),
              ("GlblcntUsage",wt.DWORD),("ProccntUsage",wt.DWORD),
              ("modBaseAddr",ctypes.POINTER(ctypes.c_byte)),("modBaseSize",wt.DWORD),
              ("hModule",wt.HMODULE),("szModule",ctypes.c_char*256),("szExePath",ctypes.c_char*260)]


class CineCameraSync:
    """Свободная камера через кинематографический сеттер. API как camera_sync."""

    def __init__(self, log=print):
        self.log=log
        self._pose=(0.0,0.0); self._pose_time=0.0
        self._enabled=False
        self._ph=None; self._gb=None; self._pid=None
        self._cave=None; self._ENABLE=None; self._ROT=None; self._AOA=None; self._DIST=None
        self._thread_installed=False
        self._neutral_rot_deg=90.0; self._neutral_aoa_deg=NEUTRAL_AOA
        self._eye_x=None; self._eye_y=None
        self._TGTX=None; self._TGTY=None; self._FARZ=None; self._ZOFF=None
        self._bnd=None                   # (minx,miny,maxx,maxy) цели камеры
        self._move=(0.0,0.0)             # стик джойстика (mx=вбок, my=вперёд/назад)
        self._last_error=""
        threading.Thread(target=self._loop,daemon=True).start()

    # ---------- API ----------
    def set_pose(self, yaw, pitch):
        self._pose=(float(yaw),float(pitch)); self._pose_time=time.time()

    def recenter(self):
        # нейтраль поворота = текущий угол камеры; наклон (AoA) держим фиксированным.
        # Для FIXED_EYE: считаем позицию глаза из текущей цели + радиус в направлении поворота.
        self._neutral_aoa_deg=NEUTRAL_AOA
        if self._ph:
            cam=self._camera()
            if cam:
                r=self._rf(cam+OFF_ROT)
                if r is not None: self._neutral_rot_deg=math.degrees(r)
                tx=self._rf(cam+OFF_TGTX); ty=self._rf(cam+OFF_TGTY)
                if tx is not None and ty is not None:
                    # глаз ПОЗАДИ цели по направлению взгляда (камера смотрит от глаза на цель)
                    d0=EYE_HEIGHT/math.tan(math.radians(NEUTRAL_E))
                    rr=math.radians(self._neutral_rot_deg)
                    self._eye_x=tx-d0*math.cos(rr)
                    self._eye_y=ty-d0*math.sin(rr)
                # границы карты для цели (не даём цели вылететь -> краш)
                bx0=self._rf(cam+OFF_BND_MINX); by0=self._rf(cam+OFF_BND_MINY)
                bx1=self._rf(cam+OFF_BND_MAXX); by1=self._rf(cam+OFF_BND_MAXY)
                if None not in (bx0,by0,bx1,by1) and bx1>bx0 and by1>by0:
                    self._bnd=(bx0,by0,bx1,by1)

    def enable(self): self._enabled=True
    def disable(self):
        self._enabled=False
        if self._cave: self._wdw(self._ENABLE,0)

    def status(self):
        return {"enabled":self._enabled,"attached":self._ph is not None,
                "mode":"cinematic free-cam","installed":self._thread_installed,
                "error":self._last_error}

    # ---------- память ----------
    def _find_hwnd(self):
        return user32.FindWindowW("Warcraft III",None)
    def _find_pid(self):
        h=self._find_hwnd()
        if not h: return None
        pid=wt.DWORD(); user32.GetWindowThreadProcessId(h,ctypes.byref(pid))
        return pid.value
    def _ensure_foreground(self):
        h=self._find_hwnd()
        if not h: return
        if user32.IsIconic(h):
            user32.ShowWindow(h,9)   # SW_RESTORE -> чтобы игра рендерила
        if user32.GetForegroundWindow()!=h:
            user32.SetForegroundWindow(h)
    def _detach(self):
        if self._ph:
            try: kernel32.CloseHandle(self._ph)
            except Exception: pass
        self._ph=None; self._gb=None; self._pid=None
        self._cave=None; self._thread_installed=False
    def _module_base(self,pid,name=b"game.dll"):
        snap=kernel32.CreateToolhelp32Snapshot(TH32,pid); me=ME32(); me.dwSize=ctypes.sizeof(ME32); base=None
        if kernel32.Module32First(snap,ctypes.byref(me)):
            while True:
                if me.szModule.lower()==name: base=ctypes.cast(me.modBaseAddr,ctypes.c_void_p).value; break
                if not kernel32.Module32Next(snap,ctypes.byref(me)): break
        kernel32.CloseHandle(snap); return base

    def _get_export(self, base, want):
        """Резолвит адрес экспорта в модуле игры (32-бит PE в памяти)."""
        def u32(a): d=self._r(a,4); return struct.unpack("<I",d)[0] if d else None
        def u16(a): d=self._r(a,2); return struct.unpack("<H",d)[0] if d else None
        e_lfanew=u32(base+0x3c)
        if e_lfanew is None: return None
        pe=base+e_lfanew
        exp_rva=u32(pe+0x78)
        if not exp_rva: return None
        exp=base+exp_rva
        num_names=u32(exp+0x18); addr_funcs=base+u32(exp+0x1c)
        addr_names=base+u32(exp+0x20); addr_ords=base+u32(exp+0x24)
        for i in range(num_names or 0):
            nr=u32(addr_names+4*i)
            nm=self._r(base+nr, len(want)+1)
            if nm and nm[:len(want)]==want and nm[len(want):len(want)+1]==b"\x00":
                ordi=u16(addr_ords+2*i)
                return base+u32(addr_funcs+4*ordi)
        return None
    def _r(self,a,n):
        b=ctypes.create_string_buffer(n); g=ctypes.c_size_t()
        return b.raw[:g.value] if kernel32.ReadProcessMemory(self._ph,ctypes.c_void_p(a),b,n,ctypes.byref(g)) else None
    def _rdw(self,a): d=self._r(a,4); return struct.unpack("<I",d)[0] if d else None
    def _rf(self,a): d=self._r(a,4); return struct.unpack("<f",d)[0] if d else None
    def _w(self,a,data):
        n=ctypes.c_size_t(); kernel32.WriteProcessMemory(self._ph,ctypes.c_void_p(a),data,len(data),ctypes.byref(n))
    def _wf(self,a,v): self._w(a,struct.pack("<f",v))
    def _wdw(self,a,v): self._w(a,struct.pack("<I",v&0xffffffff))
    def _camera(self):
        cont=self._rdw(CONTAINER_ADDR)
        if not cont: return None
        cam=self._rdw(cont+CAM_OFF)
        return cam if cam and 0x10000<cam<0x7fff0000 else None

    def _attach(self):
        pid=self._find_pid()
        if not pid: self._last_error="окно 1.26 не найдено"; return False
        ph=kernel32.OpenProcess(0x043A,False,pid)
        if not ph: self._last_error="OpenProcess fail"; return False
        gb=self._module_base(pid)
        if not gb or gb!=GDLL_BASE:
            # база должна быть 0x6f000000 (для наших абсолютных адресов)
            if gb: self._last_error="game.dll база %#x != 0x6f000000"%gb
            else: self._last_error="game.dll не найден"
            kernel32.CloseHandle(ph); return False
        self._ph=ph; self._gb=gb; self._pid=pid; self._last_error=""
        return True

    def _install_thread(self):
        pid=self._find_pid()
        kbase=self._module_base(pid,b"kernel32.dll")
        SLEEP=self._get_export(kbase,b"Sleep") if kbase else None
        if not SLEEP:
            self._last_error="не резолвится Sleep из kernel32 игры"; return False
        cave=int(kernel32.VirtualAllocEx(self._ph,None,0x1000,0x3000,0x40))
        ENABLE=cave+0x200; ROT=cave+0x204; AOA=cave+0x208; DIST=cave+0x20c
        TGTX=cave+0x210; TGTY=cave+0x214; FARZ=cave+0x218; ZOFF=cave+0x21c
        P=lambda x: struct.pack("<I",x)
        # ---- ассемблируем цикл (jz near rel32 под большой блок) ----
        code=bytearray(); jz_sites=[]
        def emit(b): code.extend(b)
        # loop (offset 0):
        emit(b"\xA1"+P(ENABLE)); emit(b"\x85\xC0")
        emit(b"\x0F\x84\x00\x00\x00\x00"); jz_sites.append(len(code)-4)  # jz near Lsleep
        emit(b"\xA1"+P(CONTAINER_ADDR)); emit(b"\x85\xC0")
        emit(b"\x0F\x84\x00\x00\x00\x00"); jz_sites.append(len(code)-4)
        emit(b"\x8B\x80"+P(CAM_OFF)); emit(b"\x85\xC0")
        emit(b"\x0F\x84\x00\x00\x00\x00"); jz_sites.append(len(code)-4)
        emit(b"\x8B\xF0")                                  # mov esi,eax (cam)
        def setfield(field, gaddr):
            emit(b"\x8B\xDC"+b"\x6A\x01"+b"\x68\x00\x00\x00\x00"+b"\xFF\x35"+P(gaddr)
                 +b"\x6A"+struct.pack("<b",field)+b"\x8B\xCE"+b"\xB8"+P(SETFIELD)+b"\xFF\xD0"+b"\x8B\xE3")
        setfield(5,ROT); setfield(2,AOA); setfield(0,DIST); setfield(1,FARZ); setfield(6,ZOFF)
        if FIXED_EYE:
            # FUN_6f3078b0(this=cam)(x,y): push y; push x; mov ecx,esi; call
            emit(b"\x8B\xDC"+b"\xFF\x35"+P(TGTY)+b"\xFF\x35"+P(TGTX)+b"\x8B\xCE"
                 +b"\xB8"+P(SETPOS)+b"\xFF\xD0"+b"\x8B\xE3")
        # Lsleep:
        Lsleep=len(code)
        emit(b"\x6A"+struct.pack("<b",TICK_MS)+b"\xB8"+P(SLEEP)+b"\xFF\xD0")
        emit(b"\xE9"+struct.pack("<i",0-(len(code)+5)))    # jmp loop
        for s in jz_sites:
            code[s:s+4]=struct.pack("<i",Lsleep-(s+4))
        self._w(cave, bytes(code))
        self._cave,self._ENABLE,self._ROT,self._AOA,self._DIST=cave,ENABLE,ROT,AOA,DIST
        self._TGTX,self._TGTY,self._FARZ,self._ZOFF=TGTX,TGTY,FARZ,ZOFF
        self.recenter()
        self._wdw(ENABLE,0)
        self._wf(FARZ,FARZ_VALUE); self._wf(ZOFF,0.0)
        if FIXED_EYE and self._eye_x is not None:
            self._write_view(0.0,0.0)
        else:
            self._wf(ROT,self._neutral_rot_deg); self._wf(AOA,self._neutral_aoa_deg); self._wf(DIST,DIST_DEFAULT)
        tid=wt.DWORD()
        th=kernel32.CreateRemoteThread(self._ph,None,0,ctypes.c_void_p(cave),ctypes.c_void_p(0),0,ctypes.byref(tid))
        if not th: self._last_error="CreateRemoteThread fail"; self._cave=None; return False
        kernel32.CloseHandle(th)
        self._thread_installed=True
        self.log("[cine] поток запущен cave=%#x neutral_rot=%.1f eye=(%s,%s) H=%.0f"%(
            cave,self._neutral_rot_deg,
            "%.0f"%self._eye_x if self._eye_x is not None else "-",
            "%.0f"%self._eye_y if self._eye_y is not None else "-",EYE_HEIGHT))
        return True

    # ---------- фиксированный глаз: направление взгляда -> поля камеры ----------
    def _write_view(self, yaw_rad, pitch_rad):
        """Глаз неподвижен; yaw/pitch головы задают направление взгляда.
        Смотрим вниз круче нейтрали: цель на земле (dist=H/sin(e), zOffset=0).
        Смотрим к горизонту/вверх (e<NEUTRAL_E, вплоть до отрицательных=НЕБО):
        дистанция постоянная D0, точка прицела поднимается в воздух через
        zOffset = H - D0*sin(e). Оба случая дают ТОТ ЖЕ неподвижный глаз."""
        sy=-1.0 if INVERT_YAW else 1.0
        sp=-1.0 if INVERT_PITCH else 1.0
        az=math.radians(self._neutral_rot_deg)+sy*yaw_rad
        e=NEUTRAL_E
        if ENABLE_PITCH:
            e=NEUTRAL_E + sp*PITCH_GAIN*math.degrees(pitch_rad)
        e=max(E_MIN,min(E_MAX,e))
        er=math.radians(e)
        D0=EYE_HEIGHT/math.sin(math.radians(NEUTRAL_E))
        if e>=NEUTRAL_E:
            dist=EYE_HEIGHT/math.sin(er); d=EYE_HEIGHT/math.tan(er); zoff=0.0
        else:
            dist=D0; d=D0*math.cos(er); zoff=EYE_HEIGHT-D0*math.sin(er)
        tx=self._eye_x+d*math.cos(az); ty=self._eye_y+d*math.sin(az)
        if self._bnd is not None:
            bx0,by0,bx1,by1=self._bnd; m=BND_MARGIN
            tx=max(bx0+m,min(bx1-m,tx)); ty=max(by0+m,min(by1-m,ty))
        self._wf(self._ROT,math.degrees(az))
        self._wf(self._AOA,(360.0-e)%360.0)
        self._wf(self._DIST,dist)
        if self._ZOFF is not None: self._wf(self._ZOFF,zoff)
        self._wf(self._TGTX,tx)
        self._wf(self._TGTY,ty)

    # ---------- перемещение джойстиком (глаз едет в направлении взгляда) ----------
    def set_move(self,mx,my):
        try: self._move=(float(mx),float(my))
        except (TypeError,ValueError): pass

    def _apply_move(self, yaw_rad, dt):
        mx,my=self._move
        if (abs(mx)<MOVE_DEADZONE and abs(my)<MOVE_DEADZONE) or self._eye_x is None:
            return
        sy=-1.0 if INVERT_YAW else 1.0
        az=math.radians(self._neutral_rot_deg)+sy*yaw_rad
        fwd=-my if abs(my)>=MOVE_DEADZONE else 0.0     # стик от себя = вперёд
        strafe=mx if abs(mx)>=MOVE_DEADZONE else 0.0   # стик вбок = стрейф
        step=MOVE_SPEED*dt
        self._eye_x += step*(fwd*math.cos(az)+strafe*math.sin(az))
        self._eye_y += step*(fwd*math.sin(az)-strafe*math.cos(az))
        if self._bnd is not None:
            bx0,by0,bx1,by1=self._bnd; m=BND_MARGIN
            self._eye_x=max(bx0+m,min(bx1-m,self._eye_x))
            self._eye_y=max(by0+m,min(by1-m,self._eye_y))

    # ---------- питон-цикл: пишет глобали из позы ----------
    def _loop(self):
        period=1.0/WRITE_HZ
        while True:
            time.sleep(period)
            if not self._enabled:
                if self._cave: self._wdw(self._ENABLE,0)
                continue
            # процесс сменился (игру перезапустили) или закрылся -> переподключиться
            cur=self._find_pid()
            if cur is None:
                self._detach(); continue
            if self._ph is not None and cur!=self._pid:
                self.log("[cine] игра перезапущена (pid %s->%s) — переподключаюсь"%(self._pid,cur))
                self._detach()
            if self._ph is None:
                if not self._attach(): time.sleep(1.0); continue
            if self._cave is None:
                if not self._install_thread(): time.sleep(1.0); continue
            # держим окно активным, чтобы игра рендерила (не чаще раза в ~1с)
            now=time.time()
            if now-getattr(self,'_last_fg',0)>1.0:
                self._ensure_foreground(); self._last_fg=now
            yaw,pitch=self._pose
            fixed=FIXED_EYE and self._eye_x is not None and self._TGTX is not None
            if time.time()-self._pose_time>1.0:
                # позы нет — держим нейтральное направление
                if fixed: self._write_view(0.0,0.0)
                else:
                    self._wf(self._ROT,self._neutral_rot_deg); self._wf(self._AOA,self._neutral_aoa_deg)
                self._wdw(self._ENABLE,1)
                continue
            if fixed:
                self._apply_move(yaw,period)
                self._write_view(yaw,pitch)
            else:
                sy=-1.0 if INVERT_YAW else 1.0
                sp=-1.0 if INVERT_PITCH else 1.0
                rot_deg=self._neutral_rot_deg + sy*math.degrees(yaw)
                self._wf(self._ROT,rot_deg)
                if ENABLE_PITCH:
                    # голова вверх -> ниже AoA -> к горизонту; вниз -> выше AoA -> сверху
                    aoa=self._neutral_aoa_deg - sp*PITCH_GAIN*math.degrees(pitch)
                    aoa=max(AOA_MIN,min(AOA_MAX,aoa))
                    self._wf(self._AOA,aoa)
            self._wdw(self._ENABLE,1)
