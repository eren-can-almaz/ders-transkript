"""Ses klonlama (isteğe bağlı eklenti, gelişmiş mod): bir konuşmacının sesinden (ör. gürültüsü
ayıklanmış bölüm) ses rengini öğrenip verilen metni o sesle yeniden üretir.

Model: Chatterbox Multilingual (Resemble AI, MIT lisansı), ONNX sürümü (onnx-community).
Türkçe dahil 23 dil; sıfırdan klonlama (eğitim gerekmez). Yalnızca onnxruntime + numpy kullanır:
PyTorch gerekmez. Model dosyaları (~1,55 GB, 4-bit dil modeli) ilk kullanımda bir kez indirilir ve
kullanıcı veri klasöründeki plugins/ altında kalır (oturum temizliğinden etkilenmez).
"""
import re
import threading
import time
import urllib.request
from pathlib import Path

import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal

from core import app_dir, user_data_dir

REPO = "onnx-community/chatterbox-multilingual-ONNX"
FILES = {  # yol: yaklaşık boyut (bayt) — ilerleme çubuğu için
    "tokenizer.json": 115_000,
    "onnx/speech_encoder.onnx": 1_200_000, "onnx/speech_encoder.onnx_data": 591_300_000,
    "onnx/embed_tokens.onnx": 30_000, "onnx/embed_tokens.onnx_data": 68_400_000,
    "onnx/conditional_decoder.onnx": 6_400_000, "onnx/conditional_decoder.onnx_data": 534_000_000,
    "onnx/language_model_q4.onnx": 200_000, "onnx/language_model_q4.onnx_data": 353_600_000,
}
TOTAL_BYTES = sum(FILES.values())
SR = 24000                       # modelin çalıştığı örnekleme hızı
START, STOP = 6561, 6562         # konuşma belirteçleri
LAYERS, KV_HEADS, HEAD_DIM = 30, 16, 64
TOKENS_PER_SEC = 25              # üretilen konuşma belirteci / saniye ses
LANGS = {"ar", "da", "de", "el", "en", "es", "fi", "fr", "he", "hi", "it", "ja", "ko", "ms", "nl",
         "no", "pl", "pt", "ru", "sv", "sw", "tr", "zh"}


def plugin_dir() -> Path:
    dev = app_dir() / "models" / "chatterbox"  # geliştirme ortamında projedeki kopya
    if all((dev / f).exists() for f in FILES):
        return dev
    return user_data_dir() / "plugins" / "chatterbox"


def installed() -> bool:
    d = plugin_dir()
    return all((d / f).exists() for f in FILES)


class Downloader(QThread):
    """Eklenti dosyalarını Hugging Face'ten indirir (kesilirse .part dosyası silinir)."""
    progress = pyqtSignal(float)  # 0..1
    done = pyqtSignal()
    failed = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.cancelled = False

    def run(self):
        d = user_data_dir() / "plugins" / "chatterbox"
        got = 0
        try:
            for rel, size in FILES.items():
                dest = d / rel
                if dest.exists():
                    got += size
                    continue
                dest.parent.mkdir(parents=True, exist_ok=True)
                part = dest.with_name(dest.name + ".part")
                url = f"https://huggingface.co/{REPO}/resolve/main/{rel}"
                with urllib.request.urlopen(url, timeout=60) as r, open(part, "wb") as f:
                    while True:
                        if self.cancelled:
                            raise RuntimeError("cancelled")
                        buf = r.read(1 << 20)
                        if not buf:
                            break
                        f.write(buf)
                        got += len(buf)
                        self.progress.emit(min(1.0, got / TOTAL_BYTES))
                part.replace(dest)
            self.done.emit()
        except Exception as e:
            for p in d.rglob("*.part"):
                p.unlink(missing_ok=True)
            self.failed.emit(f"{type(e).__name__}: {e}")


def _norm_text(text, lang="tr"):
    """Chatterbox'ın eğitildiği biçim: küçük harf + Unicode NFKD (ör. 'ğ' → 'g' + birleşik işaret),
    sade boşluklar, sonda noktalama. Türkçede I/İ küçük harfe dile uygun çevrilir (I→ı, İ→i)."""
    import unicodedata
    t = " ".join(text.split())
    if t and t[-1] not in ".!?…,;:":
        t += "."
    if lang in ("tr", "az"):
        t = t.replace("I", "ı").replace("İ", "i")
    return unicodedata.normalize("NFKD", t.lower())


def split_sentences(text, max_chars=220):
    """Metni cümlelere böl; çok uzun cümleleri virgüllerden / boşluklardan parçala."""
    parts = re.split(r"(?<=[.!?…])\s+", " ".join(text.split()))
    out = []
    for p in parts:
        while len(p) > max_chars:
            cut = max(p.rfind(", ", 0, max_chars), p.rfind(" ", 0, max_chars))
            cut = cut if cut > 40 else max_chars
            out.append(p[:cut].strip(" ,"))
            p = p[cut:].strip()
        if p:
            out.append(p)
    return out


def best_reference(audio, sr, seconds=10.0):
    """Konuşmacı örneği: enerjisi en yüksek (en net konuşulan) `seconds` saniyelik pencere."""
    n = int(seconds * sr)
    if len(audio) <= n:
        return audio
    hop = sr // 2
    frames = len(audio) // hop
    e = np.array([np.sqrt(np.mean(audio[i * hop:(i + 1) * hop] ** 2)) for i in range(frames)])
    w = int(seconds * 2)
    score = np.convolve(e, np.ones(w), mode="valid")
    start = int(np.argmax(score)) * hop
    return audio[start:start + n]


def _ticker(progress, lo, hi, expected_sec):
    """Kendi ilerlemesini bildiremeyen uzun bir adım sürerken yüzdeyi süre tahminiyle ilerlet
    (en fazla %97'ye; adım bitince gerçek değer gelir). Döner: durdurma olayı."""
    stop = threading.Event()
    t0 = time.monotonic()

    def run():
        while not stop.wait(0.25):
            f = min(0.97, (time.monotonic() - t0) / max(expected_sec, 0.1))
            progress(lo + (hi - lo) * f)
    threading.Thread(target=run, daemon=True).start()
    return stop


class VoiceClone:
    """Chatterbox ONNX çıkarımı. `reference`: 24 kHz mono float32 konuşmacı örneği."""

    def __init__(self, threads=4, progress=None):
        import onnxruntime as ort
        from tokenizers import Tokenizer

        d = plugin_dir()
        so = ort.SessionOptions()
        so.intra_op_num_threads = threads
        so.inter_op_num_threads = 1
        so.log_severity_level = 3  # kod çözücünün zararsız grafik uyarılarını gösterme
        mk = lambda f: ort.InferenceSession(str(d / "onnx" / f), so, providers=["CPUExecutionProvider"])
        progress = progress or (lambda f: None)
        t = time.monotonic()
        self.enc = mk("speech_encoder.onnx")
        enc_sec = time.monotonic() - t
        progress(0.03)
        self.emb = mk("embed_tokens.onnx")
        self.lm = mk("language_model_q4.onnx")
        progress(0.05)
        # Ses kod çözücünün yüklenmesi (grafiği çok büyük) sürenin ~%95'i ve ilerleme bildirmez:
        # süresini kodlayıcının yüklenme süresinden tahmin et (bu bilgisayarda ~35 katı)
        stop = _ticker(progress, 0.05, 1.0, max(5.0, 35 * enc_sec))
        try:
            self.dec = mk("conditional_decoder.onnx")
        finally:
            stop.set()
        progress(1.0)
        self._dec_per_tok = None  # kod çözme süresi / belirteç (ilk cümleden sonra öğrenilir)
        self.tok = Tokenizer.from_file(str(d / "tokenizer.json"))
        self._spk = None

    def set_speaker(self, reference):
        cond_emb, prompt_token, x_vector, prompt_feat = self.enc.run(
            None, {"audio_values": reference[np.newaxis, :].astype(np.float32)})
        self._spk = (cond_emb, prompt_token, x_vector, prompt_feat)

    def _tokens(self, text, lang, exaggeration, max_new, cancel, on_token=None):
        cond_emb, _, _, _ = self._spk
        ids = np.array([self.tok.encode(f"[{lang}]{_norm_text(text, lang)}").ids], dtype=np.int64)
        pos = np.where(ids >= START, 0, np.arange(ids.shape[1])[np.newaxis, :] - 1)
        feed = {"input_ids": ids, "position_ids": pos.astype(np.int64),
                "exaggeration": np.array([exaggeration], dtype=np.float32)}
        out = np.array([[START]], dtype=np.int64)
        past = attn = None
        self._lm_t0 = time.monotonic()
        for i in range(max_new):
            if cancel():
                return None
            emb = self.emb.run(None, feed)[0]
            if i == 0:
                emb = np.concatenate((cond_emb, emb), axis=1)
                past = {f"past_key_values.{l}.{kv}": np.zeros([1, KV_HEADS, 0, HEAD_DIM], np.float32)
                        for l in range(LAYERS) for kv in ("key", "value")}
                attn = np.ones((1, emb.shape[1]), dtype=np.int64)
            logits, *present = self.lm.run(None, dict(inputs_embeds=emb, attention_mask=attn, **past))
            logits = logits[:, -1, :]
            # tekrar cezası (1.2): üretilmiş belirteçlerin olasılığını düşür
            sc = np.take_along_axis(logits, out, axis=1)
            np.put_along_axis(logits, out, np.where(sc < 0, sc * 1.2, sc / 1.2), axis=1)
            nxt = np.argmax(logits, axis=-1, keepdims=True).astype(np.int64)
            out = np.concatenate((out, nxt), axis=-1)
            if int(nxt[0, 0]) == STOP:
                break
            if on_token and i % 8 == 0:
                on_token(i)
            feed["input_ids"] = nxt
            feed["position_ids"] = np.full((1, 1), i + 1, dtype=np.int64)
            attn = np.concatenate([attn, np.ones((1, 1), dtype=np.int64)], axis=1)
            for j, k in enumerate(past):
                past[k] = present[j]
        self._lm_per_tok = (time.monotonic() - self._lm_t0) / max(1, out.shape[1])
        return out[:, 1:-1] if int(out[0, -1]) == STOP else out[:, 1:]

    def synthesize(self, text, lang="tr", exaggeration=0.5, progress=None, cancel=lambda: False):
        """Metni cümle cümle üretip birleştirir. Döner: 24 kHz float32 dizi (iptal edilirse None)."""
        if self._spk is None:
            raise RuntimeError("speaker not set")
        lang = lang if lang in LANGS else "tr"
        _, prompt_token, x_vector, prompt_feat = self._spk
        pieces = []
        sents = split_sentences(text)
        gap = np.zeros(int(0.18 * SR), np.float32)
        for k, s in enumerate(sents):
            # cümle uzunluğuna göre belirteç sınırı (Türkçe ~14 harf/sn; pay bırakılır)
            expected = max(30, len(s) / 14 * TOKENS_PER_SEC)
            max_new = int(min(1000, max(60, expected * 1.6)))
            n = len(sents)
            prog = progress or (lambda f: None)
            # cümle k: belirteç üretimi [k, k+0.4], kod çözme [k+0.4, k+1] (n'e bölünür)
            tick = lambda i, k=k, e=expected: prog((k + 0.4 * min(0.95, i / e)) / n)
            toks = self._tokens(s, lang, exaggeration, max_new, cancel, on_token=tick)
            if toks is None:
                return None
            toks = np.concatenate([prompt_token, toks], axis=1)
            per_tok = self._dec_per_tok or 3.0 * self._lm_per_tok  # ilk cümlede tahmin, sonra ölçüm
            stop = _ticker(prog, (k + 0.4) / n, (k + 1) / n, per_tok * toks.shape[1])
            t = time.monotonic()
            try:
                wav = self.dec.run(None, {"speech_tokens": toks, "speaker_embeddings": x_vector,
                                          "speaker_features": prompt_feat})[0]
            finally:
                stop.set()
            self._dec_per_tok = (time.monotonic() - t) / toks.shape[1]
            pieces += [np.squeeze(wav, axis=0).astype(np.float32), gap]
            prog((k + 1) / n)
        return np.concatenate(pieces) if pieces else np.zeros(0, np.float32)


# ---------------------------------------------------------------- ayrı süreç
# Model yükleme (~1 dk) Python kilidini (GIL) bırakmadığı için iş parçacığında arayüzü dondurur
# ("yanıt vermiyor"). Bu yüzden klonlama ayrı bir süreçte çalışır: arayüz akıcı kalır, "Durdur"
# süreci anında keser, pencere kapanınca süreç biter ve bellek (~2 GB) tamamen geri verilir.

def _server(req_q, resp_q, threads):
    try:
        model = VoiceClone(threads, progress=lambda f: resp_q.put(("progress", None, ("load", f))))
    except Exception as e:
        resp_q.put(("failed", None, f"{type(e).__name__}: {e}"))
        return
    resp_q.put(("ready", None, None))
    while True:
        msg = req_q.get()
        if msg is None:
            return
        job, ref24, text, lang = msg
        try:
            resp_q.put(("progress", job, ("speaker", 0.0)))
            model.set_speaker(ref24)
            wav = model.synthesize(text, lang, progress=lambda f: resp_q.put(("progress", job, ("synth", f))))
            resp_q.put(("done", job, wav))
        except Exception as e:
            resp_q.put(("failed", job, f"{type(e).__name__}: {e}"))


def _load_time_file():
    return plugin_dir() / ".load_seconds"


def expected_load_seconds():
    """Önceki yüklemenin gerçek süresi (bu bilgisayarda); hiç yüklenmediyse ~70 sn varsay."""
    try:
        return max(5.0, float(_load_time_file().read_text()))
    except (OSError, ValueError):
        return 70.0


class CloneServer:
    """Klonlama süreci (analiz penceresi açıkken yaşar; model bir kez yüklenir)."""

    def __init__(self, threads):
        self.started_at = time.monotonic()
        import multiprocessing as mp
        ctx = mp.get_context("spawn")
        self.req, self.resp = ctx.Queue(), ctx.Queue()
        for q in (self.req, self.resp):  # süreç ölse bile çıkışta okunmamış veriyi bekleyip asılı kalma
            q.cancel_join_thread()
        self.proc = ctx.Process(target=_server, args=(self.req, self.resp, threads), daemon=True)
        self.proc.start()
        self.ready = False
        self.threads = threads

    def alive(self):
        return self.proc.is_alive()

    def stop(self):
        try:
            self.req.put(None)
            self.proc.join(1.0)
        except Exception:
            pass
        if self.proc.is_alive():
            self.proc.terminate()
            self.proc.join(2.0)


_SERVER = {"s": None}


def get_server(threads):
    s = _SERVER["s"]
    if s is None or not s.alive() or s.threads != threads:
        if s is not None:
            s.stop()
        s = _SERVER["s"] = CloneServer(threads)
    return s


def prewarm(threads):
    """Kullanıcı klonlamayla ilgilenmeye başlayınca modeli arka planda yüklemeye başla (~1 dk)."""
    get_server(threads)


def release_model():
    """Analiz penceresi kapanınca klonlama süreci biter; bellek tamamen geri verilir."""
    s = _SERVER["s"]
    _SERVER["s"] = None
    if s is not None:
        s.stop()


class CloneWorker(QThread):
    """Arayüz tarafı: isteği klonlama sürecine gönderir, ilerlemeyi ve sonucu sinyal olarak verir."""
    progress = pyqtSignal(float, str)
    done = pyqtSignal(object)  # 24 kHz float32
    failed = pyqtSignal(str)
    _job = 0

    def __init__(self, reference_16k, text, lang, threads):
        super().__init__()
        self.ref, self.text, self.lang, self.threads = reference_16k, text, lang, threads
        self.cancelled = False

    def run(self):
        import queue as _q
        try:
            ref = best_reference(self.ref, 16000)
            ref24 = np.interp(np.linspace(0, len(ref) - 1, int(len(ref) * SR / 16000)),
                              np.arange(len(ref)), ref).astype(np.float32)
            srv = get_server(self.threads)
            while True:  # ön yüklemeden kalan mesajlar: model hazır mı?
                try:
                    kind, _j, _p = srv.resp.get_nowait()
                except _q.Empty:
                    break
                if kind == "ready":
                    srv.ready = True
                elif kind == "failed" and _j is None:
                    raise RuntimeError(_p)
            CloneWorker._job += 1
            job = CloneWorker._job
            loading = not srv.ready
            expected = expected_load_seconds()

            def load_tick():  # model yüklenirken süreç mesaj gönderemez (GIL): yüzdeyi burada tahmin et
                f = min(0.97, (time.monotonic() - srv.started_at) / expected)
                self.progress.emit(0.4 * f, "load")
            if loading:
                load_tick()
            srv.req.put((job, ref24, self.text, self.lang))
            while True:
                if self.cancelled:  # durdur: süreci kes (model bir sonraki üretimde yeniden yüklenir)
                    release_model()
                    return
                if not srv.alive():
                    raise RuntimeError("clone process exited")
                try:
                    kind, j, payload = srv.resp.get(timeout=0.2)
                except _q.Empty:
                    if loading and not srv.ready:
                        load_tick()
                    continue
                if kind == "ready":
                    srv.ready = True
                    try:  # gerçek yükleme süresini sonraki tahminler için sakla
                        _load_time_file().write_text(f"{time.monotonic() - srv.started_at:.1f}")
                    except OSError:
                        pass
                    continue
                if j is not None and j != job:
                    continue  # eski bir isteğin geç gelen mesajı
                if kind == "progress":
                    stage, f = payload
                    if stage == "load":
                        continue  # yükleme yüzdesi arayüz tarafında tahmin ediliyor
                    else:
                        total = 0.4 + 0.6 * f if loading else f
                    self.progress.emit(total, stage)
                elif kind == "done":
                    self.done.emit(payload)
                    return
                elif kind == "failed":
                    raise RuntimeError(payload)
        except Exception as e:
            self.failed.emit(f"{type(e).__name__}: {e}")
