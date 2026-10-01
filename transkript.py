"""Ders Transkript — ders kayıtlarını ve canlı konuşmayı internetsiz metne çeviren masaüstü uygulaması.

faster-whisper (CPU, int8) + PyQt6. İki bağımsız panel: ses dosyası ve canlı dinleme;
sekmeli ya da yan yana kullanılabilir, aynı anda çalışabilir.
Modüller: core (modeller, işçiler), panels (iki panel), widgets (ortak parçalar),
theme (açık/koyu tema), i18n (arayüz dilleri).
"""
import os
import sys

from PyQt6.QtCore import QSettings, Qt
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import (
    QApplication, QComboBox, QHBoxLayout, QLabel, QMainWindow, QMessageBox, QPushButton,
    QSplitter, QVBoxLayout, QWidget,
)

import i18n
from core import MODES, QUALITY, decode_audio, lower_priority, model_path
from i18n import UI_LANGUAGES, tr
from panels import FilePanel, LivePanel
from theme import THEME_CHOICES, app_icon, apply_theme
from widgets import Segmented


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = QSettings("DersTranskript", "DersTranskript")
        i18n.set_lang(self.settings.value("ui_lang", _default_ui_lang()))
        self.setWindowIcon(app_icon())
        self.resize(940, 900)
        self.setMinimumSize(720, 640)
        self._tab_status = ["", ""]

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

        # sekmeler + yan yana
        bar = QHBoxLayout()
        self.tabs = Segmented(["tab_file", "tab_live"], prop="tabs")
        self.tabs.changed.connect(self._update_layout)
        bar.addWidget(self.tabs)
        bar.addStretch()
        self.split_btn = QPushButton(objectName="toggle")
        self.split_btn.setCheckable(True)
        self.split_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.split_btn.toggled.connect(self._update_layout)
        bar.addWidget(self.split_btn)
        lay.addLayout(bar)

        self.file = FilePanel()
        self.live = LivePanel()
        self.file.tab_status.connect(lambda s: self._set_tab_status(0, s))
        self.live.tab_status.connect(lambda s: self._set_tab_status(1, s))
        self.split = QSplitter(Qt.Orientation.Horizontal)
        self.split.setChildrenCollapsible(False)
        self.split.setHandleWidth(18)
        self.split.addWidget(self.file)
        self.split.addWidget(self.live)
        lay.addWidget(self.split, 1)

        # son kullanılan ayarlar
        self.theme.set_index(self._int("theme", 0, len(THEME_CHOICES)))
        self.tabs.set_index(self._int("tab", 0, 2))
        self.split_btn.setChecked(self.settings.value("side_by_side", False, type=bool))
        self.file.load_settings(self.settings)
        self.live.load_settings(self.settings)
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
        return v if 0 <= v < n else default

    def _update_layout(self, *_):
        side = self.split_btn.isChecked()
        self.tabs.setEnabled(not side)
        self.file.setVisible(side or self.tabs.index == 0)
        self.live.setVisible(side or self.tabs.index == 1)
        if side and self.width() < 1280:
            self.resize(1380, self.height())

    def _set_tab_status(self, i, text):
        self._tab_status[i] = text
        self.tabs.set_suffix(i, f"  {text}" if text else "")
        self._update_title()

    def _update_title(self):
        """Pencere başlığı = görev çubuğunda da görünen durum özeti: 'Ad — Ses dosyası %37 · Canlı ● 03:12'."""
        parts = [f"{tr(k)} {s}" for k, s in zip(["tab_file", "tab_live"], self._tab_status) if s]
        self.setWindowTitle(f"{tr('app_title')} — {' · '.join(parts)}" if parts else tr("app_title"))

    def _on_theme(self, *_):
        apply_theme(QApplication.instance(), THEME_CHOICES[self.theme.index][1])

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
        self.tabs.retranslate()
        self.split_btn.setText("▥  " + tr("side_by_side"))
        self.split_btn.setToolTip(tr("side_by_side_tip"))
        self.file.retranslate()
        self.live.retranslate()

    def closeEvent(self, e):
        if self.file.busy() or self.live.busy():
            if QMessageBox.question(self, tr("quit_title"), tr("quit_body")) \
                    != QMessageBox.StandardButton.Yes:
                e.ignore()
                return
        self.file.stop_for_quit()
        self.live.stop_for_quit()
        st = self.settings
        st.setValue("ui_lang", i18n.get_lang())
        st.setValue("theme", self.theme.index)
        st.setValue("tab", self.tabs.index)
        st.setValue("side_by_side", self.split_btn.isChecked())
        self.file.save_settings(st)
        self.live.save_settings(st)
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
