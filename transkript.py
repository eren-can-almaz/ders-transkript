"""Ders Transkript — ders kayıtlarını ve canlı konuşmayı internetsiz metne çeviren masaüstü uygulaması.

faster-whisper (CPU, int8) + PyQt6. İki bağımsız panel: ses dosyası ve canlı dinleme;
tarayıcı gibi kapatılabilir sekmelerde (+ ile yenisi açılır) ya da yan yana kullanılabilir;
aynı anda çalışabilirler.
Modüller: core (modeller, işçiler), panels (iki panel), widgets (ortak parçalar),
theme (açık/koyu tema), i18n (arayüz dilleri).
"""
import os
import sys

from PyQt6.QtCore import QSettings, QSize, Qt
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import (
    QApplication, QComboBox, QFrame, QHBoxLayout, QLabel, QMainWindow, QMenu, QMessageBox,
    QPushButton, QScrollArea, QSplitter, QStackedWidget, QVBoxLayout, QWidget,
)

import i18n
from core import MODES, QUALITY, decode_audio, lower_priority, model_path
from i18n import UI_LANGUAGES, tr
from panels import FilePanel, LivePanel
from theme import THEME_CHOICES, app_icon, apply_theme, current_colors, media_icon
from widgets import Segmented, TabChip


class Entry:
    """Açık bir pencere (sekme): türü, paneli, kaydırma alanı, sekme çipi ve durumu."""

    def __init__(self, kind, panel, area, chip):
        self.kind, self.panel, self.area, self.chip = kind, panel, area, chip
        self.status = ""

    def title(self):
        return self.panel.tab_title() if self.kind == "file" else tr("tab_live")


class EmptyState(QWidget):
    """Hiç pencere açık değilken: büyük + ve iki seçenek."""

    def __init__(self, on_new):
        super().__init__()
        outer = QVBoxLayout(self)
        outer.addStretch()
        card = QFrame(objectName="card")
        card.setFixedWidth(440)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(32, 28, 32, 28)
        lay.setSpacing(12)
        plus = QLabel("+", objectName="plus")
        plus.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(plus, alignment=Qt.AlignmentFlag.AlignHCenter)
        self.title = QLabel(objectName="emptyTitle")
        self.hint = QLabel(objectName="hint")
        for w in (self.title, self.hint):
            w.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lay.addWidget(w)
        lay.addSpacing(6)
        self.btn_file = QPushButton(objectName="choice")
        self.btn_live = QPushButton(objectName="choice")
        for b, kind in ((self.btn_file, "file"), (self.btn_live, "live")):
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setIconSize(QSize(22, 22))
            b.clicked.connect(lambda _=False, k=kind: on_new(k))
            lay.addWidget(b)
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(card)
        row.addStretch()
        outer.addLayout(row)
        outer.addStretch()

    def retranslate(self):
        self.title.setText(tr("empty_title"))
        self.hint.setText(tr("empty_hint"))
        self.btn_file.setText("   " + tr("new_file"))
        self.btn_live.setText("   " + tr("new_live"))
        self.btn_file.setIcon(app_icon())
        self.btn_live.setIcon(media_icon("record", current_colors()["live"]))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = QSettings("DersTranskript", "DersTranskript")
        i18n.set_lang(self.settings.value("ui_lang", _default_ui_lang()))
        self.setWindowIcon(app_icon())
        self.resize(940, 900)
        self.setMinimumSize(720, 640)
        self.entries = []
        self.active = None

        root = QWidget(objectName="root")
        self.setCentralWidget(root)
        lay = QVBoxLayout(root)
        lay.setContentsMargins(28, 20, 28, 20)
        lay.setSpacing(14)

        # başlık: ad + rozet + arayüz dili + tema
        head = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(2)
        self.title = QLabel(objectName="title")
        self.subtitle = QLabel(objectName="subtitle")
        titles.addWidget(self.title)
        titles.addWidget(self.subtitle)
        head.addLayout(titles)
        head.addStretch()
        right = QVBoxLayout()
        right.setSpacing(8)
        self.badge = QLabel(objectName="badge")
        right.addWidget(self.badge, alignment=Qt.AlignmentFlag.AlignRight)
        prefs = QHBoxLayout()
        prefs.setSpacing(8)
        self.ui_lang = QComboBox(objectName="small")
        for code, name in UI_LANGUAGES:
            self.ui_lang.addItem(name, code)
        self.ui_lang.setCurrentIndex(max(0, self.ui_lang.findData(i18n.get_lang())))
        self.ui_lang.currentIndexChanged.connect(self._on_ui_lang)
        self.theme = Segmented([k for k, _ in THEME_CHOICES], prop="small")
        prefs.addWidget(self.ui_lang)
        prefs.addWidget(self.theme)
        right.addLayout(prefs)
        head.addLayout(right)
        lay.addLayout(head)

        # sekmeler (kapatılabilir) + yeni pencere (+) + yan yana
        bar = QHBoxLayout()
        self.tabbar = QFrame(objectName="tabbar")
        self.tab_row = QHBoxLayout(self.tabbar)
        self.tab_row.setContentsMargins(3, 3, 3, 3)
        self.tab_row.setSpacing(2)
        self.add_btn = QPushButton("+", objectName="addTab")
        self.add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.add_btn.clicked.connect(self._show_add_menu)
        self.tab_row.addWidget(self.add_btn)
        bar.addWidget(self.tabbar)
        bar.addStretch()
        self.split_btn = QPushButton(objectName="toggle")
        self.split_btn.setCheckable(True)
        self.split_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.split_btn.toggled.connect(self._update_layout)
        bar.addWidget(self.split_btn)
        lay.addLayout(bar)

        # gövde: pencereler (sekmeli veya yan yana) ya da boş durum
        self.stack = QStackedWidget()
        self.empty = EmptyState(self.add_panel)
        self.split = QSplitter(Qt.Orientation.Horizontal)
        self.split.setChildrenCollapsible(False)
        self.split.setHandleWidth(18)
        self.stack.addWidget(self.empty)
        self.stack.addWidget(self.split)
        lay.addWidget(self.stack, 1)

        # son oturumdaki pencereler ve ayarlar
        self.theme.set_index(self._int("theme", 0, len(THEME_CHOICES)))
        self.split_btn.setChecked(self.settings.value("side_by_side", False, type=bool))
        saved = self.settings.value("open_tabs", None)
        kinds = [k for k in (saved.split(",") if isinstance(saved, str) else ["file", "live"])
                 if k in ("file", "live")]
        for k in kinds:
            if k == "file" or not self._live_entry():
                self.add_panel(k, activate=False)
        if self.entries:
            self._activate(self.entries[min(self._int("active", 0, len(self.entries)), len(self.entries) - 1)])
        self.theme.changed.connect(self._on_theme)
        try:  # "Sistem" seçiliyken işletim sistemi teması değişirse uygula
            QGuiApplication.styleHints().colorSchemeChanged.connect(lambda *_: self._on_theme())
        except AttributeError:
            pass
        self._update_layout()
        self.retranslate()

    def _int(self, key, default, n):
        try:
            v = int(self.settings.value(key, default))
        except (TypeError, ValueError):
            v = default
        return v if 0 <= v < max(n, 1) else default

    # --- pencereler -----------------------------------------------------
    def _live_entry(self):
        return next((e for e in self.entries if e.kind == "live"), None)

    def add_panel(self, kind, activate=True):
        if kind == "live" and self._live_entry():  # tek mikrofon: tek kayıt penceresi
            self._activate(self._live_entry())
            return
        panel = FilePanel() if kind == "file" else LivePanel()
        panel.load_settings(self.settings)
        area = QScrollArea()  # pencere küçükse ezilmek yerine kaydırılsın
        area.setWidgetResizable(True)
        area.setFrameShape(QScrollArea.Shape.NoFrame)
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        area.setWidget(panel)
        chip = TabChip()
        e = Entry(kind, panel, area, chip)
        chip.clicked.connect(lambda: self._activate(e))
        chip.close.connect(lambda: self.close_panel(e))
        panel.tab_status.connect(lambda s: self._set_status(e, s))
        if kind == "file":
            panel.title_changed.connect(lambda: self._render_chip(e))
        else:
            panel.transcribe_request.connect(self._transcribe_recording)
        self.entries.append(e)
        self.tab_row.insertWidget(self.tab_row.count() - 1, chip)  # "+" düğmesinden önce
        self.split.addWidget(area)
        self._render_chip(e)
        if activate or self.active is None:
            self._activate(e)
        self._update_layout()
        return e

    def close_panel(self, e):
        if e.panel.busy():
            if QMessageBox.question(self, tr("close_tip"), tr("close_busy")) != QMessageBox.StandardButton.Yes:
                return
        e.panel.stop_for_quit()
        e.panel.save_settings(self.settings)
        i = self.entries.index(e)
        self.entries.remove(e)
        for w in (e.chip, e.area):
            w.setParent(None)
            w.deleteLater()
        if self.active is e:
            self.active = None
            if self.entries:
                self._activate(self.entries[min(i, len(self.entries) - 1)])
        self._update_layout()
        self._update_title()

    def _activate(self, e):
        self.active = e
        for x in self.entries:
            x.chip.set_active(x is e)
        self._update_layout()

    def _update_layout(self, *_):
        n = len(self.entries)
        self.stack.setCurrentIndex(1 if n else 0)
        self.split_btn.setVisible(n > 1)
        side = self.split_btn.isChecked() and n > 1
        for e in self.entries:
            e.area.setVisible(side or e is self.active)
        if side and self.width() < 640 * n:
            self.resize(min(700 * n, 1900), self.height())

    def _show_add_menu(self):
        menu = QMenu(self)
        a_file = menu.addAction(app_icon(), tr("new_file"))
        a_live = menu.addAction(media_icon("record", current_colors()["live"]), tr("new_live"))
        a_live.setEnabled(self._live_entry() is None)
        chosen = menu.exec(self.add_btn.mapToGlobal(self.add_btn.rect().bottomLeft()))
        if chosen is a_file:
            self.add_panel("file")
        elif chosen is a_live:
            self.add_panel("live")

    def _transcribe_recording(self, path):
        """Kayıt listesindeki bir kaydı bir ses dosyası penceresinde yazıya dökmeye hazırla."""
        e = next((x for x in self.entries if x.kind == "file" and not x.panel.busy()
                  and not x.panel.audio_path), None) or self.add_panel("file")
        e.panel.set_file(path)
        self._activate(e)

    def _render_chip(self, e):
        e.chip.label.setText(e.title() + (f"  {e.status}" if e.status else ""))
        e.chip.close_btn.setToolTip(tr("close_tip"))

    def _set_status(self, e, text):
        e.status = text
        self._render_chip(e)
        self._update_title()

    def _update_title(self):
        """Pencere başlığı = görev çubuğunda da görünen durum özeti."""
        parts = [f"{e.title()} {e.status}" for e in self.entries if e.status]
        self.setWindowTitle(f"{tr('app_title')} — {' · '.join(parts)}" if parts else tr("app_title"))

    # --- tema / dil -----------------------------------------------------
    def _on_theme(self, *_):
        apply_theme(QApplication.instance(), THEME_CHOICES[self.theme.index][1])
        for e in self.entries:
            if e.kind == "live":
                e.panel.refresh_icons()

    def _on_ui_lang(self, *_):
        i18n.set_lang(self.ui_lang.currentData())
        self.retranslate()

    def retranslate(self):
        self._update_title()
        self.title.setText(tr("app_title"))
        self.subtitle.setText(tr("app_subtitle"))
        self.badge.setText(tr("badge_offline"))
        self.ui_lang.setToolTip(tr("ui_lang_tip"))
        self.theme.retranslate()
        self.add_btn.setToolTip(tr("add_tip"))
        self.split_btn.setText("▥  " + tr("side_by_side"))
        self.split_btn.setToolTip(tr("side_by_side_tip"))
        self.empty.retranslate()
        for e in self.entries:
            e.panel.retranslate()
            self._render_chip(e)

    def closeEvent(self, e):
        if any(x.panel.busy() for x in self.entries):
            if QMessageBox.question(self, tr("quit_title"), tr("quit_body")) \
                    != QMessageBox.StandardButton.Yes:
                e.ignore()
                return
        for x in self.entries:
            x.panel.stop_for_quit()
        live = self._live_entry()
        unsaved = live.panel.takes.unsaved() if live else []
        if unsaved:  # kaydedilmemiş kayıtlar: sakla (sonraki açılışta listede) / sil / vazgeç
            box = QMessageBox(QMessageBox.Icon.Question, tr("quit_title"),
                              tr("quit_unsaved", n=len(unsaved)), parent=self)
            keep = box.addButton(tr("quit_keep"), QMessageBox.ButtonRole.AcceptRole)
            delete = box.addButton(tr("quit_delete"), QMessageBox.ButtonRole.DestructiveRole)
            box.addButton(QMessageBox.StandardButton.Cancel)
            box.setDefaultButton(keep)
            box.exec()
            if box.clickedButton() is delete:
                live.panel.takes.delete_all_unsaved()
            elif box.clickedButton() is not keep:
                e.ignore()
                return
        st = self.settings
        st.setValue("ui_lang", i18n.get_lang())
        st.setValue("theme", self.theme.index)
        st.setValue("side_by_side", self.split_btn.isChecked())
        st.setValue("open_tabs", ",".join(x.kind for x in self.entries))
        st.setValue("active", self.entries.index(self.active) if self.active in self.entries else 0)
        for x in self.entries:
            x.panel.save_settings(st)
        e.accept()


def _default_ui_lang():
    """İlk açılışta arayüz dili Türkçe; başlıktaki seçiciden değiştirilebilir ve hatırlanır."""
    return "tr"


def selftest(audio=None):
    """Pencere açmadan uçtan uca test: model yükle, sesi çöz, metne çevir. (Derleme doğrulaması için.)"""
    import tempfile
    import wave
    import numpy as np
    from faster_whisper import WhisperModel

    if audio is None:  # ses verilmediyse 3 sn'lik bir ton üret (av ile çözülebilsin diye wav)
        audio = os.path.join(tempfile.gettempdir(), "ders_transkript_selftest.wav")
        tone = (0.2 * np.sin(2 * np.pi * 440 * np.arange(48000) / 16000) * 32767).astype(np.int16)
        with wave.open(audio, "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000); w.writeframes(tone.tobytes())
    for name, _ in QUALITY:
        path = model_path(name)
        print(f"model {name}: {path} -> {'VAR' if (path / 'model.bin').exists() else 'YOK'}", flush=True)
    model = WhisperModel(str(model_path("small")), device="cpu", compute_type="int8",
                         cpu_threads=MODES[0][1])
    data = decode_audio(audio)[: 16000 * 30]
    segs, info = model.transcribe(data, beam_size=1, vad_filter=True)
    text = " ".join(s.text.strip() for s in segs)
    print(f"ses {len(data) / 16000:.1f} sn, dil {info.language}: {text[:200]!r}", flush=True)
    _selftest_mic()
    print("SELFTEST OK", flush=True)


def _selftest_mic():
    """Mikrofon yolu: varsa 1 sn okur. Mikrofonsuz makinede (ör. derleme sunucusu) atlanır."""
    from PyQt6.QtCore import QCoreApplication, QTimer
    from PyQt6.QtMultimedia import QMediaDevices
    from panels import Microphone

    app = QCoreApplication.instance() or QCoreApplication(sys.argv)
    dev = QMediaDevices.defaultAudioInput()
    if dev.isNull():
        print("mikrofon: yok (atlandı)", flush=True)
        return
    got = []
    mic = Microphone(dev, lambda a: got.append(len(a)), None)
    QTimer.singleShot(1000, app.quit)
    app.exec()
    mic.stop()
    print(f"mikrofon: {dev.description()} -> {sum(got) / 16000:.2f} sn ses okundu", flush=True)


def main():
    if "--selftest" in sys.argv:
        if sys.stdout is None:  # pencereli exe'de konsol yok: çıktıyı dosyaya yaz
            sys.stdout = sys.stderr = open("selftest.log", "w", encoding="utf-8")
        i = sys.argv.index("--selftest")
        selftest(sys.argv[i + 1] if len(sys.argv) > i + 1 else None)
        return
    lower_priority()
    app = QApplication(sys.argv)
    app.setApplicationName("Ders Transkript")
    app.setDesktopFileName("ders-transkript")  # Linux: görev çubuğunda doğru ikon
    app.setStyle("Fusion")
    font = app.font()
    if sys.platform == "win32":
        font.setFamily("Segoe UI")  # macOS/Linux kendi sistem yazı tipini kullanır
    font.setPointSize(10 if sys.platform != "darwin" else 13)
    app.setFont(font)
    apply_theme(app, "system")
    w = MainWindow()
    w._on_theme()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
