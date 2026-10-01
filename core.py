"""Çekirdek: modeller, ses çözme, dosya ve canlı transkript işçileri (arayüzden bağımsız)."""
import os
import queue
import sys
import threading
import time
from collections import deque
from pathlib import Path

import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal

SR = 16000            # Whisper'ın beklediği örnekleme hızı
CHUNK_SEC = 30.0      # Whisper sesi 30 sn'lik parçalar halinde işler
PARAGRAPH_GAP = 2.0   # saniye; bu kadar sessizlikten sonra yeni paragraf

AUDIO_EXT = {".mp3", ".m4a", ".wav", ".aac", ".ogg", ".opus", ".flac", ".wma",
             ".amr", ".3gp", ".mp4", ".webm", ".mkv", ".mov"}

# (kod, i18n anahtarı) — model adı, kalite açıklaması i18n'de
QUALITY = [("small", "q_standard"), ("large-v3-turbo", "q_high")]
QUALITY_DEFAULT = 1

_N_CPU = os.cpu_count() or 4
MODES = [  # (i18n anahtarı, thread sayısı)
    ("mode_quiet", max(2, _N_CPU // 4)),
    ("mode_balanced", max(3, _N_CPU // 2)),
    ("mode_fast", max(4, _N_CPU * 3 // 4)),
]

# Whisper'ın desteklediği dillerden sık kullanılanlar (kendi dillerindeki adlarıyla).
# "Otomatik" seçiliyken Whisper'ın desteklediği ~100 dilin tamamı algılanabilir.
LANGUAGES = [
    ("tr", "Türkçe"), ("en", "English"), ("de", "Deutsch"), ("fr", "Français"),
    ("es", "Español"), ("it", "Italiano"), ("pt", "Português"), ("nl", "Nederlands"),
    ("pl", "Polski"), ("ru", "Русский"), ("uk", "Українська"), ("ar", "العربية"),
    ("fa", "فارسی"), ("az", "Azərbaycanca"), ("kk", "Қазақша"), ("el", "Ελληνικά"),
    ("bg", "Български"), ("ro", "Română"), ("hu", "Magyar"), ("cs", "Čeština"),
    ("sv", "Svenska"), ("no", "Norsk"), ("da", "Dansk"), ("fi", "Suomi"),
    ("zh", "中文"), ("ja", "日本語"), ("ko", "한국어"), ("hi", "हिन्दी"),
    ("id", "Bahasa Indonesia"), ("vi", "Tiếng Việt"),
]


def lower_priority():
    """Süreci düşük öncelikle çalıştır: bilgisayarda başka iş yapılırken işlemci önce ona verilir."""
    try:
        if sys.platform == "win32":
            import ctypes
            BELOW_NORMAL_PRIORITY_CLASS = 0x4000
            k32 = ctypes.windll.kernel32
            k32.SetPriorityClass(k32.GetCurrentProcess(), BELOW_NORMAL_PRIORITY_CLASS)
        else:
            os.nice(10)
    except Exception:
        pass


def app_dir() -> Path:
    """Exe içinde çalışırken exe'nin klasörü, aksi halde betiğin klasörü."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def user_data_dir() -> Path:
    """Uygulamanın yazılabilir veri klasörü (indirilen modeller vb.)."""
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "DersTranskript"


def recordings_dir() -> Path:
    """Canlı dinleme kayıtları: Belgeler/Ders Transkript."""
    docs = Path.home() / "Documents"
    if not docs.is_dir():
        docs = Path.home()
    return docs / "Ders Transkript"


def model_path(name: str) -> Path:
    """Modeli olası konumlarda arar; bulunamazsa indirileceği yeri döndürür.

    Windows: exe'nin yanındaki models/  ·  macOS: DersTranskript.app/Contents/Resources/models/
    """
    candidates = [app_dir() / "models"]
    if getattr(sys, "frozen", False):
        candidates += [Path(getattr(sys, "_MEIPASS", app_dir())) / "models",
                       app_dir().parent / "Resources" / "models"]
    candidates.append(user_data_dir() / "models")
    for d in candidates:
        if (d / name / "model.bin").exists():
            return d / name
    return (user_data_dir() / "models" if getattr(sys, "frozen", False) else app_dir() / "models") / name


def decode_audio(path: str, sr: int = SR):
    """Dosyayı 16 kHz mono float32 diziye çevirir (PyAV ile; harici ffmpeg gerekmez).

    faster-whisper'ın kendi decode_audio'su yeni PyAV sürümleriyle uyumsuz olduğu için
    çözme işlemi burada yapılıyor.
    """
    import av

    chunks = []
    resampler = av.AudioResampler(format="s16", layout="mono", rate=sr)
    with av.open(path) as container:
        stream = container.streams.audio[0]
        for frame in container.decode(stream):
            for f in resampler.resample(frame):
                chunks.append(f.to_ndarray().reshape(-1))
        for f in resampler.resample(None):
            chunks.append(f.to_ndarray().reshape(-1))
    if not chunks:
        raise ValueError("no audio")
    return np.concatenate(chunks).astype(np.float32) / 32768.0


def probe_audio(path):
    """(süre sn veya None, boyut bayt) — dosya seçilince bilgi göstermek için."""
    size = os.path.getsize(path)
    try:
        import av
        with av.open(path) as c:
            dur = c.duration / 1_000_000 if c.duration else None
    except Exception:
        dur = None
    return dur, size


def fmt_time(sec: float) -> str:
    sec = int(max(0, sec))
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{h:d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


class ModelCache:
    """Modelleri bir kez yükler ve işler arasında paylaştırır.

    Dosya ve canlı sekme aynı modeli kullanıyorsa bellekte tek kopya durur. Kimse
    kullanmayınca model bir süre sonra bellekten atılır (tekrar başlatmalar hızlı olsun diye
    hemen değil).
    """
    IDLE_RELEASE_SEC = 180

    def __init__(self):
        self._lock = threading.Lock()
        self._models = {}  # (ad, thread) -> [model, kullanan sayısı, son bırakılma zamanı]

    def acquire(self, name, threads, on_download=None):
        from faster_whisper import WhisperModel

        key = (name, threads)
        with self._lock:
            entry = self._models.get(key)
            if entry is None:
                path = model_path(name)
                if not (path / "model.bin").exists():
                    from faster_whisper.utils import download_model
                    if on_download:
                        on_download()
                    download_model(name, output_dir=str(path))
                model = WhisperModel(str(path), device="cpu", compute_type="int8",
                                     cpu_threads=threads)
                entry = self._models[key] = [model, 0, 0.0]
            entry[1] += 1
            return entry[0]

    def release(self, name, threads):
        with self._lock:
            entry = self._models.get((name, threads))
            if entry:
                entry[1] -= 1
                entry[2] = time.time()
        t = threading.Timer(self.IDLE_RELEASE_SEC + 1, self._collect)
        t.daemon = True
        t.start()

    def _collect(self):
        with self._lock:
            now = time.time()
            for key in [k for k, (_, n, t) in self._models.items()
                        if n <= 0 and now - t >= self.IDLE_RELEASE_SEC]:
                del self._models[key]


CACHE = ModelCache()


def join_piece(text, start, last_end, timestamps):
    """Bir cümleyi öncekiyle birleştirirken boşluk / paragraf / zaman damgası ekler."""
    if timestamps:
        return ("\n" if last_end is not None else "") + f"[{fmt_time(start)}] {text}"
    if last_end is None:
        return text
    if start - last_end > PARAGRAPH_GAP:
        return "\n\n" + text
    return " " + text


class FileWorker(QThread):
    """Bir ses dosyasını baştan sona metne çevirir."""
    step = pyqtSignal(int)               # 0: model, 1: ses okuma, 2: çeviri
    info = pyqtSignal(str, str)          # (i18n anahtarı, değer) — ek bilgi
    progress = pyqtSignal(float, float)  # işlenen ses (sn), toplam ses (sn)
    segment = pyqtSignal(str)
    finished_ok = pyqtSignal(float)      # geçen süre
    failed = pyqtSignal(str)

    def __init__(self, audio_path, model_name, language, timestamps, threads):
        super().__init__()
        self.audio_path = audio_path
        self.model_name = model_name
        self.language = language
        self.timestamps = timestamps
        self.threads = threads
        self.cancelled = False

    def cancel(self):
        self.cancelled = True

    def run(self):
        t0 = time.time()
        model = None
        try:
            self.step.emit(0)
            model = CACHE.acquire(self.model_name, self.threads,
                                  on_download=lambda: self.info.emit("downloading_model", ""))
            if self.cancelled:
                return
            self.step.emit(1)
            audio = decode_audio(self.audio_path)
            if self.cancelled:
                return
            self.step.emit(2)
            segments, info = model.transcribe(
                audio, language=self.language, beam_size=5,
                vad_filter=True,  # sessiz bölümleri atlar: hız + daha az uydurma metin
                vad_parameters={"min_silence_duration_ms": 500},
            )
            duration = info.duration or 1.0
            self.progress.emit(0.0, duration)
            if not self.language:
                self.info.emit("detected_lang", info.language)
            last_end = None
            for seg in segments:
                if self.cancelled:
                    return
                self.progress.emit(min(seg.end, duration), duration)
                text = seg.text.strip()
                if not text:
                    continue
                self.segment.emit(join_piece(text, seg.start, last_end, self.timestamps))
                last_end = seg.end
            self.progress.emit(duration, duration)
            self.finished_ok.emit(time.time() - t0)
        except Exception as e:
            self.failed.emit(f"{type(e).__name__}: {e}")
        finally:
            if model is not None:
                CACHE.release(self.model_name, self.threads)


class RecordingWriter:
    """Canlı dinlenen sesi diske yazar: önce M4A (AAC, ~15 MB/saat), olmazsa WAV."""

    def __init__(self, path_base: Path):
        path_base.parent.mkdir(parents=True, exist_ok=True)
        self._wav = None
        self._out = None
        try:
            import av
            self.path = path_base.parent / (path_base.name + ".m4a")
            self._out = av.open(str(self.path), "w")
            self._stream = self._out.add_stream("aac", rate=SR)
            self._stream.layout = "mono"
            self._stream.bit_rate = 32000
            self._resampler = av.AudioResampler(format=self._stream.format, layout="mono", rate=SR)
            self._av = av
            self._pts = 0
        except Exception:
            self._out = None
            import wave
            self.path = path_base.parent / (path_base.name + ".wav")
            self._wav = wave.open(str(self.path), "wb")
            self._wav.setnchannels(1)
            self._wav.setsampwidth(2)
            self._wav.setframerate(SR)

    def write(self, samples):
        pcm = (np.clip(samples, -1, 1) * 32767).astype(np.int16)
        if self._wav is not None:
            self._wav.writeframes(pcm.tobytes())
            return
        frame = self._av.AudioFrame.from_ndarray(pcm.reshape(1, -1), format="s16", layout="mono")
        frame.sample_rate = SR
        frame.pts = self._pts
        self._pts += len(pcm)
        for f in self._resampler.resample(frame):
            for packet in self._stream.encode(f):
                self._out.mux(packet)

    def close(self):
        if self._wav is not None:
            self._wav.close()
            return
        for packet in self._stream.encode(None):
            self._out.mux(packet)
        self._out.close()


class LiveWorker(QThread):
    """Mikrofondan gelen sesi duraklamalardan bölüp parça parça metne çevirir.

    Ses arayüz iş parçacığında yakalanıp `feed()` ile kuyruğa konur; bu iş parçacığı
    parçaları biriktirir, konuşmada ~0,6 sn duraklama olunca (ya da en geç MAX_CHUNK
    saniyede, en sessiz noktadan) birikeni çevirir. Böylece cümleler ortadan bölünmez.
    """
    MIN_CHUNK = 2.5      # sn; bundan kısa parçalar duraklama olsa da beklenir
    MAX_CHUNK = 12.0     # sn; konuşma hiç durmazsa en geç bu uzunlukta kesilir
    SILENCE_TAIL = 0.6   # sn; parçayı bitiren duraklama
    FRAME = 320          # 20 ms

    ready = pyqtSignal()
    segment = pyqtSignal(str)
    processed = pyqtSignal(float)        # metne çevrilen ses süresi (sn, başlangıçtan)
    info = pyqtSignal(str, str)
    finished_ok = pyqtSignal(str)        # kayıt dosyasının yolu ("" = kayıt yok)
    failed = pyqtSignal(str)

    def __init__(self, model_name, language, timestamps, threads, record_base=None):
        super().__init__()
        self.model_name = model_name
        self.language = language
        self.timestamps = timestamps
        self.threads = threads
        self.record_base = record_base
        self.q = queue.Queue()
        self.text_tail = ""

    def feed(self, samples):
        self.q.put(samples)

    def stop(self):
        self.q.put(None)  # kuyruktaki ses bitince durur, son parça da çevrilir

    def run(self):
        model = None
        writer = None
        try:
            model = CACHE.acquire(self.model_name, self.threads,
                                  on_download=lambda: self.info.emit("downloading_model", ""))
            writer = RecordingWriter(self.record_base) if self.record_base else None
            self.ready.emit()
            self._loop(model, writer)
            if writer:
                writer.close()
            self.finished_ok.emit(str(writer.path) if writer else "")
        except Exception as e:
            if writer:
                try:
                    writer.close()
                except Exception:
                    pass
            self.failed.emit(f"{type(e).__name__}: {e}")
        finally:
            if model is not None:
                CACHE.release(self.model_name, self.threads)

    def _loop(self, model, writer):
        pending = np.zeros(0, np.float32)
        offset = 0.0                       # pending[0]'ın kayıt başından itibaren zamanı
        recent = deque(maxlen=500)         # son ~10 sn'nin çerçeve enerjileri (gürültü tabanı için)
        last_end = None
        lang = self.language
        stopping = False
        while not stopping:
            item = self.q.get()
            if item is None:
                stopping = True
            else:
                if writer:
                    writer.write(item)
                pending = np.concatenate([pending, item])
                n = len(item) // self.FRAME
                if n:
                    fr = item[: n * self.FRAME].reshape(n, self.FRAME)
                    recent.extend(np.sqrt((fr ** 2).mean(axis=1)).tolist())
                if not self.q.empty():
                    continue  # kuyrukta daha ses var: önce hepsini topla

            cut = self._find_cut(pending, recent, final=stopping)
            if cut == "drop":  # uzun süredir konuşma yok: sessizliği at
                keep = int(0.5 * SR)
                offset += (len(pending) - keep) / SR
                pending = pending[-keep:]
                self.processed.emit(offset)
                continue
            if cut is None:
                continue
            chunk, pending = pending[:cut], pending[cut:]
            last_end, lang = self._transcribe(model, chunk, offset, last_end, lang)
            offset += len(chunk) / SR
            self.processed.emit(offset)

    def _find_cut(self, pending, recent, final):
        L = len(pending) / SR
        if final:
            return len(pending) if L > 0.3 else None
        if L < 1.0:
            return None
        floor = np.percentile(recent, 20) if recent else 0.0
        thr = max(0.004, floor * 2.5)
        n = len(pending) // self.FRAME
        rms = np.sqrt((pending[: n * self.FRAME].reshape(n, self.FRAME) ** 2).mean(axis=1))
        speech_frames = int((rms > thr).sum())
        if speech_frames * self.FRAME / SR < 0.3:
            return "drop" if L > 5 else None
        tail_frames = int(self.SILENCE_TAIL * SR / self.FRAME)
        if L >= self.MIN_CHUNK and (rms[-tail_frames:] < thr).all():
            return len(pending)
        if L >= self.MAX_CHUNK:  # konuşma durmuyor: son 4 sn'nin en sessiz yerinden kes
            lo = max(0, n - int(4 * SR / self.FRAME))
            return (lo + int(np.argmin(rms[lo:]))) * self.FRAME
        return None

    def _transcribe(self, model, chunk, offset, last_end, lang):
        segments, info = model.transcribe(
            chunk, language=lang, beam_size=3, vad_filter=True,
            condition_on_previous_text=False,
            initial_prompt=self.text_tail[-200:] or None,  # önceki metin: süreklilik ve yazım tutarlılığı
        )
        segs = list(segments)
        if lang is None and info.language_probability > 0.8 and len(chunk) > 3 * SR:
            lang = info.language  # dil güvenle belli oldu: sonraki parçalarda tekrar algılama yapma
            self.info.emit("detected_lang", lang)
        for s in segs:
            text = s.text.strip()
            # sessizlikte uydurulan metni ele ("İzlediğiniz için teşekkürler" vb.)
            if not text or (s.no_speech_prob > 0.6 and s.avg_logprob < -1.0):
                continue
            start = offset + s.start
            self.segment.emit(join_piece(text, start, last_end, self.timestamps))
            last_end = offset + s.end
            self.text_tail = (self.text_tail + " " + text)[-400:]
        return last_end, lang
