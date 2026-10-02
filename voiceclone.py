"""Ses klonlama (isteğe bağlı eklenti, gelişmiş mod): bir konuşmacının sesinden (ör. gürültüsü
ayıklanmış bölüm) ses rengini öğrenip verilen metni o sesle yeniden üretir.

Model: Chatterbox Multilingual (Resemble AI, MIT lisansı), ONNX sürümü (onnx-community).
Türkçe dahil 23 dil; sıfırdan klonlama (eğitim gerekmez). Yalnızca onnxruntime + numpy kullanır:
PyTorch gerekmez. Model dosyaları (~1,55 GB, 4-bit dil modeli) ilk kullanımda bir kez indirilir ve
kullanıcı veri klasöründeki plugins/ altında kalır (oturum temizliğinden etkilenmez).
"""
import re
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


def _norm_text(text):
    """Chatterbox'ın beklediği biçim: boşlukları sadeleştir, sonda noktalama olsun."""
    t = " ".join(text.split())
    if t and t[-1] not in ".!?…,;:":
        t += "."
    return t


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


class VoiceClone:
    """Chatterbox ONNX çıkarımı. `reference`: 24 kHz mono float32 konuşmacı örneği."""

    def __init__(self, threads=4):
        import onnxruntime as ort
        from tokenizers import Tokenizer

        d = plugin_dir()
        so = ort.SessionOptions()
        so.intra_op_num_threads = threads
        so.inter_op_num_threads = 1
        mk = lambda f: ort.InferenceSession(str(d / "onnx" / f), so, providers=["CPUExecutionProvider"])
        self.enc = mk("speech_encoder.onnx")
        self.emb = mk("embed_tokens.onnx")
        self.lm = mk("language_model_q4.onnx")
        self.dec = mk("conditional_decoder.onnx")
        self.tok = Tokenizer.from_file(str(d / "tokenizer.json"))
        self._spk = None

    def set_speaker(self, reference):
        cond_emb, prompt_token, x_vector, prompt_feat = self.enc.run(
            None, {"audio_values": reference[np.newaxis, :].astype(np.float32)})
        self._spk = (cond_emb, prompt_token, x_vector, prompt_feat)

    def _tokens(self, text, lang, exaggeration, max_new, cancel):
        cond_emb, _, _, _ = self._spk
        ids = np.array([self.tok.encode(f"[{lang}]{_norm_text(text)}").ids], dtype=np.int64)
        pos = np.where(ids >= START, 0, np.arange(ids.shape[1])[np.newaxis, :] - 1)
        feed = {"input_ids": ids, "position_ids": pos.astype(np.int64),
                "exaggeration": np.array([exaggeration], dtype=np.float32)}
        out = np.array([[START]], dtype=np.int64)
        past = attn = None
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
            feed["input_ids"] = nxt
            feed["position_ids"] = np.full((1, 1), i + 1, dtype=np.int64)
            attn = np.concatenate([attn, np.ones((1, 1), dtype=np.int64)], axis=1)
            for j, k in enumerate(past):
                past[k] = present[j]
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
            max_new = int(min(1000, max(60, len(s) / 14 * TOKENS_PER_SEC * 1.6)))
            toks = self._tokens(s, lang, exaggeration, max_new, cancel)
            if toks is None:
                return None
            toks = np.concatenate([prompt_token, toks], axis=1)
            wav = self.dec.run(None, {"speech_tokens": toks, "speaker_embeddings": x_vector,
                                      "speaker_features": prompt_feat})[0]
            pieces += [np.squeeze(wav, axis=0).astype(np.float32), gap]
            if progress:
                progress((k + 1) / len(sents))
        return np.concatenate(pieces) if pieces else np.zeros(0, np.float32)


class CloneWorker(QThread):
    """Arka planda: konuşmacıyı öğren → metni o sesle üret."""
    progress = pyqtSignal(float, str)
    done = pyqtSignal(object)  # 24 kHz float32
    failed = pyqtSignal(str)

    def __init__(self, reference_16k, text, lang, threads):
        super().__init__()
        self.ref, self.text, self.lang, self.threads = reference_16k, text, lang, threads
        self.cancelled = False

    def run(self):
        try:
            self.progress.emit(0.0, "load")
            vc = VoiceClone(self.threads)
            ref = best_reference(self.ref, 16000)
            ref24 = np.interp(np.linspace(0, len(ref) - 1, int(len(ref) * SR / 16000)),
                              np.arange(len(ref)), ref).astype(np.float32)
            self.progress.emit(0.0, "speaker")
            vc.set_speaker(ref24)
            wav = vc.synthesize(self.text, self.lang, progress=lambda f: self.progress.emit(f, "synth"),
                                cancel=lambda: self.cancelled)
            if wav is not None:
                self.done.emit(wav)
        except Exception as e:
            self.failed.emit(f"{type(e).__name__}: {e}")
