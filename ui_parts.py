"""Arayüz parçaları: ses dalgası, kayıt düğmesi, oynatıcı, transkript kutusu, seçenekler, liste satırı."""
import math
from collections import deque
from pathlib import Path

import numpy as np
from PyQt6.QtCore import QPointF, QRectF, QSize, Qt, QThread, QTimer, QUrl, QVariantAnimation, pyqtSignal
from PyQt6.QtGui import QColor, QGuiApplication, QPainter, QPalette, QTextCharFormat
from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
from PyQt6.QtWidgets import (
    QAbstractButton, QCheckBox, QComboBox, QFileDialog, QFrame, QHBoxLayout, QLabel,
    QPlainTextEdit, QPushButton, QSlider, QVBoxLayout, QWidget,
)

from core import LANGUAGES, MODES, QUALITY, QUALITY_DEFAULT, fmt_time
from i18n import fmt_date, tr
from theme import colors, glyph


def repolish(w):
    w.style().unpolish(w)
    w.style().polish(w)


class Waveform(QWidget):
    """Kayıt sırasında akan ses dalgası (sağdan sola). Seviyeler 0..1."""
    BAR, GAP = 3, 3

    def __init__(self):
        super().__init__()
        self.setFixedHeight(110)
        self.levels = deque(maxlen=400)
        self.active = False

    def add(self, level):
        self.levels.append(max(0.0, min(1.0, level)))
        self.update()

    def clear(self):
        self.levels.clear()
        self.update()

    def set_active(self, on):
        self.active = on
        self.update()

    def paintEvent(self, e):
        c = colors()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        mid = h / 2
        p.setPen(QColor(c["sep"]))
        p.drawLine(0, int(mid), w, int(mid))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(c["red"] if self.active else c["faint"]))
        step = self.BAR + self.GAP
        x = w - step
        for lv in reversed(self.levels):
            if x < 0:
                break
            bh = max(3.0, lv * (h - 10))
            p.drawRoundedRect(QRectF(x, mid - bh / 2, self.BAR, bh), 1.5, 1.5)
            x -= step


class RecordButton(QAbstractButton):
    """Apple tarzı kayıt düğmesi: halka içinde kırmızı daire; kayıtta yuvarlak kareye dönüşür."""

    def __init__(self):
        super().__init__()
        self.setFixedSize(84, 84)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._t = 0.0  # 0 = daire, 1 = kare
        self._anim = QVariantAnimation(self, duration=220)
        self._anim.valueChanged.connect(self._set_t)

    def _set_t(self, v):
        self._t = float(v)
        self.update()

    def set_recording(self, on):
        self._anim.stop()
        self._anim.setStartValue(self._t)
        self._anim.setEndValue(1.0 if on else 0.0)
        self._anim.start()

    def paintEvent(self, e):
        c = colors()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        ring = QColor(c["ring"])
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(ring)
        p.drawEllipse(QRectF(0, 0, 84, 84))
        p.setBrush(QColor(c["bg"]))
        p.drawEllipse(QRectF(5, 5, 74, 74))
        red = QColor(c["red"] if self.isEnabled() else c["disabled"])
        if self.isDown():
            red = red.darker(115)
        elif self.underMouse():
            red = red.lighter(108)
        p.setBrush(red)
        size = 62 - 30 * self._t         # 62 → 32
        radius = size / 2 - (size / 2 - 7) * self._t
        off = (84 - size) / 2
        p.drawRoundedRect(QRectF(off, off, size, size), radius, radius)

    def enterEvent(self, e):
        self.update()

    def leaveEvent(self, e):
        self.update()


class PlayerBar(QWidget):
    """▶ düğmesi + konum çubuğu + süre. Aynı anda yalnızca bir oynatıcı çalar."""
    _all = []

    def __init__(self):
        super().__init__()
        PlayerBar._all.append(self)
        self.path = None
        self._duration = None
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)
        self.btn = QPushButton(objectName="play")
        self.btn.setIconSize(QSize(22, 22))
        self.btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn.clicked.connect(self.toggle)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, 0)
        self.slider.sliderMoved.connect(lambda v: self.player.setPosition(v))
        self.time = QLabel("00:00", objectName="faint")
        lay.addWidget(self.btn)
        lay.addWidget(self.slider, 1)
        lay.addWidget(self.time)
        self.player = QMediaPlayer(self)
        self.out = QAudioOutput(self)
        self.player.setAudioOutput(self.out)
        self.player.durationChanged.connect(lambda d: (self.slider.setRange(0, d), self._time()))
        self.player.positionChanged.connect(self._pos)
        self.player.playbackStateChanged.connect(lambda *_: self.refresh_icons())
        self.refresh_icons()

    def set_source(self, path, duration=None):
        self.player.stop()
        self.player.setSource(QUrl())
        self.path = path
        self._duration = duration
        self.slider.setRange(0, int((duration or 0) * 1000))
        self.slider.setValue(0)
        self._time()

    def toggle(self):
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
            return
        for other in PlayerBar._all:
            if other is not self:
                other.pause()
        if self.player.source().isEmpty() and self.path:
            self.player.setSource(QUrl.fromLocalFile(str(self.path)))
        self.player.play()

    def seek_to(self, sec):
        if self.player.source().isEmpty() and self.path:
            self.player.setSource(QUrl.fromLocalFile(str(self.path)))
        self.player.setPosition(int(sec * 1000))

    def play_from(self, sec):
        for other in PlayerBar._all:
            if other is not self:
                other.pause()
        self.seek_to(sec)
        self.player.play()

    def pause(self):
        try:
            if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
                self.player.pause()
        except RuntimeError:  # pencere kapanmış
            pass

    def release(self):
        """Dosya taşınacak/silinecekse önce bırak."""
        self.player.stop()
        self.player.setSource(QUrl())

    def _pos(self, ms):
        if not self.slider.isSliderDown():
            self.slider.setValue(ms)
        self._time()

    def _time(self):
        d = self.player.duration()
        total = d / 1000 if d > 0 else (self._duration or 0)
        self.time.setText(f"{fmt_time(self.player.position() / 1000)} / {fmt_time(total)}")

    def refresh_icons(self):
        playing = self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
        self.btn.setIcon(glyph("pause" if playing else "play", "#ffffff"))
        self.btn.setToolTip(tr("pause_tip" if playing else "play_tip"))


class TranscriptBox(QFrame):
    """Transkript alanı: başlık, kelime sayısı, Kopyala / Metni kaydet ve metin (gri taslak desteğiyle)."""
    edited = pyqtSignal()  # kullanıcı metni değiştirdi (kaydetmek için)

    def __init__(self):
        super().__init__(objectName="box")
        self.default_path = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(10)
        bar = QHBoxLayout()
        self.title = QLabel(objectName="sectionTitle")
        self.words = QLabel(objectName="faint")
        self.save_btn = QPushButton(objectName="plain")
        self.save_btn.clicked.connect(self.save)
        self.copy_btn = QPushButton(objectName="tinted")
        self.copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.copy_btn.clicked.connect(self.copy)
        bar.addWidget(self.title)
        bar.addSpacing(8)
        bar.addWidget(self.words)
        bar.addStretch()
        bar.addWidget(self.save_btn)
        bar.addWidget(self.copy_btn)
        lay.addLayout(bar)
        self.text = QPlainTextEdit()
        self.text.setMinimumHeight(180)
        self.text.textChanged.connect(self._changed)
        lay.addWidget(self.text, 1)
        self.placeholder_key = "placeholder_none"
        self._draft_at = None
        self._programmatic = False
        self._copied = False
        self.retranslate()

    # --- metin ----------------------------------------------------------
    def _insert_end(self, text, fmt):
        sb = self.text.verticalScrollBar()
        at_bottom = sb.value() >= sb.maximum() - 4  # kullanıcı yukarı kaydırdıysa zıplatma
        cur = self.text.textCursor()
        cur.movePosition(cur.MoveOperation.End)
        cur.insertText(text, fmt)
        if at_bottom:
            sb.setValue(sb.maximum())

    def _remove_draft(self):
        if self._draft_at is None:
            return
        cur = self.text.textCursor()
        cur.setPosition(min(self._draft_at, self.text.document().characterCount() - 1))
        cur.movePosition(cur.MoveOperation.End, cur.MoveMode.KeepAnchor)
        cur.removeSelectedText()
        self._draft_at = None

    def append(self, piece):
        """Kesinleşmiş metni ekler (varsa taslağı kaldırarak)."""
        self._programmatic = True
        self._remove_draft()
        self._insert_end(piece, QTextCharFormat())
        self._programmatic = False
        self._update()

    def set_draft(self, text):
        """Henüz kesinleşmemiş metni sonda gri ve italik gösterir."""
        self._programmatic = True
        self._remove_draft()
        if text:
            committed = self.text.toPlainText()
            sep = " " if committed and not committed.endswith(("\n", " ")) else ""
            fmt = QTextCharFormat()
            fmt.setForeground(self.text.palette().color(QPalette.ColorRole.PlaceholderText))
            fmt.setFontItalic(True)
            self._draft_at = len(committed)
            self._insert_end(sep + text, fmt)
        self._programmatic = False

    def set_text(self, text):
        self._programmatic = True
        self._draft_at = None
        self.text.setPlainText(text)
        self._programmatic = False
        self._update()

    def plain(self):
        """Yalnızca kesinleşmiş metin (kopyala/kaydet bunu kullanır)."""
        txt = self.text.toPlainText()
        return txt[: self._draft_at] if self._draft_at is not None else txt

    def set_placeholder(self, key):
        self.placeholder_key = key
        self.text.setPlaceholderText(tr(key))

    def _changed(self):
        self._update()
        if not self._programmatic:
            self.edited.emit()

    def _update(self):
        txt = self.plain()
        has = bool(txt.strip())
        self.copy_btn.setEnabled(has)
        self.save_btn.setEnabled(has)
        self.words.setText(tr("words_fmt", n=len(txt.split())) if has else "")

    # --- eylemler -------------------------------------------------------
    def copy(self):
        QGuiApplication.clipboard().setText(self.plain())
        self._copied = True
        self._render_copy()
        QTimer.singleShot(1600, self._copy_reset)

    def _copy_reset(self):
        self._copied = False
        self._render_copy()

    def _render_copy(self):
        self.copy_btn.setText(("✓  " + tr("copied")) if self._copied else tr("copy"))
        self.copy_btn.setProperty("done", "true" if self._copied else "false")
        repolish(self.copy_btn)

    def save(self):
        default = self.default_path or str(Path.home() / "transkript.txt")
        path, _ = QFileDialog.getSaveFileName(self, tr("save_dialog"), default, f"{tr('filter_text')} (*.txt)")
        if path:
            Path(path).write_text(self.plain(), encoding="utf-8")

    def retranslate(self):
        self.title.setText(tr("transcript"))
        self.save_btn.setText(tr("save_txt"))
        self.text.setPlaceholderText(tr(self.placeholder_key))
        self._render_copy()
        self._update()


class Options(QWidget):
    """Yazıya dökme seçenekleri: dil, doğruluk, işlemci + zaman damgaları (tek satır, sade)."""
    changed = pyqtSignal()

    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        row = QHBoxLayout()
        row.setSpacing(16)
        self.labels = []
        self.lang, self.quality, self.mode = QComboBox(), QComboBox(), QComboBox()
        self.lang.setMaxVisibleItems(16)
        for combo in (self.lang, self.quality, self.mode):
            col = QVBoxLayout()
            col.setSpacing(4)
            lbl = QLabel(objectName="faint")
            self.labels.append(lbl)
            col.addWidget(lbl)
            col.addWidget(combo)
            row.addLayout(col)
            combo.currentIndexChanged.connect(self._on_change)
        row.addStretch()
        lay.addLayout(row)
        self.ts = QCheckBox()
        lay.addWidget(self.ts)
        self.hint = QLabel(objectName="faint")
        self.hint.setWordWrap(True)
        lay.addWidget(self.hint)
        self._filling = False
        self.retranslate()

    def _on_change(self, *_):
        if self._filling:
            return
        self._update_hint()
        self.changed.emit()

    def language(self):
        return self.lang.currentData()

    def model_name(self):
        return QUALITY[max(0, self.quality.currentIndex())][0]

    def threads(self):
        return MODES[max(0, self.mode.currentIndex())][1]

    def is_quiet(self):
        return self.mode.currentIndex() == 0

    def timestamps(self):
        return self.ts.isChecked()

    def _update_hint(self):
        q = QUALITY[max(0, self.quality.currentIndex())][1]
        m = MODES[max(0, self.mode.currentIndex())][0]
        self.hint.setText(f"{tr(q + '_desc')}  {tr(m + '_desc')}")

    def retranslate(self):
        self._filling = True
        for lbl, key in zip(self.labels, ["opt_lang", "opt_quality", "opt_speed"]):
            lbl.setText(tr(key))
        idx = [c.currentIndex() for c in (self.lang, self.quality, self.mode)]
        self.lang.clear()
        self.lang.addItem(tr("lang_auto"), None)
        for code, name in LANGUAGES:
            self.lang.addItem(name, code)
        self.quality.clear()
        for _, key in QUALITY:
            self.quality.addItem(tr(key))
        self.mode.clear()
        for key, _ in MODES:
            self.mode.addItem(tr(key))
        self.lang.setCurrentIndex(max(0, idx[0]))
        self.quality.setCurrentIndex(idx[1] if idx[1] >= 0 else QUALITY_DEFAULT)
        self.mode.setCurrentIndex(max(0, idx[2]))
        self.ts.setText(tr("timestamps"))
        self._filling = False
        self._update_hint()

    def save(self, st):
        st.setValue("opt/lang", self.lang.currentIndex())
        st.setValue("opt/quality", self.quality.currentIndex())
        st.setValue("opt/mode", self.mode.currentIndex())
        st.setValue("opt/ts", self.ts.isChecked())

    def load(self, st):
        def get(key, default, n):
            try:
                v = int(st.value(key, default))
            except (TypeError, ValueError):
                v = default
            return v if 0 <= v < n else default
        self._filling = True
        self.lang.setCurrentIndex(get("opt/lang", 0, self.lang.count()))
        self.quality.setCurrentIndex(get("opt/quality", QUALITY_DEFAULT, len(QUALITY)))
        self.mode.setCurrentIndex(get("opt/mode", 0, len(MODES)))
        self.ts.setChecked(st.value("opt/ts", False, type=bool))
        self._filling = False
        self._update_hint()


class ItemRow(QFrame):
    """Kenar çubuğunda bir öğe: başlık, tarih · süre, sağda durum."""
    clicked = pyqtSignal()

    def __init__(self, item):
        super().__init__(objectName="row")
        self.item = item
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 9, 12, 9)
        lay.setSpacing(10)
        self.icon = QLabel()
        self.icon.setFixedSize(22, 22)
        lay.addWidget(self.icon, alignment=Qt.AlignmentFlag.AlignTop)
        texts = QVBoxLayout()
        texts.setSpacing(2)
        self.title = QLabel(objectName="rowTitle")
        self.meta = QLabel(objectName="rowMeta")
        texts.addWidget(self.title)
        texts.addWidget(self.meta)
        lay.addLayout(texts, 1)
        self.badge = QLabel(objectName="rowBadge")
        lay.addWidget(self.badge, alignment=Qt.AlignmentFlag.AlignTop)
        self.status = ""      # çalışan iş: "● 03:12", "%37" vb.
        self.refresh()

    def mousePressEvent(self, e):
        self.clicked.emit()

    def set_selected(self, on):
        self.setProperty("selected", "true" if on else "false")
        repolish(self)

    def set_status(self, text, kind=""):
        self.status = text
        self._status_kind = kind
        self.refresh()

    def refresh(self):
        it = self.item
        c = colors()
        recording = getattr(self, "_status_kind", "") == "rec" and bool(self.status)
        color = c["red"] if recording or (it.kind == "rec" and it.new) else c["muted"]
        self.icon.setPixmap(glyph("mic" if it.kind == "rec" else "wave", color, 44).pixmap(22, 22))
        fm = self.title.fontMetrics()
        self.title.setText(fm.elidedText(it.title, Qt.TextElideMode.ElideRight, 170))
        meta = fmt_date(it.created)
        if it.duration:
            meta += f"  ·  {fmt_time(it.duration)}"
        self.meta.setText(meta)
        kind = getattr(self, "_status_kind", "")
        if self.status:
            text = self.status
        elif it.new:
            text, kind = tr("badge_new"), "busy"
        elif it.kind == "rec" and not it.saved:
            text, kind = "●", "unsaved"
            self.badge.setToolTip(tr("badge_unsaved"))
        else:
            text = ""
        self.badge.setText(text)
        self.badge.setProperty("kind", kind)
        repolish(self.badge)


class PeaksWorker(QThread):
    """Sesin genlik zarfı: saniyede 100 kova (min, max). Diskte önbelleğe alınır."""
    done = pyqtSignal(object)
    RATE = 100  # kova / sn

    def __init__(self, audio_path, cache_path):
        super().__init__()
        self.audio_path, self.cache_path = Path(audio_path), Path(cache_path)

    def run(self):
        import numpy as np
        from core import SR, decode_audio
        try:
            if self.cache_path.exists() and self.cache_path.stat().st_mtime >= self.audio_path.stat().st_mtime:
                self.done.emit(np.load(self.cache_path))
                return
            a = decode_audio(str(self.audio_path))
            step = SR // self.RATE
            n = len(a) // step
            b = a[: n * step].reshape(n, step)
            peaks = np.stack([b.min(axis=1), b.max(axis=1)], axis=1).astype(np.float32)
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            np.save(self.cache_path, peaks)
            self.done.emit(peaks)
        except Exception:
            self.done.emit(None)


class WaveView(QWidget):
    """Genlik dalgası (Ses Kayıtları tarzı): tıkla = git, sürükle = aralık seç, çift tık = seçimi kaldır,
    tekerlek = yakınlaştır, Shift+tekerlek = kaydır."""
    seek = pyqtSignal(float)
    selection_changed = pyqtSignal(object)  # (başlangıç, bitiş) ya da None
    BAR, GAP = 2, 1

    def __init__(self):
        super().__init__()
        self.setFixedHeight(128)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.IBeamCursor)
        self.peaks = None
        self.duration = 0.0
        self.pos_s = 0.0
        self.sel = None
        self.v0 = self.v1 = 0.0
        self._press = None
        self._hover = None

    def set_peaks(self, peaks, duration):
        self.peaks = peaks
        self.duration = duration or (len(peaks) / PeaksWorker.RATE if peaks is not None else 0)
        self.v0, self.v1 = 0.0, max(self.duration, 0.1)
        # kova başına tepe genliği; sütunlarda bunların ortalaması çizilir (uzun kayıtta da konuşma ve
        # duraklamalar ayırt edilsin — en büyük değer her sütunu doldururdu)
        self._env = np.maximum(-peaks[:, 0], peaks[:, 1]) if peaks is not None and len(peaks) else None
        self.update()

    def set_position(self, sec):
        self.pos_s = sec
        if self.v1 - self.v0 < self.duration and not (self.v0 <= sec <= self.v1):  # yakınlaştırılmışsa takip et
            w = self.v1 - self.v0
            self.v0 = min(max(0.0, sec - w * 0.1), self.duration - w)
            self.v1 = self.v0 + w
        self.update()

    def set_selection(self, sel):
        self.sel = sel
        self.update()
        self.selection_changed.emit(sel)

    # --- koordinat dönüşümü
    def _plot(self):
        return QRectF(0, 4, self.width(), self.height() - 24)

    def _t(self, x):
        return max(0.0, min(self.duration, self.v0 + x / max(self.width(), 1) * (self.v1 - self.v0)))

    def _x(self, t):
        return (t - self.v0) / max(self.v1 - self.v0, 1e-9) * self.width()

    def paintEvent(self, e):
        c = colors()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self._plot()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(c["fill"]))
        p.drawRoundedRect(r, 12, 12)
        if self.peaks is None or not len(self.peaks):
            return
        mid, half = r.center().y(), r.height() / 2 - 8
        if self.sel:  # seçili aralık arka planı
            x0, x1 = self._x(self.sel[0]), self._x(self.sel[1])
            sel_bg = QColor(c["accent"])
            sel_bg.setAlpha(40)
            p.setBrush(sel_bg)
            p.drawRect(QRectF(x0, r.top(), x1 - x0, r.height()))
        step = self.BAR + self.GAP
        n_cols = int(self.width() / step)
        rate = PeaksWorker.RATE
        base, accent = QColor(c["faint"]), QColor(c["accent"])
        played = QColor(c["muted"])
        cols = []
        for i in range(n_cols):
            t0, t1 = self._t(i * step), self._t((i + 1) * step)
            a, b = int(t0 * rate), max(int(t0 * rate) + 1, int(t1 * rate))
            seg = self._env[a:b]
            cols.append((t0, t1, float(seg.mean()) if len(seg) else 0.0))
        top = max(1e-4, float(np.percentile([v for _, _, v in cols], 98))) if cols else 1.0
        for i, (t0, t1, v) in enumerate(cols):
            amp = min(1.0, (v / top) ** 0.8)
            h = max(2.0, amp * half * 2)
            tm = (t0 + t1) / 2
            if self.sel and self.sel[0] <= tm <= self.sel[1]:
                p.setBrush(accent)
            else:
                p.setBrush(played if tm <= self.pos_s else base)
            p.drawRoundedRect(QRectF(i * step, mid - h / 2, self.BAR, h), 1, 1)
        if self.sel:  # seçim kenar tutamaçları
            p.setBrush(accent)
            for t in self.sel:
                x = self._x(t)
                p.drawRect(QRectF(x - 1, r.top(), 2, r.height()))
                p.drawEllipse(QRectF(x - 4, r.top() - 3, 8, 8))
        # oynatma imleci
        x = self._x(self.pos_s)
        if 0 <= x <= self.width():
            p.setBrush(QColor(c["red"]))
            p.drawRect(QRectF(x - 1, r.top(), 2, r.height()))
        # zaman etiketleri
        p.setPen(QColor(c["faint"]))
        span = self.v1 - self.v0
        stepl = next(s for s in (1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 900, 1800) if span / s <= 8)
        t = math.ceil(self.v0 / stepl) * stepl
        while t <= self.v1:
            xx = min(max(self._x(t), 30), self.width() - 30)  # kenardaki etiketler kesilmesin
            p.drawText(QRectF(xx - 30, r.bottom() + 3, 60, 16), Qt.AlignmentFlag.AlignHCenter, fmt_time(t))
            t += stepl
        if self._hover is not None and self._press is None:
            p.setPen(QColor(c["muted"]))
            p.drawLine(QPointF(self._hover, r.top()), QPointF(self._hover, r.bottom()))

    def mousePressEvent(self, e):
        if self.peaks is None:
            return
        self._press = e.position().x()

    def mouseMoveEvent(self, e):
        x = e.position().x()
        self._hover = x
        if self._press is not None and abs(x - self._press) > 3:
            a, b = sorted((self._t(self._press), self._t(x)))
            self.sel = (a, b)
            self.selection_changed.emit(self.sel)
        self.update()

    def mouseReleaseEvent(self, e):
        if self._press is None:
            return
        x = e.position().x()
        if abs(x - self._press) <= 3:  # tıklama: oraya git
            self.seek.emit(self._t(x))
        elif self.sel and self.sel[1] - self.sel[0] < 0.2:  # çok kısa seçim yok sayılır
            self.set_selection(None)
        self._press = None
        self.update()

    def mouseDoubleClickEvent(self, e):
        self.set_selection(None)

    def leaveEvent(self, e):
        self._hover = None
        self.update()

    def wheelEvent(self, e):
        if self.peaks is None:
            return
        dy = e.angleDelta().y() or e.angleDelta().x()
        span = self.v1 - self.v0
        if e.modifiers() & Qt.KeyboardModifier.ShiftModifier or e.angleDelta().x():
            shift = -dy / 120 * span * 0.15  # kaydır
            self.v0 = min(max(0.0, self.v0 + shift), max(0.0, self.duration - span))
            self.v1 = self.v0 + span
        else:  # imlecin olduğu yere doğru yakınlaştır / uzaklaştır
            anchor = self._t(e.position().x())
            f = 0.8 if dy > 0 else 1.25
            new = min(self.duration, max(2.0, span * f))
            frac = (anchor - self.v0) / max(span, 1e-9)
            self.v0 = min(max(0.0, anchor - frac * new), max(0.0, self.duration - new))
            self.v1 = self.v0 + new
        self.update()
