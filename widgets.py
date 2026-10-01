"""İki panelin ortak kullandığı arayüz parçaları."""
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel,
    QPlainTextEdit, QProgressBar, QPushButton, QVBoxLayout,
)

from core import AUDIO_EXT, LANGUAGES, MODES, QUALITY, QUALITY_DEFAULT
from i18n import tr
from theme import app_icon


def repolish(w):
    w.style().unpolish(w)
    w.style().polish(w)


def make_card():
    f = QFrame(objectName="card")
    lay = QVBoxLayout(f)
    lay.setContentsMargins(18, 16, 18, 16)
    lay.setSpacing(12)
    return f, lay


class Segmented(QFrame):
    """Yan yana seçilebilen düğmeler. Etiketler i18n anahtarlarıyla verilir."""
    changed = pyqtSignal(int)

    def __init__(self, keys, default=0, prop=None):
        super().__init__(objectName="segbox")
        if prop:
            self.setProperty(prop, "true")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(3, 3, 3, 3)
        lay.setSpacing(2)
        self.keys = keys
        self.suffixes = [""] * len(keys)
        self.buttons = []
        for i in range(len(keys)):
            b = QPushButton(objectName="seg")
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _=False, i=i: self.set_index(i))
            lay.addWidget(b)
            self.buttons.append(b)
        self.index = default
        self.retranslate()
        self.set_index(default)

    def set_index(self, i):
        for j, b in enumerate(self.buttons):
            b.setChecked(i == j)
        self.index = i
        self.changed.emit(i)

    def set_suffix(self, i, text):
        """Sekme etiketine durum eki (ör. '· %37')."""
        self.suffixes[i] = text
        self.buttons[i].setText(tr(self.keys[i]) + text)

    def retranslate(self):
        for b, k, sfx in zip(self.buttons, self.keys, self.suffixes):
            b.setText(tr(k) + sfx)


class SettingsBlock(QVBoxLayout):
    """Ses dili + doğruluk + çalışma modu + açıklama satırı (her iki panelde aynı)."""

    def __init__(self):
        super().__init__()
        self.setSpacing(12)
        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(8)
        self.titles = [QLabel(objectName="section") for _ in range(3)]
        self.lang = QComboBox()
        self.lang.setMaxVisibleItems(16)
        self.quality = Segmented([k for _, k in QUALITY], default=QUALITY_DEFAULT)
        self.mode = Segmented([k for k, _ in MODES], default=0)
        grid.addWidget(self.titles[0], 0, 0)
        grid.addWidget(self.lang, 1, 0)
        grid.addWidget(self.titles[1], 0, 1)
        grid.addWidget(self.quality, 1, 1)
        grid.addWidget(self.titles[2], 2, 0, 1, 2)
        grid.addWidget(self.mode, 3, 0, 1, 2, alignment=Qt.AlignmentFlag.AlignLeft)
        grid.setColumnStretch(2, 1)
        self.addLayout(grid)
        self.hint = QLabel(objectName="hint")
        self.hint.setWordWrap(True)
        self.addWidget(self.hint)
        self.quality.changed.connect(self._update_hint)
        self.mode.changed.connect(self._update_hint)
        self.retranslate()

    def widgets(self):
        return [self.lang, self.quality, self.mode]

    def language(self):
        return self.lang.currentData()

    def model_name(self):
        return QUALITY[self.quality.index][0]

    def threads(self):
        return MODES[self.mode.index][1]

    def _update_hint(self, *_):
        q = QUALITY[self.quality.index][1]
        m = MODES[self.mode.index][0]
        self.hint.setText(f"<b>{tr(q)}:</b> {tr(q + '_desc')}<br><b>{tr(m)}:</b> {tr(m + '_desc')}")

    def retranslate(self):
        for lbl, key in zip(self.titles, ["sec_language", "sec_quality", "sec_mode"]):
            lbl.setText(tr(key))
        cur = self.lang.currentIndex()
        self.lang.blockSignals(True)
        self.lang.clear()
        self.lang.addItem(tr("lang_auto"), None)
        for code, name in LANGUAGES:
            self.lang.addItem(name, code)
        self.lang.setCurrentIndex(max(0, cur))
        self.lang.blockSignals(False)
        self.quality.retranslate()
        self.mode.retranslate()
        self._update_hint()

    # ayarları sakla / geri yükle
    def save(self, settings, prefix):
        settings.setValue(prefix + "lang", self.lang.currentIndex())
        settings.setValue(prefix + "quality", self.quality.index)
        settings.setValue(prefix + "mode", self.mode.index)

    def load(self, settings, prefix):
        def get(key, default, n):
            try:
                v = int(settings.value(prefix + key, default))
            except (TypeError, ValueError):
                v = default
            return v if 0 <= v < n else default
        self.lang.setCurrentIndex(get("lang", 0, self.lang.count()))
        self.quality.set_index(get("quality", QUALITY_DEFAULT, len(QUALITY)))
        self.mode.set_index(get("mode", 0, len(MODES)))


class DropZone(QFrame):
    fileDropped = pyqtSignal(str)

    def __init__(self):
        super().__init__(objectName="drop")
        self.setAcceptDrops(True)
        self.file_info = None  # (ad, süre, boyut)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(18, 14, 18, 14)
        lay.setSpacing(14)
        self.icon = QLabel()
        self.icon.setPixmap(app_icon().pixmap(40, 40))
        lay.addWidget(self.icon)
        texts = QVBoxLayout()
        texts.setSpacing(2)
        self.name = QLabel(objectName="fileName")
        self.info = QLabel(objectName="muted")
        self.info.setWordWrap(True)
        texts.addWidget(self.name)
        texts.addWidget(self.info)
        lay.addLayout(texts, 1)
        self.btn = QPushButton()
        self.btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn.clicked.connect(self.choose)
        lay.addWidget(self.btn)
        self.retranslate()

    def show_file(self, path, dur, size):
        self.file_info = (Path(path).name, dur, size)
        self.retranslate()

    def retranslate(self):
        if self.file_info is None:
            self.name.setText(tr("drop_title"))
            self.info.setText(tr("drop_info"))
            self.btn.setText(tr("choose_file"))
            return
        name, dur, size = self.file_info
        parts = []
        if dur:
            m, s = int(dur // 60), int(dur % 60)
            parts.append(tr("dur_min_sec", m=m, s=s) if m else tr("dur_sec", s=s))
        parts.append(f"{size / 1_048_576:.1f} MB")
        self.name.setText(name)
        self.info.setText("  ·  ".join(parts))
        self.btn.setText(tr("change"))

    def _set_hover(self, on):
        self.setProperty("hover", "true" if on else "false")
        repolish(self)

    def choose(self):
        exts = " ".join("*" + x for x in sorted(AUDIO_EXT))
        path, _ = QFileDialog.getOpenFileName(
            self, tr("file_dialog"), str(Path.home()),
            f"{tr('filter_audio')} ({exts});;{tr('filter_all')} (*)")
        if path:
            self.fileDropped.emit(path)

    def mousePressEvent(self, e):
        if self.isEnabled():
            self.choose()

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
            self._set_hover(True)

    def dragLeaveEvent(self, e):
        self._set_hover(False)

    def dropEvent(self, e):
        self._set_hover(False)
        urls = e.mimeData().urls()
        if urls:
            self.fileDropped.emit(urls[0].toLocalFile())


class StatCard(QFrame):
    """Başlık + yüzde + çubuk + küçük istatistik sütunları + not satırı."""

    def __init__(self, keys):
        super().__init__(objectName="card")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 14, 18, 14)
        lay.setSpacing(10)
        top = QHBoxLayout()
        self.step = QLabel(objectName="step")
        self.pct = QLabel(objectName="pct")
        top.addWidget(self.step)
        top.addStretch()
        top.addWidget(self.pct)
        lay.addLayout(top)
        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(8)
        lay.addWidget(self.bar)
        grid = QGridLayout()
        grid.setHorizontalSpacing(28)
        grid.setVerticalSpacing(2)
        self.keys = keys
        self.titles, self.vals = {}, {}
        for col, key in enumerate(keys):
            t = QLabel(objectName="k")
            v = QLabel("—", objectName="v")
            grid.addWidget(t, 0, col)
            grid.addWidget(v, 1, col)
            self.titles[key], self.vals[key] = t, v
        grid.setColumnStretch(len(keys), 1)
        lay.addLayout(grid)
        self.note = QLabel(objectName="hint")
        self.note.setWordWrap(True)
        lay.addWidget(self.note)
        self.retranslate()

    def set(self, key, text):
        self.vals[key].setText(text)

    def reset(self):
        for v in self.vals.values():
            v.setText("—")
        self.note.setText("")
        self.pct.setText("")
        self.step.setText("")

    def retranslate(self):
        for k, t in self.titles.items():
            t.setText(tr(k))


class TranscriptCard(QFrame):
    """Başlık, kelime sayısı, kaydet / kopyala düğmeleri ve metin alanı."""

    def __init__(self, placeholder_key, default_name):
        super().__init__(objectName="card")
        self.placeholder_key = placeholder_key
        self.default_path = None
        self.default_name = default_name
        self.on_saved = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 16, 18, 16)
        lay.setSpacing(8)
        bar = QHBoxLayout()
        self.title = QLabel(objectName="section")
        self.words = QLabel(objectName="hint")
        bar.addWidget(self.title)
        bar.addSpacing(6)
        bar.addWidget(self.words)
        bar.addStretch()
        self.save_btn = QPushButton()
        self.save_btn.clicked.connect(self.save)
        self.copy_btn = QPushButton(objectName="copy")
        self.copy_btn.setMinimumWidth(140)
        self.copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.copy_btn.clicked.connect(self.copy)
        bar.addWidget(self.save_btn)
        bar.addWidget(self.copy_btn)
        lay.addLayout(bar)
        sep = QFrame(objectName="sep")
        sep.setFixedHeight(1)
        lay.addWidget(sep)
        self.text = QPlainTextEdit()
        self.text.textChanged.connect(self._update)
        lay.addWidget(self.text, 1)
        self._copied = False
        self.retranslate()

    def append(self, piece):
        sb = self.text.verticalScrollBar()
        at_bottom = sb.value() >= sb.maximum() - 4  # kullanıcı yukarı kaydırdıysa zıplatma
        cur = self.text.textCursor()
        cur.movePosition(cur.MoveOperation.End)
        cur.insertText(piece)
        if at_bottom:
            sb.setValue(sb.maximum())

    def clear(self):
        self.text.clear()

    def plain(self):
        return self.text.toPlainText()

    def _update(self):
        txt = self.plain()
        has = bool(txt.strip())
        self.copy_btn.setEnabled(has)
        self.save_btn.setEnabled(has)
        self.words.setText(tr("words_fmt", n=len(txt.split())) if has else "")

    def copy(self):
        QGuiApplication.clipboard().setText(self.plain())
        self._copied = True
        self._render_copy()
        QTimer.singleShot(1800, self._copy_reset)

    def _copy_reset(self):
        self._copied = False
        self._render_copy()

    def _render_copy(self):
        self.copy_btn.setText(tr("copied") if self._copied else tr("copy_all"))
        self.copy_btn.setProperty("done", "true" if self._copied else "false")
        repolish(self.copy_btn)

    def save(self):
        default = self.default_path or str(Path.home() / self.default_name)
        path, _ = QFileDialog.getSaveFileName(self, tr("save_dialog"), default,
                                              f"{tr('filter_text')} (*.txt)")
        if path:
            Path(path).write_text(self.plain(), encoding="utf-8")
            if self.on_saved:
                self.on_saved(path)

    def retranslate(self):
        self.title.setText(tr("transcript"))
        self.save_btn.setText(tr("save_txt"))
        self.text.setPlaceholderText(tr(self.placeholder_key))
        self._render_copy()
        self._update()

