# -*- coding: utf-8 -*-
"""
Звук игры в шлем: захват вывода ПК через WASAPI loopback (pyaudiowpatch)
и раздача сырого PCM (int16) всем подключённым клиентам /audio.
Формат потока: заголовок 12 байт  b"WCVA" + rate(u32) + channels(u16) + bits(u16),
дальше непрерывный PCM. Очередь каждого клиента ограничена — при отставании
старые чанки выбрасываются, чтобы задержка не росла.
"""
import threading, struct, queue, time
try:
    import pyaudiowpatch as pyaudio
except ImportError:
    pyaudio = None


class AudioHub:
    MAGIC = b"WCVA"

    def __init__(self, chunk_ms=20, log=print):
        self.log = log
        self.rate = 48000; self.channels = 2; self.chunk_ms = chunk_ms
        self.subs = set(); self.lock = threading.Lock()
        self.ok = False; self.error = ""; self.device_name = ""
        if pyaudio is None:
            self.error = "нет pyaudiowpatch (pip install pyaudiowpatch)"; return
        threading.Thread(target=self._run, daemon=True).start()

    def header(self):
        return self.MAGIC + struct.pack("<IHH", self.rate, self.channels, 16)

    def subscribe(self):
        q = queue.Queue(maxsize=25)          # ~0.5 с максимум в очереди
        with self.lock: self.subs.add(q)
        return q

    def unsubscribe(self, q):
        with self.lock: self.subs.discard(q)

    def _find_loopback(self, pa):
        try:
            wasapi = pa.get_host_api_info_by_type(pyaudio.paWASAPI)
        except OSError:
            raise RuntimeError("WASAPI недоступен")
        dev = pa.get_device_info_by_index(wasapi["defaultOutputDevice"])
        if dev.get("isLoopbackDevice"):
            return dev
        for lb in pa.get_loopback_device_info_generator():
            if dev["name"] in lb["name"]:
                return lb
        raise RuntimeError("loopback для устройства «%s» не найден" % dev["name"])

    def _run(self):
        while True:
            pa = None
            try:
                pa = pyaudio.PyAudio()
                dev = self._find_loopback(pa)
                self.rate = int(dev["defaultSampleRate"])
                self.channels = max(1, min(2, int(dev["maxInputChannels"])))
                self.device_name = dev["name"]
                frames = int(self.rate * self.chunk_ms / 1000)
                stream = pa.open(format=pyaudio.paInt16, channels=self.channels, rate=self.rate,
                                 input=True, input_device_index=dev["index"],
                                 frames_per_buffer=frames)
                self.ok = True; self.error = ""
                self.log("[audio] loopback: %s  %d Hz x%d" % (dev["name"], self.rate, self.channels))
                while True:
                    data = stream.read(frames, exception_on_overflow=False)
                    with self.lock: subs = list(self.subs)
                    for q in subs:
                        try:
                            q.put_nowait(data)
                        except queue.Full:
                            try: q.get_nowait()          # выкинуть старое
                            except queue.Empty: pass
                            try: q.put_nowait(data)
                            except queue.Full: pass
            except Exception as ex:
                self.ok = False; self.error = str(ex)
                self.log("[audio] ошибка: %s (повтор через 3 с)" % ex)
                time.sleep(3)
            finally:
                try:
                    if pa: pa.terminate()
                except Exception:
                    pass
