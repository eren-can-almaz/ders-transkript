"""Sinyal analizi penceresi (gelişmiş mod): spektrogram (STFT / dalgacık), gürültü ayıklama,
konuşma yükseltme, sessizlik çıkarma; önce / sonra / fark görünümü ve yeniden sentezlenmiş sesi dinleme.
"""
import math
import tempfile
import time
import wave
from pathlib import Path

import numpy as np
from PyQt6.QtCore import QPointF, QRectF, QSize, Qt, QThread, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QImage, QPainter, QPen, QPolygonF
from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel,
    QPushButton, QScrollArea, QSlider, QSpinBox, QSplitter, QVBoxLayout, QWidget,
)

import dsp
from core import SR, decode_audio, decode_range, fmt_time, release_memory, user_data_dir
from i18n import tr
from theme import colors, glyph

ROWS, COLS = 360, 1400  # spektrogram görüntü çözünürlüğü
CWT_MAX_SEC = 60        # dalgacık dönüşümü ağır: bölüm üst sınırı
_RUNNING = set()        # pencere kapansa da bitene kadar yaşayan işler (QThread çalışırken yok edilirse Qt çöker)


def _keep_alive(worker):
    _RUNNING.add(worker)
    worker.finished.connect(lambda: _RUNNING.discard(worker))


def write_wav(path, y, sr=SR):
    pcm = (np.clip(y, -1, 1) * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())


class SpectrogramView(QWidget):
    """Eksenli spektrogram: zaman (s) × frekans (Hz), renk çubuğu, fare ile okuma,
    oynatma imleci; tıklanınca o andan çalmak için `clicked(saniye)`."""
    L, R, T, B = 62, 64, 24, 30
    clicked = pyqtSignal(float)

    def __init__(self):
        super().__init__()
        self.setMinimumHeight(190)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.img = None
        self.title = ""
        self.hover = None
        self.playhead = None  # sn (eksen zamanı) ya da None

    def set_playhead(self, t):
        self.playhead = t
        self.update()

    def set_data(self, rgb, db, t0, t1, freqs, title, vmin, vmax, lut, unit="dB"):
        h, w, _ = rgb.shape
        self._rgb = rgb  # QImage belleği paylaşır: dizi canlı kalmalı
        self.img = QImage(rgb.data, w, h, 3 * w, QImage.Format.Format_RGB888)
        self.db, self.t0, self.t1, self.freqs = db, t0, t1, freqs
        self.title, self.vmin, self.vmax, self.lut, self.unit = title, vmin, vmax, lut, unit
        self.update()

    def clear(self, title=""):
        self.img = self._rgb = self.db = None
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
        # oynatma imleci
        if self.playhead is not None and self.t0 <= self.playhead <= self.t1:
            x = r.left() + (self.playhead - self.t0) / span * r.width()
            p.setPen(QPen(QColor(c["red"]), 2))
            p.drawLine(QPointF(x, r.top()), QPointF(x, r.bottom()))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(c["red"]))
            p.drawPolygon(QPolygonF([QPointF(x - 5, r.top() - 6), QPointF(x + 5, r.top() - 6), QPointF(x, r.top())]))
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

    def mousePressEvent(self, e):
        r = self._plot()
        if self.img is not None and r.contains(e.position()):
            self.clicked.emit(self.t0 + (e.position().x() - r.left()) / r.width() * (self.t1 - self.t0))


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
            seg = decode_range(str(w.path), p["start"], p["length"])  # tüm kayıt değil, yalnız bölüm
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
            audio = decode_audio(str(w.path))  # yalnız bu iş süresince bellekte
            y, _ = dsp.process(audio, SR, denoise=p["denoise"], boost_db=p["boost"], trim=p["trim"],
                               profile=w.noise_profile(p), progress=self.progress.emit)
            del audio
            if self.dest.suffix.lower() == ".m4a":  # listeye eklenen: sıkıştırılmış (≈ 15 MB/saat)
                from core import RecordingWriter
                rw = RecordingWriter(self.dest.with_suffix(""))
                for i in range(0, len(y), SR * 10):
                    rw.write(y[i:i + SR * 10])
                rw.close()
                self.dest = rw.path
            else:
                write_wav(self.dest, y)
            del y
            release_memory()
            self.done.emit(str(self.dest))
        except Exception as e:
            self.failed.emit(f"{type(e).__name__}: {e}")


class AnalysisWindow(QWidget):
    """Gelişmiş: bir öğenin sesi için spektrogram ve işleme ekranı."""

    def __init__(self, item, parent=None, start=None, end=None, on_added=None):
        super().__init__(parent, Qt.WindowType.Window)
        self.on_added = on_added  # işlenmiş ses listeye eklenince (pencere kapansa da çağrılır)
        self.setObjectName("content")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.item = item
        self.path = item.audio
        self.audio = None
        self._profiles = {}
        self.worker = None
        self.exporter = None
        self.result = None
        self._closed = False
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
        if isinstance(start, (int, float)) and not isinstance(start, bool) \
                and isinstance(end, (int, float)) and end > start:  # dalgada seçilen aralıkla aç
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
        self._build_clone_section(f, section)
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
        self.v_clone = SpectrogramView()
        self.play_btns, self.play_times = {}, {}
        for v, which in ((self.v_before, "orig"), (self.v_after, "proc"), (self.v_diff, None),
                         (self.v_clone, "clone")):
            panel = QWidget()
            pl = QHBoxLayout(panel)
            pl.setContentsMargins(0, 0, 0, 0)
            pl.setSpacing(6)
            col_w = QWidget()
            col_w.setFixedWidth(56)  # üç panel hizalı kalsın
            col = QVBoxLayout(col_w)
            col.setContentsMargins(0, 0, 0, 0)
            col.setSpacing(4)
            col.addSpacing(SpectrogramView.T)
            if which:  # her spektrogramın yanında kendi oynat / duraklat düğmesi
                b = QPushButton(objectName="play")
                b.setIconSize(QSize(20, 20))
                b.setCursor(Qt.CursorShape.PointingHandCursor)
                b.clicked.connect(lambda _=False, w=which: self._play(w))
                tl = QLabel("00:00", objectName="faint")
                tl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                col.addWidget(b, alignment=Qt.AlignmentFlag.AlignHCenter)
                col.addWidget(tl)
                self.play_btns[which], self.play_times[which] = b, tl
                v.clicked.connect(lambda t, w=which: self._play_at(w, t))
            else:
                v.clicked.connect(lambda t: self._play_at("orig", t))
            col.addStretch()
            pl.addWidget(col_w)
            pl.addWidget(v, 1)
            split.addWidget(panel)
            if which == "clone":
                self.clone_panel = panel
                panel.hide()
        rl.addWidget(split, 1)
        play = QHBoxLayout()
        play.setSpacing(8)
        self.export_btn = QPushButton(tr("an_export"))
        self.add_btn = QPushButton(tr("an_to_list"), objectName="primary")
        self.export_btn.clicked.connect(lambda: self.export(to_list=False))
        self.add_btn.clicked.connect(lambda: self.export(to_list=True))
        self.vc_save_btn = QPushButton(tr("vc_save"))
        self.vc_add_btn = QPushButton(tr("vc_to_list"), objectName="tinted")
        self.vc_save_btn.clicked.connect(lambda: self.export_clone(to_list=False))
        self.vc_add_btn.clicked.connect(lambda: self.export_clone(to_list=True))
        for b in (self.vc_save_btn, self.vc_add_btn):
            b.hide()
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
        self._pending_seek = None
        self.player.mediaStatusChanged.connect(self._on_media_status)
        self.head_timer = QTimer(self)  # imleç akıcı ilerlesin (~30 kare/sn)
        self.head_timer.timeout.connect(self._update_heads)
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
        self.length.setMaximum(CWT_MAX_SEC if cwt else 300)  # dalgacık dönüşümü ağır: bölüm sınırlı

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
            dur = self.item.duration or 0
            if dur <= 120:
                sample = decode_range(str(self.path), 0, dur or 120)
            else:  # tüm dosyayı çözmeden: kaydın 12 farklı yerinden 10'ar saniye
                sample = np.concatenate([decode_range(str(self.path), t, 10)
                                         for t in np.linspace(0, dur - 10, 12)])
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
        _keep_alive(self.worker)
        self.worker.done.connect(self._on_done)
        self.worker.failed.connect(lambda m: self.info.setText(tr("error") + "  " + m))
        self.worker.finished.connect(self._on_worker_end)
        self.worker.start()

    def _on_worker_end(self):
        self.worker = None
        self.compute_btn.setEnabled(True)
        self.compute_btn.setText(tr("an_compute"))

    def _on_done(self, out):
        if self._closed:  # pencere hesap sürerken kapatıldı: geç gelen sonucu yok say
            return
        self.result = None  # önceki analizin dizileri yenisi gelmeden bırakılsın
        release_memory()
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
        if out.get("nr_db", 0) >= 0.5:  # temiz kayıtta ölçülebilir bir azalma yoksa gösterme
            parts.append(tr("an_nr", db=f"{out['nr_db']:.1f}"))
        if out["removed"]:
            parts.append(tr("an_removed", s=f"{out['removed']:.1f}"))
        self.info.setText("   ·   ".join(parts))
        # dinlemek için geçici dosyalar (yeniden sentezlenmiş ses dahil)
        self.player.stop()
        self.player.setSource(QUrl())
        self._playing = None
        for v in (self.v_before, self.v_after, self.v_diff):
            v.set_playhead(None)
        for tl in self.play_times.values():
            tl.setText("00:00")
        write_wav(self.tmp / "orig.wav", out["seg"])
        if out["after"] is not None:
            write_wav(self.tmp / "proc.wav", out["after"])
        self._set_enabled_outputs(out["after"] is not None)

    def _set_enabled_outputs(self, has_proc):
        self.play_btns["proc"].setEnabled(has_proc)
        self.export_btn.setEnabled(has_proc)
        self.add_btn.setEnabled(has_proc)

    # --- dinleme / dışa aktarma ------------------------------------------
    def _play(self, which):
        if self._playing == which and self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
            return
        if self._playing != which:
            self._load(which)
        self.player.play()

    def _load(self, which):
        self.player.stop()
        self.player.setSource(QUrl.fromLocalFile(str(self.tmp / f"{which}.wav")))
        self._playing = which

    def _play_at(self, which, t):
        """Spektrograma tıklanınca: o andan çal."""
        if which == "clone":
            if self.clone is None:
                return
        elif self.result is None or (which == "proc" and self.result.get("after") is None):
            return
        pos = int(max(0.0, t - self._offset(which)) * 1000)
        if self._playing != which:
            self._load(which)
            self._pending_seek = pos  # kaynak yüklenince konumlan
        else:
            self.player.setPosition(pos)
        self.player.play()

    def _on_media_status(self, status):
        if self._pending_seek is not None and status in (QMediaPlayer.MediaStatus.LoadedMedia,
                                                          QMediaPlayer.MediaStatus.BufferedMedia):
            self.player.setPosition(self._pending_seek)
            self._pending_seek = None

    def _offset(self, which):
        """Panelin zaman ekseninin başlangıcı (klon 0'dan, diğerleri bölüm başından)."""
        return 0.0 if which == "clone" else (self.result["t0"] if self.result else 0.0)

    def _update_heads(self):
        w = self._playing
        t = self._offset(w) + self.player.position() / 1000 if w else None
        self.v_before.set_playhead(t if w == "orig" else None)
        self.v_diff.set_playhead(t if w == "orig" else None)
        self.v_after.set_playhead(t if w == "proc" else None)
        self.v_clone.set_playhead(t if w == "clone" else None)
        if self._playing in self.play_times:
            self.play_times[self._playing].setText(fmt_time(self.player.position() / 1000))

    def _render_play(self):
        playing = self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
        c = colors()
        for which, b in self.play_btns.items():
            active = playing and self._playing == which
            b.setIcon(glyph("pause" if active else "play", "#ffffff"))
            b.setToolTip(tr("pause_tip" if active else "an_play_" + which))
        if playing:
            self.head_timer.start(33)
        else:
            self.head_timer.stop()
            self._update_heads()

    def export(self, to_list):
        if self.exporter is not None:
            return
        name = f"{self.item.title} {tr('an_processed_suffix')}.wav"
        if to_list:
            d = user_data_dir() / "processed"
            d.mkdir(parents=True, exist_ok=True)
            dest = d / (Path(name).stem + ".m4a")
        else:
            path, _ = QFileDialog.getSaveFileName(self, tr("an_export"), str(Path.home() / name), "WAV (*.wav)")
            if not path:
                return
            dest = Path(path)
        self.exporter = ExportWorker(self, self._p, dest)
        _keep_alive(self.exporter)
        self._ui_progress = lambda x: self.info.setText(tr("an_exporting", p=int(x * 100)))
        self._ui_done = lambda p: self.info.setText(tr("saved_in", path=p))
        self._ui_failed = lambda m: self.info.setText(tr("error") + "  " + m)
        self.exporter.progress.connect(self._ui_progress)
        self.exporter.done.connect(self._ui_done)
        self.exporter.failed.connect(self._ui_failed)
        if to_list and self.on_added:  # pencere kapatılsa da listeye eklensin
            self.exporter.done.connect(self.on_added)
        self.exporter.finished.connect(lambda: setattr(self, "exporter", None))
        self.info.setText(tr("an_exporting", p=0))
        self.exporter.start()

    # ================================================================ ses klonlama (eklenti)
    def _build_clone_section(self, f, section):
        import voiceclone
        self.clone = None
        self.vc_worker = self.vc_tr_worker = self.vc_dl = None
        section("vc_title")
        desc = QLabel(tr("vc_desc"), objectName="faint")
        desc.setWordWrap(True)
        f.addWidget(desc)
        consent = QLabel("⚠  " + tr("vc_consent"), objectName="warn")
        consent.setWordWrap(True)
        f.addWidget(consent)
        # kurulu değilse: indir
        self.vc_install = QPushButton(tr("vc_install"), objectName="tinted")
        self.vc_install.clicked.connect(self._download_plugin)
        f.addWidget(self.vc_install)
        # kuruluysa: metin, dil, üret
        self.vc_box = QWidget()
        vb = QVBoxLayout(self.vc_box)
        vb.setContentsMargins(0, 0, 0, 0)
        vb.setSpacing(8)
        from PyQt6.QtWidgets import QPlainTextEdit
        self.vc_text = QPlainTextEdit()
        self.vc_text.setPlaceholderText(tr("vc_text_ph"))
        self.vc_text.setFixedHeight(110)
        self._vc_prog_set = False   # metin programla mı değişti
        self._vc_user_edited = False
        self.vc_text.textChanged.connect(
            lambda: None if self._vc_prog_set else setattr(self, "_vc_user_edited", True))
        self.vc_text.setStyleSheet("QPlainTextEdit { background: palette(alternate-base); border-radius: 8px; padding: 6px; }")
        vb.addWidget(self.vc_text)
        row = QHBoxLayout()
        self.vc_get = QPushButton(tr("vc_get_text"), objectName="plain")
        self.vc_get.clicked.connect(lambda: self._fill_from_segment(force=True))
        self.vc_lang = QComboBox()
        for code in ("tr", "en", "de", "fr", "es", "it", "pt", "nl", "pl", "ru", "ar", "el", "sv", "no",
                     "da", "fi", "he", "hi", "ja", "ko", "ms", "sw", "zh"):
            self.vc_lang.addItem(code.upper(), code)
        self.vc_lang.setFixedWidth(84)
        row.addWidget(self.vc_get)
        row.addStretch()
        row.addWidget(QLabel(tr("vc_lang"), objectName="muted"))
        row.addWidget(self.vc_lang)
        vb.addLayout(row)
        self.vc_btn = QPushButton(tr("vc_generate"), objectName="primary")
        self.vc_btn.clicked.connect(self._generate_clone)
        vb.addWidget(self.vc_btn)
        f.addWidget(self.vc_box)
        self.vc_status = QLabel(objectName="faint")
        self.vc_status.setWordWrap(True)
        f.addWidget(self.vc_status)
        self._refresh_clone_section()
        if voiceclone.installed():
            self._prefill_clone()

    def _refresh_clone_section(self):
        import voiceclone
        ok = voiceclone.installed()
        self.vc_install.setVisible(not ok and self.vc_dl is None)
        self.vc_box.setVisible(ok)

    def _download_plugin(self):
        import voiceclone
        self.vc_dl = d = voiceclone.Downloader()
        _keep_alive(d)
        d.progress.connect(lambda x: self.vc_status.setText(tr("vc_downloading", p=int(x * 100))))
        d.done.connect(lambda: (self.vc_status.setText(""), self._refresh_clone_section(), self._prefill_clone()))
        d.failed.connect(lambda m: self.vc_status.setText(tr("error") + "  " + m))
        d.finished.connect(lambda: (setattr(self, "vc_dl", None), self._refresh_clone_section()))
        self.vc_install.hide()
        self.vc_status.setText(tr("vc_downloading", p=0))
        d.start()

    def _set_vc_text(self, text):
        self._vc_prog_set = True
        self.vc_text.setPlainText(text)
        self._vc_prog_set = False

    def _prefill_clone(self):
        """Varsayılan: kaydın zaten yazıya dökülmüş metni (bölüm kaydın tamamıysa) ve algılanan dil.
        Bölüm kaydın bir parçasıysa o parça arka planda yazıya dökülür. Kullanıcı değiştirebilir."""
        p = self.params()
        dur = self.item.duration or 0
        whole = p["start"] <= 0.5 and p["start"] + p["length"] >= dur - 0.5
        if whole and self.item.text.strip() and not self._vc_user_edited:
            self._set_vc_text(self.item.text.strip())
            self._fill_from_segment(force=False, text_too=False)  # yalnızca dili algıla
        else:
            self._fill_from_segment(force=False)

    def _fill_from_segment(self, force, text_too=True):
        """Bölümü (Standart model) yazıya dök: dili seç, metni kutuya koy (force değilse kullanıcının
        yazdığına dokunma). Dil otomatik algılanır."""
        from core import FileWorker, MODES
        if self.vc_tr_worker is not None:
            return
        p = self.params()
        w = self.vc_tr_worker = FileWorker(str(self.path), "small", None, False, MODES[1][1],
                                           clip=(p["start"], p["start"] + p["length"]))
        _keep_alive(w)
        pieces = []
        w.segment.connect(pieces.append)

        def on_info(key, value):
            if key == "detected_lang":
                i = self.vc_lang.findData(value)
                if i >= 0:
                    self.vc_lang.setCurrentIndex(i)

        def on_done(_elapsed):
            if text_too and (force or not self._vc_user_edited):
                self._set_vc_text("".join(pieces).strip())
                if force:
                    self._vc_user_edited = False
        w.info.connect(on_info)
        w.finished_ok.connect(on_done)
        w.failed.connect(lambda m: self.vc_status.setText(tr("error") + "  " + m))
        w.finished.connect(lambda: (setattr(self, "vc_tr_worker", None), self.vc_get.setEnabled(True),
                                    self.vc_status.setText("")))
        self.vc_get.setEnabled(False)
        self.vc_status.setText(tr("vc_getting_text"))
        w.start()

    def _generate_clone(self):
        import os
        import voiceclone
        if self.vc_worker is not None:  # durdur
            self.vc_worker.cancelled = True
            return
        text = self.vc_text.toPlainText().strip()
        if not text or self.result is None:
            return
        # konuşmacı örneği: işlenmiş (gürültüsü ayıklanmış) bölüm varsa o, yoksa orijinal
        ref = self.result["after"] if self.result.get("after") is not None else self.result["seg"]
        w = self.vc_worker = voiceclone.CloneWorker(ref, text, self.vc_lang.currentData(),
                                                    max(2, (os.cpu_count() or 4) // 2))
        _keep_alive(w)
        t0 = time.time()
        msgs = {"load": lambda p: tr("vc_load"), "speaker": lambda p: tr("vc_speaker"),
                "synth": lambda p: tr("vc_synth", p=int(p * 100))}
        w.progress.connect(lambda p, k: self.vc_status.setText(msgs[k](p)))
        w.done.connect(lambda wav: self._on_clone(wav, time.time() - t0))
        w.failed.connect(lambda m: self.vc_status.setText(tr("error") + "  " + m))
        w.finished.connect(self._on_clone_end)
        self.vc_btn.setText(tr("vc_stop"))
        self.vc_btn.setObjectName("destructive")
        self.vc_btn.style().unpolish(self.vc_btn)
        self.vc_btn.style().polish(self.vc_btn)
        w.start()

    def _on_clone_end(self):
        self.vc_worker = None
        self.vc_btn.setText(tr("vc_generate"))
        self.vc_btn.setObjectName("primary")
        self.vc_btn.style().unpolish(self.vc_btn)
        self.vc_btn.style().polish(self.vc_btn)

    def _on_clone(self, wav24, took):
        if self._closed or not len(wav24):
            return
        from voiceclone import SR as VSR
        self.clone = wav24
        if self._playing == "clone":
            self.player.stop()
            self.player.setSource(QUrl())
            self._playing = None
        write_wav(self.tmp / "clone.wav", wav24, VSR)
        # spektrogram: diğer panellerle aynı ayarlarla (16 kHz'e indirerek)
        y16 = np.interp(np.linspace(0, len(wav24) - 1, int(len(wav24) * SR / VSR)), np.arange(len(wav24)),
                        wav24).astype(np.float32)
        p = self._p if hasattr(self, "_p") else self.params()
        S = dsp.stft(y16, p["n_fft"], p["hop"], p["window"])
        db = dsp.to_db(np.abs(S))
        db -= db.max()
        img, rows = dsp.remap_freq(db, np.fft.rfftfreq(p["n_fft"], 1 / SR), p["axis"],
                                   40 if p["axis"] != "linear" else 0, SR / 2, ROWS)
        img = dsp.downsample_time(img, COLS)
        lut = dsp.colormap(p["cmap"])
        vmin = -p["range"]
        self.v_clone.set_data(dsp.to_rgb(img, vmin, 0, lut), img, 0.0, len(y16) / SR, rows, tr("vc_panel"),
                              vmin, 0, lut)
        self._clone16 = y16
        self.clone_panel.show()
        self.play_times["clone"].setText("00:00")
        for b in (self.vc_save_btn, self.vc_add_btn):
            b.show()
        self.vc_status.setText(tr("vc_done", s=f"{len(wav24) / VSR:.1f}", t=fmt_time(took)))

    def export_clone(self, to_list):
        from voiceclone import SR as VSR
        if self.clone is None:
            return
        name = f"{self.item.title} {tr('vc_suffix')}"
        if to_list:
            from core import RecordingWriter
            d = user_data_dir() / "processed"
            d.mkdir(parents=True, exist_ok=True)
            rw = RecordingWriter(d / name)
            rw.write(self._clone16)
            rw.close()
            if self.on_added:
                self.on_added(str(rw.path))
            self.vc_status.setText(tr("saved_in", path=rw.path))
            return
        path, _ = QFileDialog.getSaveFileName(self, tr("vc_save"), str(Path.home() / (name + ".wav")), "WAV (*.wav)")
        if path:
            write_wav(path, self.clone, VSR)
            self.vc_status.setText(tr("saved_in", path=path))


    def closeEvent(self, e):
        import shutil
        self._closed = True
        self.player.stop()
        self.player.setSource(QUrl())
        self.head_timer.stop()
        for w in (self.vc_worker, self.vc_tr_worker, self.vc_dl):
            if w is not None:
                for sig in ("done", "failed", "progress", "segment", "finished_ok"):
                    try:
                        getattr(w, sig).disconnect()
                    except (AttributeError, TypeError):
                        pass
                if hasattr(w, "cancel"):
                    w.cancel()
                w.cancelled = True
        if self.worker is not None:  # hesap sonucu artık gösterilmeyecek
            for sig in (self.worker.done, self.worker.failed):
                try:
                    sig.disconnect()
                except TypeError:
                    pass
        if self.exporter is not None:  # yalnızca bu pencerenin ekranını güncelleyen bağlantılar kesilir
            for sig, slot in ((self.exporter.progress, self._ui_progress), (self.exporter.done, self._ui_done),
                              (self.exporter.failed, self._ui_failed)):
                try:
                    sig.disconnect(slot)
                except TypeError:
                    pass
        for w in (self.worker, self.exporter):
            if w is not None:
                w.wait(3000)  # uzun iş (ör. 86 dk dışa aktarma) arka planda biter; _RUNNING yaşatır
        self.result = None  # son analizin dizileri (bölüm, spektrogramlar) bırakılsın
        self.clone = None
        for v in (self.v_before, self.v_after, self.v_diff, self.v_clone):
            v.clear()
        shutil.rmtree(self.tmp, ignore_errors=True)
        import voiceclone
        voiceclone.release_model()  # klonlama süreci biter, bellek tamamen geri verilir
        release_memory()
        e.accept()
