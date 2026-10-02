"""Sinyal analizi penceresi (gelişmiş mod): spektrogram (STFT / dalgacık), gürültü ayıklama,
konuşma yükseltme, sessizlik çıkarma; önce / sonra / fark görünümü ve yeniden sentezlenmiş sesi dinleme.
"""
import math
import tempfile
import time
import wave
from pathlib import Path

import numpy as np
from PyQt6.QtCore import QPointF, QRectF, Qt, QThread, QUrl, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QImage, QPainter, QPen
from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel,
    QPushButton, QScrollArea, QSlider, QSpinBox, QSplitter, QVBoxLayout, QWidget,
)

import dsp
from core import SR, decode_audio, fmt_time, user_data_dir
from i18n import tr
from theme import colors

ROWS, COLS = 360, 1400  # spektrogram görüntü çözünürlüğü


def write_wav(path, y, sr=SR):
    pcm = (np.clip(y, -1, 1) * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())


class SpectrogramView(QWidget):
    """Eksenli spektrogram: zaman (s) × frekans (Hz), renk çubuğu, fare ile okuma."""
    L, R, T, B = 62, 64, 24, 30

    def __init__(self):
        super().__init__()
        self.setMinimumHeight(190)
        self.setMouseTracking(True)
        self.img = None
        self.title = ""
        self.hover = None

    def set_data(self, rgb, db, t0, t1, freqs, title, vmin, vmax, lut, unit="dB"):
        h, w, _ = rgb.shape
        self._rgb = rgb  # QImage belleği paylaşır: dizi canlı kalmalı
        self.img = QImage(rgb.data, w, h, 3 * w, QImage.Format.Format_RGB888)
        self.db, self.t0, self.t1, self.freqs = db, t0, t1, freqs
        self.title, self.vmin, self.vmax, self.lut, self.unit = title, vmin, vmax, lut, unit
        self.update()

    def clear(self, title=""):
        self.img = None
        self.title = title
        self.update()

    def _plot(self):
        return QRectF(self.L, self.T, self.width() - self.L - self.R, self.height() - self.T - self.B)

    def _row_of_freq(self, f):
        fr = self.freqs  # yüksekten düşüğe
        return float(np.interp(-f, -fr, np.arange(len(fr))))

    def paintEvent(self, e):
        c = colors()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        r = self._plot()
        f = QFont(self.font())
        f.setPointSizeF(max(7.5, f.pointSizeF() - 1.5))
        p.setFont(f)
        p.setPen(QColor(c["text"]))
        bold = QFont(f)
        bold.setBold(True)
        p.setFont(bold)
        p.drawText(QRectF(r.left(), 0, r.width(), self.T - 4), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom, self.title)
        p.setFont(f)
        if self.img is None:
            p.fillRect(r, QColor(c["fill"]))
            return
        p.drawImage(r, self.img)
        muted = QColor(c["muted"])
        p.setPen(muted)
        # zaman ekseni
        span = max(self.t1 - self.t0, 1e-6)
        step = next(s for s in (0.1, 0.2, 0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300, 600) if span / s <= 10)
        t = math.ceil(self.t0 / step) * step
        while t <= self.t1 + 1e-9:
            x = r.left() + (t - self.t0) / span * r.width()
            p.drawLine(QPointF(x, r.bottom()), QPointF(x, r.bottom() + 4))
            p.drawText(QRectF(x - 30, r.bottom() + 5, 60, 16), Qt.AlignmentFlag.AlignHCenter, f"{t:g}")
            t += step
        p.drawText(QRectF(r.right() + 6, r.bottom() + 5, 30, 16), Qt.AlignmentFlag.AlignLeft, "s")
        # frekans ekseni
        fmax, fmin = self.freqs[0], self.freqs[-1]
        lin = abs((self.freqs[0] - self.freqs[1]) - (self.freqs[-2] - self.freqs[-1])) < 1e-3
        ticks = [0, 1000, 2000, 3000, 4000, 5000, 6000, 7000, 8000] if lin else \
            [50, 100, 200, 500, 1000, 2000, 4000, 8000]
        last_y = None
        for fq in sorted(ticks, reverse=True):  # yukarıdan aşağı; birbirine çok yakın etiketleri atla
            if fq < fmin - 1 or fq > fmax + 1:
                continue
            y = r.top() + self._row_of_freq(fq) / (len(self.freqs) - 1) * r.height()
            if last_y is not None and y - last_y < 16:
                continue
            last_y = y
            p.drawLine(QPointF(r.left() - 4, y), QPointF(r.left(), y))
            label = f"{fq / 1000:g}k" if fq >= 1000 else f"{fq}"
            p.drawText(QRectF(0, y - 8, r.left() - 7, 16), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, label)
        p.save()
        p.translate(12, r.center().y())
        p.rotate(-90)
        p.drawText(QRectF(-40, -10, 80, 14), Qt.AlignmentFlag.AlignCenter, "Hz")
        p.restore()
        # renk çubuğu
        cb = QRectF(r.right() + 12, r.top(), 10, r.height())
        for i in range(int(cb.height())):
            col = self.lut[int(255 * (1 - i / max(cb.height() - 1, 1)))]
            p.setPen(QColor(int(col[0]), int(col[1]), int(col[2])))
            p.drawLine(QPointF(cb.left(), cb.top() + i), QPointF(cb.right(), cb.top() + i))
        p.setPen(muted)
        for v, yy in ((self.vmax, cb.top()), ((self.vmax + self.vmin) / 2, cb.center().y()), (self.vmin, cb.bottom())):
            p.drawText(QRectF(cb.right() + 3, yy - 8, 40, 16), Qt.AlignmentFlag.AlignVCenter, f"{v:.0f}")
        p.drawText(QRectF(cb.left() - 6, 2, 60, self.T - 6), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom, self.unit)
        # fare ile okuma
        if self.hover:
            x, y, text = self.hover
            p.setPen(QPen(QColor(255, 255, 255, 140), 1, Qt.PenStyle.DashLine))
            p.drawLine(QPointF(x, r.top()), QPointF(x, r.bottom()))
            p.drawLine(QPointF(r.left(), y), QPointF(r.right(), y))
            box = QRectF(r.right() - 190, r.top() + 6, 184, 20)
            p.fillRect(box, QColor(0, 0, 0, 160))
            p.setPen(QColor("white"))
            p.drawText(box, Qt.AlignmentFlag.AlignCenter, text)

    def mouseMoveEvent(self, e):
        r = self._plot()
        pos = e.position()
        if self.img is None or not r.contains(pos):
            self.hover = None
        else:
            fx = (pos.x() - r.left()) / r.width()
            fy = (pos.y() - r.top()) / r.height()
            t = self.t0 + fx * (self.t1 - self.t0)
            row = min(len(self.freqs) - 1, max(0, int(fy * (len(self.freqs) - 1))))
            col = min(self.db.shape[1] - 1, max(0, int(fx * (self.db.shape[1] - 1))))
            self.hover = (pos.x(), pos.y(), tr("an_hover", t=f"{t:.2f}", f=f"{self.freqs[row]:.0f}",
                                               db=f"{self.db[row, col]:.1f}", unit=self.unit))
        self.update()

    def leaveEvent(self, e):
        self.hover = None
        self.update()


class ComputeWorker(QThread):
    """Seçilen bölüm için önce/sonra/fark spektrogramlarını hesaplar (arka planda)."""
    done = pyqtSignal(dict)
    failed = pyqtSignal(str)

    def __init__(self, win, params):
        super().__init__()
        self.win, self.p = win, params

    def run(self):
        try:
            t_start = time.time()
            w, p = self.win, self.p
            if w.audio is None:
                w.audio = decode_audio(str(w.path))
            a = w.audio
            s0 = int(p["start"] * SR)
            seg = a[s0: s0 + int(p["length"] * SR)]
            if len(seg) < SR // 4:
                raise ValueError("segment too short")
            proc = p["denoise"] or p["boost"] or p["trim"] is not None
            after, removed = (dsp.process(seg, SR, denoise=p["denoise"], boost_db=p["boost"], trim=p["trim"],
                                          profile=w.noise_profile(p)) if proc else (None, 0.0))
            before_db, fr = self._spec(seg, p)
            ref = before_db.max()
            out = {"seg": seg, "after": after, "removed": removed, "freqs": fr, "ref": ref,
                   "before": before_db - ref, "t0": p["start"], "t1": p["start"] + len(seg) / SR}
            if after is not None:
                after_db, _ = self._spec(after, p)
                out["after_db"] = after_db - ref
                out["t1_after"] = p["start"] + len(after) / SR
                if p["trim"] is None:
                    out["diff"] = out["before"] - out["after_db"]
                if p["denoise"]:  # kabaca gürültü azaltma: en sessiz %10 kısımdaki enerji düşüşü
                    q = np.percentile(out["before"], 10)
                    m = out["before"] <= q
                    out["nr_db"] = float(np.mean(out["before"][m] - out["after_db"][m]))
            out["ms"] = int((time.time() - t_start) * 1000)
            self.done.emit(out)
        except Exception as e:
            self.failed.emit(f"{type(e).__name__}: {e}")

    def _spec(self, x, p):
        if p["transform"] == "cwt":
            mag, freqs = dsp.cwt(x, SR, p["wavelet"], n_scales=p["scales"], fmin=40, out_cols=COLS)
            db = dsp.to_db(mag).T                        # [zaman × frekans]
        else:
            S = dsp.stft(x, p["n_fft"], p["hop"], p["window"])
            db = dsp.to_db(np.abs(S))
            freqs = np.fft.rfftfreq(p["n_fft"], 1 / SR)
        fmin = 40 if p["axis"] != "linear" else 0
        img, rows = dsp.remap_freq(db, freqs, p["axis"], fmin, SR / 2, ROWS)
        return dsp.downsample_time(img, COLS), rows


class ExportWorker(QThread):
    """Kaydın tamamını işleyip WAV olarak yazar."""
    progress = pyqtSignal(float)
    done = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, win, params, dest):
        super().__init__()
        self.win, self.p, self.dest = win, params, dest

    def run(self):
        try:
            w, p = self.win, self.p
            if w.audio is None:
                w.audio = decode_audio(str(w.path))
            y, _ = dsp.process(w.audio, SR, denoise=p["denoise"], boost_db=p["boost"], trim=p["trim"],
                               profile=w.noise_profile(p), progress=self.progress.emit)
            write_wav(self.dest, y)
            self.done.emit(str(self.dest))
        except Exception as e:
            self.failed.emit(f"{type(e).__name__}: {e}")


class AnalysisWindow(QWidget):
    """Gelişmiş: bir öğenin sesi için spektrogram ve işleme ekranı."""
    add_to_list = pyqtSignal(str)  # işlenmiş WAV'ı listeye ekle

    def __init__(self, item, parent=None, start=None, end=None):
        super().__init__(parent, Qt.WindowType.Window)
        self.setObjectName("content")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.item = item
        self.path = item.audio
        self.audio = None
        self._profiles = {}
        self.worker = None
        self.exporter = None
        self.result = None
        self.tmp = Path(tempfile.mkdtemp(prefix="ders_transkript_an_"))
        self.setWindowTitle(tr("an_title", name=item.title))
        self.resize(1320, 900)

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ---- sol: ayarlar
        side = QFrame(objectName="sidebar")
        side.setFixedWidth(360)
        sa = QScrollArea()
        sa.setWidgetResizable(True)
        sa.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        inner = QWidget()
        f = QVBoxLayout(inner)
        f.setContentsMargins(20, 20, 20, 20)
        f.setSpacing(8)
        sa.setWidget(inner)
        sl = QVBoxLayout(side)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.addWidget(sa)

        def section(key):
            lbl = QLabel(tr(key), objectName="sectionTitle")
            f.addSpacing(10)
            f.addWidget(lbl)

        def row(key, widget):
            g = QHBoxLayout()
            lbl = QLabel(tr(key), objectName="muted")
            g.addWidget(lbl)
            g.addStretch()
            widget.setFixedWidth(176)
            g.addWidget(widget)
            f.addLayout(g)
            return widget

        def combo(items):
            cb = QComboBox()
            for key, data in items:
                cb.addItem(tr(key), data)
            return cb

        dur = item.duration or 60
        section("an_segment")
        self.start = row("an_start", QDoubleSpinBox(decimals=1, maximum=max(0.0, dur - 1), suffix=" s"))
        self.length = row("an_length", QDoubleSpinBox(decimals=1, minimum=1, maximum=300, value=min(30, dur), suffix=" s"))
        if start is not None:  # dalgada seçilen aralıkla aç
            self.start.setValue(start)
            self.length.setValue(min(300.0, max(1.0, end - start)))

        section("an_transform")
        self.transform = row("an_method", combo([("tf_stft", "stft"), ("tf_cwt", "cwt")]))
        self.stft_box = QWidget()
        sb = QVBoxLayout(self.stft_box)
        sb.setContentsMargins(0, 0, 0, 0)
        f_save = f
        f = sb
        self.window = row("an_window", combo([(f"win_{w}", w) for w in dsp.WINDOWS]))
        self.n_fft = row("an_nfft", combo([(str(n), n) for n in (256, 512, 1024, 2048, 4096)]))
        self.n_fft.setCurrentIndex(2)
        self.overlap = row("an_overlap", combo([("50 %", 0.5), ("75 %", 0.75), ("87.5 %", 0.875)]))
        self.overlap.setCurrentIndex(1)
        f = f_save
        f.addWidget(self.stft_box)
        self.cwt_box = QWidget()
        cb_l = QVBoxLayout(self.cwt_box)
        cb_l.setContentsMargins(0, 0, 0, 0)
        f = cb_l
        self.wavelet = row("an_wavelet", combo([(f"wl_{w}", w) for w in dsp.WAVELETS]))
        self.scales = row("an_scales", QSpinBox(minimum=24, maximum=256, value=96))
        f = f_save
        f.addWidget(self.cwt_box)
        self.transform.currentIndexChanged.connect(self._on_transform)

        section("an_display")
        self.axis = row("an_faxis", combo([("fa_linear", "linear"), ("fa_log", "log"), ("fa_mel", "mel")]))
        self.axis.setCurrentIndex(2)
        self.range = row("an_range", combo([("60 dB", 60), ("80 dB", 80), ("100 dB", 100)]))
        self.range.setCurrentIndex(1)
        self.cmap = row("an_cmap", combo([(f"cm_{c}", c) for c in dsp.CMAPS]))

        section("an_processing")
        self.denoise = QCheckBox(tr("an_denoise"))
        f.addWidget(self.denoise)
        self.strength = self._slider(f, "an_strength", 0, 100, 60, "%")
        self.boost = QCheckBox(tr("an_boost"))
        f.addWidget(self.boost)
        self.gain = self._slider(f, "an_gain", 0, 18, 6, " dB")
        self.trim = QCheckBox(tr("an_trim"))
        f.addWidget(self.trim)
        self.thresh = self._slider(f, "an_thresh", 20, 60, 40, " dB")
        f.addSpacing(14)
        self.compute_btn = QPushButton(tr("an_compute"), objectName="primary")
        self.compute_btn.clicked.connect(self.compute)
        f.addWidget(self.compute_btn)
        f.addStretch()
        root.addWidget(side)

        # ---- sağ: spektrogramlar + dinleme
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(28, 22, 28, 18)
        rl.setSpacing(12)
        head = QHBoxLayout()
        title = QLabel(item.title, objectName="h1")
        head.addWidget(title, 1)
        rl.addLayout(head)
        self.info = QLabel(objectName="faint")
        rl.addWidget(self.info)
        split = QSplitter(Qt.Orientation.Vertical)
        self.v_before, self.v_after, self.v_diff = SpectrogramView(), SpectrogramView(), SpectrogramView()
        for v in (self.v_before, self.v_after, self.v_diff):
            split.addWidget(v)
        rl.addWidget(split, 1)
        play = QHBoxLayout()
        play.setSpacing(8)
        self.play_orig = QPushButton(objectName="tinted")
        self.play_proc = QPushButton(objectName="tinted")
        self.export_btn = QPushButton(tr("an_export"))
        self.add_btn = QPushButton(tr("an_to_list"), objectName="primary")
        self.play_orig.clicked.connect(lambda: self._play("orig"))
        self.play_proc.clicked.connect(lambda: self._play("proc"))
        self.export_btn.clicked.connect(lambda: self.export(to_list=False))
        self.add_btn.clicked.connect(lambda: self.export(to_list=True))
        for b in (self.play_orig, self.play_proc):
            play.addWidget(b)
        play.addStretch()
        play.addWidget(self.export_btn)
        play.addWidget(self.add_btn)
        rl.addLayout(play)
        root.addWidget(right, 1)

        self.player = QMediaPlayer(self)
        self.out = QAudioOutput(self)
        self.player.setAudioOutput(self.out)
        self.player.playbackStateChanged.connect(lambda *_: self._render_play())
        self._playing = None
        self._on_transform()
        self._render_play()
        self._set_enabled_outputs(False)
        self.v_before.clear(tr("an_before"))
        self.v_after.clear(tr("an_after"))
        self.v_diff.clear(tr("an_diff"))
        self.compute()

    def _slider(self, f, key, lo, hi, val, unit):
        g = QHBoxLayout()
        g.setContentsMargins(26, 0, 0, 0)
        lbl = QLabel(tr(key), objectName="faint")
        s = QSlider(Qt.Orientation.Horizontal, minimum=lo, maximum=hi, value=val)
        v = QLabel(f"{val}{unit}", objectName="faint")
        v.setFixedWidth(42)
        s.valueChanged.connect(lambda x: v.setText(f"{x}{unit}"))
        g.addWidget(lbl)
        g.addWidget(s, 1)
        g.addWidget(v)
        f.addLayout(g)
        return s

    def _on_transform(self):
        cwt = self.transform.currentData() == "cwt"
        self.stft_box.setVisible(not cwt)
        self.cwt_box.setVisible(cwt)
        if cwt and self.length.value() > 60:  # dalgacık dönüşümü ağır: bölümü kısalt
            self.length.setValue(60)

    def params(self):
        n_fft = self.n_fft.currentData()
        return {
            "start": self.start.value(), "length": self.length.value(),
            "transform": self.transform.currentData(), "window": self.window.currentData(),
            "n_fft": n_fft, "hop": max(1, int(n_fft * (1 - self.overlap.currentData()))),
            "wavelet": self.wavelet.currentData(), "scales": self.scales.value(),
            "axis": self.axis.currentData(), "range": self.range.currentData(), "cmap": self.cmap.currentData(),
            "denoise": self.strength.value() / 100 if self.denoise.isChecked() else 0.0,
            "boost": float(self.gain.value()) if self.boost.isChecked() else 0.0,
            "trim": -float(self.thresh.value()) if self.trim.isChecked() else None,
        }

    def noise_profile(self, p):
        """Gürültü profili kaydın tamamından (örneklenmiş) bir kez hesaplanır ve saklanır.

        İşleme her zaman konuşmaya uygun sabit STFT ile yapılır (dsp.process varsayılanları:
        1024 / 256 / Hann); görüntüleme ayarları yalnızca spektrogramın çizimini etkiler.
        """
        if not p["denoise"]:
            return None
        if "proc" not in self._profiles:
            a = self.audio
            sample = a if len(a) <= SR * 120 else np.concatenate(
                [a[i: i + SR * 10] for i in np.linspace(0, len(a) - SR * 10, 12).astype(int)])
            self._profiles["proc"] = dsp.noise_profile(np.abs(dsp.stft(sample)))
        return self._profiles["proc"]

    # --- hesaplama -----------------------------------------------------
    def compute(self):
        if self.worker is not None:
            return
        self.compute_btn.setEnabled(False)
        self.compute_btn.setText(tr("an_computing"))
        self._p = self.params()
        self.worker = ComputeWorker(self, self._p)
        self.worker.done.connect(self._on_done)
        self.worker.failed.connect(lambda m: self.info.setText(tr("error") + "  " + m))
        self.worker.finished.connect(self._on_worker_end)
        self.worker.start()

    def _on_worker_end(self):
        self.worker = None
        self.compute_btn.setEnabled(True)
        self.compute_btn.setText(tr("an_compute"))

    def _on_done(self, out):
        self.result = out
        p = self._p
        lut = dsp.colormap(p["cmap"])
        vmin, vmax = -p["range"], 0
        self.v_before.set_data(dsp.to_rgb(out["before"], vmin, vmax, lut), out["before"], out["t0"], out["t1"],
                               out["freqs"], tr("an_before"), vmin, vmax, lut)
        if "after_db" in out:
            self.v_after.set_data(dsp.to_rgb(out["after_db"], vmin, vmax, lut), out["after_db"], out["t0"],
                                  out["t1_after"], out["freqs"], tr("an_after"), vmin, vmax, lut)
        else:
            self.v_after.clear(tr("an_after") + "  —  " + tr("an_no_proc"))
        if "diff" in out:
            dl = dsp.colormap("diverge")
            lim = 30
            self.v_diff.set_data(dsp.to_rgb(out["diff"], -lim, lim, dl), out["diff"], out["t0"], out["t1"],
                                 out["freqs"], tr("an_diff"), -lim, lim, dl, unit="ΔdB")
            self.v_diff.show()
        else:
            self.v_diff.clear(tr("an_diff"))
            self.v_diff.setVisible(out["after"] is None)
        parts = [tr("an_ms", ms=out["ms"]),
                 f"{fmt_time(out['t0'])}–{fmt_time(out['t1'])}"]
        if "nr_db" in out:
            parts.append(tr("an_nr", db=f"{out['nr_db']:.1f}"))
        if out["removed"]:
            parts.append(tr("an_removed", s=f"{out['removed']:.1f}"))
        self.info.setText("   ·   ".join(parts))
        # dinlemek için geçici dosyalar (yeniden sentezlenmiş ses dahil)
        self.player.stop()
        self.player.setSource(QUrl())
        write_wav(self.tmp / "orig.wav", out["seg"])
        if out["after"] is not None:
            write_wav(self.tmp / "proc.wav", out["after"])
        self._set_enabled_outputs(out["after"] is not None)

    def _set_enabled_outputs(self, has_proc):
        self.play_proc.setEnabled(has_proc)
        self.export_btn.setEnabled(has_proc)
        self.add_btn.setEnabled(has_proc)

    # --- dinleme / dışa aktarma ------------------------------------------
    def _play(self, which):
        if self._playing == which and self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
            return
        if self._playing != which:
            self.player.setSource(QUrl.fromLocalFile(str(self.tmp / f"{which}.wav")))
            self._playing = which
        self.player.play()

    def _render_play(self):
        playing = self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
        for b, which, key in ((self.play_orig, "orig", "an_play_orig"), (self.play_proc, "proc", "an_play_proc")):
            b.setText(("❚❚  " if playing and self._playing == which else "▶  ") + tr(key))

    def export(self, to_list):
        if self.exporter is not None:
            return
        name = f"{self.item.title} {tr('an_processed_suffix')}.wav"
        if to_list:
            d = user_data_dir() / "processed"
            d.mkdir(parents=True, exist_ok=True)
            dest = d / name
        else:
            path, _ = QFileDialog.getSaveFileName(self, tr("an_export"), str(Path.home() / name), "WAV (*.wav)")
            if not path:
                return
            dest = Path(path)
        self.exporter = ExportWorker(self, self._p, dest)
        self.exporter.progress.connect(lambda x: self.info.setText(tr("an_exporting", p=int(x * 100))))
        self.exporter.done.connect(lambda p: (self.info.setText(tr("saved_in", path=p)),
                                              to_list and self.add_to_list.emit(p)))
        self.exporter.failed.connect(lambda m: self.info.setText(tr("error") + "  " + m))
        self.exporter.finished.connect(lambda: setattr(self, "exporter", None))
        self.info.setText(tr("an_exporting", p=0))
        self.exporter.start()

    def closeEvent(self, e):
        self.player.stop()
        for w in (self.worker, self.exporter):
            if w is not None:
                w.wait(10000)
        e.accept()
