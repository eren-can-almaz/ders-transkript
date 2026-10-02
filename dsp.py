"""Sinyal işleme (yalnızca numpy): STFT/ISTFT, dalgacık dönüşümü, gürültü ayıklama, konuşma
yükseltme, sessizlik çıkarma ve spektrogram görüntüsü üretimi. Gelişmiş moddaki analiz ekranı kullanır.
"""
import math

import numpy as np

# ------------------------------------------------------------------ pencereler / STFT

WINDOWS = ["hann", "hamming", "blackman", "gauss", "rect"]


def window(name, n):
    if name == "hamming":
        return np.hamming(n)
    if name == "blackman":
        return np.blackman(n)
    if name == "gauss":
        k = np.arange(n) - (n - 1) / 2
        return np.exp(-0.5 * (k / (n / 6)) ** 2)
    if name == "rect":
        return np.ones(n)
    return np.hanning(n + 2)[1:-1]  # periyodik Hann (ISTFT için kusursuz örtüşme)


def stft(x, n_fft=1024, hop=256, win="hann"):
    """(kare sayısı × n_fft/2+1) karmaşık spektrum. Kenarlar yansıtılarak doldurulur."""
    w = window(win, n_fft).astype(np.float32)
    pad = n_fft // 2
    xp = np.pad(x.astype(np.float32), (pad, pad), mode="reflect" if len(x) > pad else "constant")
    n_frames = 1 + max(0, (len(xp) - n_fft) // hop)
    idx = np.arange(n_fft)[None, :] + hop * np.arange(n_frames)[:, None]
    return np.fft.rfft(xp[idx] * w, axis=1)


def istft(S, n_fft=1024, hop=256, win="hann", length=None):
    """Örtüş-topla ile ters STFT (pencere karesiyle normalize edilir)."""
    w = window(win, n_fft).astype(np.float32)
    frames = np.fft.irfft(S, n=n_fft, axis=1).astype(np.float32) * w
    n = n_fft + hop * (len(frames) - 1)
    y = np.zeros(n, np.float32)
    norm = np.zeros(n, np.float32)
    for i, f in enumerate(frames):
        s = i * hop
        y[s:s + n_fft] += f
        norm[s:s + n_fft] += w * w
    y /= np.maximum(norm, 1e-8)
    pad = n_fft // 2
    y = y[pad:]
    return y[:length] if length is not None else y[: len(y) - pad]


def to_db(mag, floor=-120.0):
    return np.maximum(20 * np.log10(np.maximum(mag, 1e-12)), floor)


# ------------------------------------------------------------------ dalgacık dönüşümü

WAVELETS = ["morlet", "mexhat", "paul"]


def cwt(x, sr, wavelet="morlet", n_scales=96, fmin=60.0, fmax=None, out_cols=1600):
    """Sürekli dalgacık dönüşümü (Torrence & Compo, FFT ile). Döner: (|katsayı| [ölçek×zaman], frekanslar).

    Frekanslar logaritmik aralıklı, yüksekten düşüğe sıralı. Zaman ekseni `out_cols` sütuna seyreltilir.
    """
    fmax = fmax or sr / 2 * 0.95
    n = len(x)
    N = 1 << int(math.ceil(math.log2(max(n, 2))))
    X = np.fft.fft(np.pad(x.astype(np.float64), (0, N - n)))
    w = 2 * np.pi * np.fft.fftfreq(N, d=1 / sr)  # açısal frekans
    if wavelet == "mexhat":       # DOG m=2
        factor = 2 * np.pi / math.sqrt(2.5)
    elif wavelet == "paul":       # m=4
        m = 4
        factor = 4 * np.pi / (2 * m + 1)
    else:                         # Morlet w0=6
        w0 = 6.0
        factor = 4 * np.pi / (w0 + math.sqrt(2 + w0 ** 2))
    freqs = np.geomspace(fmax, fmin, n_scales)
    scales = 1.0 / (freqs * factor)
    step = max(1, n // out_cols)
    out = np.empty((n_scales, len(range(0, n, step))), np.float32)
    for i, s in enumerate(scales):
        sw = s * w
        if wavelet == "mexhat":  # analitik biçim (yalnız pozitif frekans ×2): genlik faza göre salınmaz
            psi = 2 * (sw > 0) * (1 / math.sqrt(math.gamma(2.5))) * sw ** 2 * np.exp(-sw ** 2 / 2)
        elif wavelet == "paul":
            psi = (2 ** m / math.sqrt(m * math.factorial(2 * m - 1))) * np.where(sw > 0, sw, 0) ** m \
                * np.exp(-np.where(sw > 0, sw, 0)) * (sw > 0)
        else:
            psi = np.pi ** -0.25 * np.exp(-(sw - w0) ** 2 / 2) * (sw > 0)
        psi = psi * np.sqrt(2 * np.pi * s * sr)
        coef = np.fft.ifft(X * np.conj(psi))[:n]
        out[i] = np.abs(coef[::step]).astype(np.float32)
    return out, freqs


# ------------------------------------------------------------------ işleme

def noise_profile(mag, percentile=10):
    """Her frekans kutusu için gürültü seviyesi: en sessiz karelerin genliği."""
    return np.percentile(mag, percentile, axis=0)


def _smooth(m, k_t=3, k_f=3):
    """Maskeyi zaman ve frekansta yumuşat (müzikal gürültüyü azaltır)."""
    if k_t > 1:
        ker = np.ones(k_t) / k_t
        m = np.apply_along_axis(lambda v: np.convolve(v, ker, mode="same"), 0, m)
    if k_f > 1:
        ker = np.ones(k_f) / k_f
        m = np.apply_along_axis(lambda v: np.convolve(v, ker, mode="same"), 1, m)
    return m


def denoise_spec(S, strength=0.6, profile=None):
    """Spektral kapılama (Wiener benzeri): kazanç = sqrt(max(0, 1 − (α·N/|X|)²)), taban 0.05."""
    mag = np.abs(S)
    N = noise_profile(mag) if profile is None else profile
    alpha = 1.0 + 3.0 * strength
    g = np.sqrt(np.maximum(0.0, 1.0 - (alpha * N[None, :] / np.maximum(mag, 1e-10)) ** 2))
    g = np.maximum(_smooth(g), 0.05 * (1 - strength) + 0.02)
    return S * g


def boost_spec(S, sr, n_fft, gain_db=6.0):
    """Konuşma bandını (300–3400 Hz) yükselt, 80 Hz altını kes."""
    f = np.fft.rfftfreq(n_fft, 1 / sr)
    band = np.clip((f - 200) / 100, 0, 1) * np.clip((4000 - f) / 600, 0, 1)
    g = 10 ** (gain_db * band / 20) * np.clip((f - 40) / 40, 0, 1)
    return S * g[None, :]


def normalize(y, peak_db=-1.0):
    p = np.max(np.abs(y)) if len(y) else 0
    return y * (10 ** (peak_db / 20) / p) if p > 1e-6 else y


def remove_silence(y, sr, thresh_db=-40.0, min_sil=0.6, pad=0.15):
    """Uzun sessizlikleri çıkar (anlamlı kısımları bırak). Döner: (yeni sinyal, çıkarılan süre sn)."""
    frame = int(0.02 * sr)
    n = len(y) // frame
    if n == 0:
        return y, 0.0
    rms = np.sqrt((y[: n * frame].reshape(n, frame) ** 2).mean(axis=1))
    db = 20 * np.log10(np.maximum(rms, 1e-9))
    loud = db > (db.max() + thresh_db)
    keep = loud.copy()
    p = int(pad / 0.02)
    for i in np.flatnonzero(loud):  # konuşmanın etrafında biraz pay bırak
        keep[max(0, i - p): i + p + 1] = True
    # kısa sessizlikleri (cümle içi duraklamalar) koru
    min_f = int(min_sil / 0.02)
    i = 0
    while i < n:
        if not keep[i]:
            j = i
            while j < n and not keep[j]:
                j += 1
            if j - i < min_f:
                keep[i:j] = True
            i = j
        else:
            i += 1
    mask = np.repeat(keep, frame)
    out = np.concatenate([y[: n * frame][mask], y[n * frame:]])
    return out, (len(y) - len(out)) / sr


def process(x, sr, denoise=0.0, boost_db=0.0, trim=None, n_fft=1024, hop=256, win="hann",
            profile=None, chunk_sec=60, progress=None):
    """İşleme zinciri: gürültü ayıkla → konuşmayı yükselt → (isteğe bağlı) sessizlikleri çıkar.

    Uzun kayıtlar 60 sn'lik bloklarla (1 sn örtüşmeli, çapraz geçişli) işlenir; bellek sınırlı kalır.
    Döner: (işlenmiş sinyal, çıkarılan sessizlik sn).
    """
    if not denoise and not boost_db:
        y = x.astype(np.float32)
    else:
        if denoise and profile is None:  # gürültü profili: kaydın tamamından örneklenmiş bölümler
            sample = x if len(x) <= sr * 120 else np.concatenate(
                [x[i: i + sr * 10] for i in np.linspace(0, len(x) - sr * 10, 12).astype(int)])
            profile = noise_profile(np.abs(stft(sample, n_fft, hop, win)))
        block, ov = int(chunk_sec * sr), sr
        y = np.zeros(len(x), np.float32)
        weight = np.zeros(len(x), np.float32)
        starts = list(range(0, max(1, len(x)), block))
        for k, s in enumerate(starts):
            a, b = max(0, s - ov), min(len(x), s + block + ov)
            seg = x[a:b]
            S = stft(seg, n_fft, hop, win)
            if denoise:
                S = denoise_spec(S, denoise, profile)
            if boost_db:
                S = boost_spec(S, sr, n_fft, boost_db)
            out = istft(S, n_fft, hop, win, length=len(seg))
            ramp = np.ones(len(seg), np.float32)  # blok kenarlarında doğrusal çapraz geçiş
            if a > 0:
                ramp[: 2 * ov] = np.linspace(0, 1, 2 * ov)
            if b < len(x):
                ramp[-2 * ov:] = np.minimum(ramp[-2 * ov:], np.linspace(1, 0, 2 * ov))
            y[a:b] += out * ramp
            weight[a:b] += ramp
            if progress:
                progress((k + 1) / len(starts))
        y /= np.maximum(weight, 1e-6)
        if boost_db:
            y = normalize(y)
    removed = 0.0
    if trim is not None:
        y, removed = remove_silence(y, sr, thresh_db=trim)
    return y.astype(np.float32), removed


# ------------------------------------------------------------------ görüntü

_CMAPS = {  # (konum, renk) çapa noktaları
    "magma": [(0, "#000004"), (.25, "#3b0f70"), (.5, "#8c2981"), (.75, "#de4968"), (.9, "#fe9f6d"), (1, "#fcfdbf")],
    "viridis": [(0, "#440154"), (.25, "#3b528b"), (.5, "#21918c"), (.75, "#5ec962"), (1, "#fde725")],
    "gray": [(0, "#000000"), (1, "#ffffff")],
    "diverge": [(0, "#2166ac"), (.5, "#f7f7f7"), (1, "#b2182b")],
}
CMAPS = ["magma", "viridis", "gray"]


def colormap(name):
    pts = _CMAPS.get(name, _CMAPS["magma"])
    xs = np.array([p for p, _ in pts])
    cols = np.array([[int(c[i:i + 2], 16) for i in (1, 3, 5)] for _, c in pts], np.float32)
    t = np.linspace(0, 1, 256)
    return np.stack([np.interp(t, xs, cols[:, k]) for k in range(3)], axis=1).astype(np.uint8)


def hz_to_mel(f):
    return 2595 * np.log10(1 + np.asarray(f) / 700)


def mel_to_hz(m):
    return 700 * (10 ** (np.asarray(m) / 2595) - 1)


def freq_rows(axis, fmin, fmax, rows):
    """Görüntünün her satırına karşılık gelen frekans (üstten alta: yüksek → düşük)."""
    if axis == "log":
        f = np.geomspace(max(fmin, 20), fmax, rows)
    elif axis == "mel":
        f = mel_to_hz(np.linspace(hz_to_mel(fmin), hz_to_mel(fmax), rows))
    else:
        f = np.linspace(fmin, fmax, rows)
    return f[::-1]


def remap_freq(db, src_freqs, axis, fmin, fmax, rows):
    """[zaman × frekans] dB dizisini istenen frekans eksenine (satırlar) yeniden örnekler → [satır × zaman]."""
    target = freq_rows(axis, fmin, fmax, rows)
    order = np.argsort(src_freqs)
    sf = np.asarray(src_freqs)[order]
    d = db[:, order]
    return np.stack([np.interp(target, sf, col) for col in d], axis=1), target


def downsample_time(arr, cols):
    """[satır × zaman] → en fazla `cols` sütun (blok ortalaması)."""
    n = arr.shape[1]
    if n <= cols:
        return arr
    edges = np.linspace(0, n, cols + 1).astype(int)
    return np.stack([arr[:, a:max(b, a + 1)].mean(axis=1) for a, b in zip(edges[:-1], edges[1:])], axis=1)


def to_rgb(db, vmin, vmax, lut):
    idx = np.clip((db - vmin) / max(vmax - vmin, 1e-6) * 255, 0, 255).astype(np.uint8)
    return np.ascontiguousarray(lut[idx])
