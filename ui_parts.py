"""Arayüz parçaları: ses dalgası, kayıt düğmesi, oynatıcı, transkript kutusu, seçenekler, liste satırı."""
from collections import deque
from pathlib import Path

from PyQt6.QtCore import QRectF, QSize, Qt, QTimer, QUrl, QVariantAnimation, pyqtSignal
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
