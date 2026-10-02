"""Ders Transkript — ders kayıtlarını ve canlı konuşmayı internetsiz metne çeviren masaüstü uygulaması.

faster-whisper (CPU, int8) + PyQt6. Apple Ses Kayıtları tarzı: solda kayıtlar ve eklenen ses
dosyaları listesi (+ ile yenisi), sağda seçilenin sayfası. Her sayfa bağımsız çalışır.
Modüller: core (modeller, işçiler), library (liste ve kalıcılık), views (ayrıntı sayfası),
ui_parts (arayüz parçaları), audio (mikrofon), theme (görünüm), i18n (arayüz dilleri).
"""
import os
import sys
from pathlib import Path

from PyQt6.QtCore import QSettings, QSize, Qt, QUrl
from PyQt6.QtGui import QDesktopServices, QGuiApplication, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QDoubleSpinBox, QFileDialog, QFrame, QGridLayout,
    QHBoxLayout, QLabel, QSpinBox,
    QMainWindow, QMenu, QMessageBox, QPushButton, QScrollArea, QStackedWidget, QVBoxLayout, QWidget,
)

import i18n
from core import AUDIO_EXT, MODES, QUALITY, decode_audio, lower_priority, model_path, probe_audio, recordings_dir
from i18n import UI_LANGUAGES, tr
from library import Item, Library
from theme import THEME_CHOICES, app_icon, apply_theme, colors, glyph, icon_pixmap
from ui_parts import ItemRow
from views import ItemView


class EmptyState(QWidget):
    """Listede hiçbir şey yokken ya da hiçbir şey seçili değilken."""

    def __init__(self, on_new, on_add):
        super().__init__()
        outer = QVBoxLayout(self)
        outer.addStretch(2)
        icon = QLabel()
        icon.setPixmap(icon_pixmap(160).scaled(80, 80, Qt.AspectRatioMode.KeepAspectRatio,
                                               Qt.TransformationMode.SmoothTransformation))
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(icon)
        outer.addSpacing(10)
        self.title = QLabel(objectName="emptyTitle")
        self.hint = QLabel(objectName="muted")
        for w in (self.title, self.hint):
            w.setAlignment(Qt.AlignmentFlag.AlignCenter)
            outer.addWidget(w)
        outer.addSpacing(18)
        col = QVBoxLayout()
        col.setSpacing(10)
        self.btn_rec = QPushButton(objectName="choice")
        self.btn_file = QPushButton(objectName="choice")
        for b, fn in ((self.btn_rec, on_new), (self.btn_file, on_add)):
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setIconSize(QSize(24, 24))
            b.setFixedWidth(320)
            b.clicked.connect(fn)
            col.addWidget(b, alignment=Qt.AlignmentFlag.AlignHCenter)
        outer.addLayout(col)
        outer.addStretch(3)

    def retranslate(self, has_items=None):
        c = colors()
        if has_items is not None:
            self._has_items = has_items
        some = getattr(self, "_has_items", False)
        self.title.setText(tr("empty_title_some" if some else "empty_title"))
        self.hint.setText(tr("empty_hint_some" if some else "empty_hint"))
        self.btn_rec.setText("   " + tr("new_recording"))
        self.btn_file.setText("   " + tr("add_file"))
        self.btn_rec.setIcon(glyph("mic", c["red"]))
        self.btn_file.setIcon(glyph("wave", c["accent"]))


class SettingsDialog(QDialog):
    """Seyrek değişen ayarlar: arayüz dili, görünüm, kayıt klasörü."""

    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self.setModal(True)
        self.setMinimumWidth(460)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(26, 24, 26, 20)
        lay.setSpacing(16)
        self.heading = QLabel(objectName="emptyTitle")
        lay.addWidget(self.heading)
        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(14)
        self.l_lang, self.l_theme, self.l_folder = (QLabel(objectName="muted") for _ in range(3))
        self.lang = QComboBox()
        for code, name in UI_LANGUAGES:
            self.lang.addItem(name, code)
        self.lang.setCurrentIndex(max(0, self.lang.findData(i18n.get_lang())))
        self.lang.currentIndexChanged.connect(lambda: win.set_ui_lang(self.lang.currentData()))
        self.theme = QComboBox()
        self.theme.currentIndexChanged.connect(lambda i: i >= 0 and win.set_theme(i))
        self.folder = QLabel(objectName="muted")
        f_row = QHBoxLayout()
        f_row.addWidget(self.folder, 1)
        self.change = QPushButton(objectName="plain")
        self.change.clicked.connect(self._choose)
        self.open = QPushButton(objectName="plain")
        self.open.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(win.folder))))
        f_row.addWidget(self.change)
        f_row.addWidget(self.open)
        grid.addWidget(self.l_lang, 0, 0)
        grid.addWidget(self.lang, 0, 1)
        grid.addWidget(self.l_theme, 1, 0)
        grid.addWidget(self.theme, 1, 1)
        grid.addWidget(self.l_folder, 2, 0)
        grid.addLayout(f_row, 2, 1)
        grid.setColumnStretch(1, 1)
        lay.addLayout(grid)
        self.offline = QLabel(objectName="faint")
        lay.addWidget(self.offline)

        # ---- gelişmiş
        sep = QFrame(objectName="sep")
        lay.addWidget(sep)
        self.adv = QCheckBox(objectName="switch")
        self.adv.setChecked(win.settings.value("adv/enabled", False, type=bool))
        self.adv.toggled.connect(self._on_adv)
        lay.addWidget(self.adv)
        self.adv_hint = QLabel(objectName="faint")
        self.adv_hint.setWordWrap(True)
        lay.addWidget(self.adv_hint)
        self.adv_box = QWidget()
        ab = QGridLayout(self.adv_box)
        ab.setContentsMargins(0, 4, 0, 0)
        ab.setHorizontalSpacing(16)
        ab.setVerticalSpacing(10)
        self.adv_head = QLabel(objectName="sectionTitle")
        ab.addWidget(self.adv_head, 0, 0, 1, 2)
        self.draft_model = QComboBox()
        self.f_interval = QDoubleSpinBox(minimum=0.3, maximum=3.0, singleStep=0.1, decimals=1)
        self.f_threads = QSpinBox(minimum=1, maximum=max(1, os.cpu_count() or 4))
        self.f_silence = QDoubleSpinBox(minimum=0.2, maximum=1.5, singleStep=0.1, decimals=1)
        self.f_min = QDoubleSpinBox(minimum=1.0, maximum=5.0, singleStep=0.5, decimals=1)
        self.f_max = QDoubleSpinBox(minimum=4.0, maximum=20.0, singleStep=1.0, decimals=0)
        self.f_beam = QSpinBox(minimum=1, maximum=5)
        self.adv_fields = [("draft_model", self.draft_model), ("draft_interval", self.f_interval),
                           ("draft_threads", self.f_threads), ("silence_tail", self.f_silence),
                           ("min_chunk", self.f_min), ("max_chunk", self.f_max), ("beam", self.f_beam)]
        self.adv_labels = {}
        for r, (key, w) in enumerate(self.adv_fields, start=1):
            lbl = QLabel(objectName="muted")
            self.adv_labels[key] = lbl
            ab.addWidget(lbl, r, 0)
            ab.addWidget(w, r, 1, alignment=Qt.AlignmentFlag.AlignLeft)
        self.defaults_btn = QPushButton(objectName="tinted")
        self.defaults_btn.clicked.connect(self._defaults)
        ab.addWidget(self.defaults_btn, len(self.adv_fields) + 1, 0, 1, 2, alignment=Qt.AlignmentFlag.AlignLeft)
        lay.addWidget(self.adv_box)
        self._load_adv()
        for key, w in self.adv_fields:
            sig = w.currentIndexChanged if isinstance(w, QComboBox) else w.valueChanged
            sig.connect(self._store_adv)
        self.adv_box.setVisible(self.adv.isChecked())
        row = QHBoxLayout()
        row.addStretch()
        self.close_btn = QPushButton(objectName="primary")
        self.close_btn.clicked.connect(self.accept)
        row.addWidget(self.close_btn)
        lay.addLayout(row)
        self.retranslate()

    def _load_adv(self):
        from core import LIVE_DEFAULTS
        st = self.win.settings
        self._loading = True
        for key, w in self.adv_fields:
            v = st.value(f"adv/{key}", LIVE_DEFAULTS[key])
            if isinstance(w, QComboBox):
                w.setCurrentIndex(max(0, w.findData(v)))
            else:
                w.setValue(type(LIVE_DEFAULTS[key])(v))
        self._loading = False

    def _store_adv(self, *_):
        if getattr(self, "_loading", False):
            return
        for key, w in self.adv_fields:
            self.win.settings.setValue(f"adv/{key}", w.currentData() if isinstance(w, QComboBox) else w.value())

    def _defaults(self):
        """Tek tıkla tüm gelişmiş değerleri varsayılana döndür."""
        from core import LIVE_DEFAULTS
        for key, v in LIVE_DEFAULTS.items():
            self.win.settings.setValue(f"adv/{key}", v)
        self._load_adv()

    def _on_adv(self, on):
        self.win.settings.setValue("adv/enabled", on)
        self.adv_box.setVisible(on)
        self.adjustSize()
        self.win.advanced_changed()

    def _choose(self):
        d = QFileDialog.getExistingDirectory(self, tr("folder_dialog"), str(self.win.folder))
        if d:
            self.win.folder = Path(d)
            self.win.settings.setValue("folder", d)
            self.retranslate()

    def retranslate(self):
        self.setWindowTitle(tr("settings"))
        self.heading.setText(tr("settings"))
        self.l_lang.setText(tr("set_ui_lang"))
        self.l_theme.setText(tr("set_theme"))
        self.l_folder.setText(tr("set_folder"))
        self.theme.blockSignals(True)
        self.theme.clear()
        for key, _ in THEME_CHOICES:
            self.theme.addItem(tr(key))
        self.theme.setCurrentIndex(self.win.theme_index)
        self.theme.blockSignals(False)
        self.folder.setText(ItemView._short(self.win.folder))
        self.folder.setToolTip(str(self.win.folder))
        self.change.setText(tr("change"))
        self.open.setText(tr("open"))
        self.offline.setText("●  " + tr("offline"))
        self.close_btn.setText(tr("close"))
        self.adv.setText(tr("adv_enable"))
        self.adv_hint.setText(tr("adv_hint"))
        self.adv_head.setText(tr("adv_live"))
        cur = self.draft_model.currentData()
        self._loading = True
        self.draft_model.clear()
        for m in ("tiny", "base", "small"):
            self.draft_model.addItem(tr(f"dm_{m}"), m)
        self._loading = False
        self._load_adv() if cur is None else self.draft_model.setCurrentIndex(max(0, self.draft_model.findData(cur)))
        for key, k in [("draft_model", "adv_draft_model"), ("draft_interval", "adv_interval"),
                       ("draft_threads", "adv_threads"), ("silence_tail", "adv_silence"),
                       ("min_chunk", "adv_min_chunk"), ("max_chunk", "adv_max_chunk"), ("beam", "adv_beam")]:
            self.adv_labels[key].setText(tr(k))
        for w in (self.f_interval, self.f_silence, self.f_min, self.f_max):
            w.setSuffix(tr("unit_s"))
        self.defaults_btn.setText("↺  " + tr("adv_defaults"))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = QSettings("DersTranskript", "DersTranskript")
        i18n.set_lang(self.settings.value("ui_lang", _default_ui_lang()))
        self.theme_index = self._int("theme", 0, len(THEME_CHOICES))
        self.folder = Path(self.settings.value("folder", str(recordings_dir())))
        self.setWindowIcon(app_icon())
        self.resize(1080, 760)
        self.setMinimumSize(820, 560)
        self.setAcceptDrops(True)
        self.lib = Library()
        self.rows = {}    # öğe id → ItemRow
        self.views = {}   # öğe id → (kaydırma alanı, ItemView)
        self.current = None

        root = QWidget(objectName="content")
        self.setCentralWidget(root)
        lay = QHBoxLayout(root)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # ---- kenar çubuğu: başlık + "+" , liste, ayarlar
        side = QFrame(objectName="sidebar")
        side.setFixedWidth(300)
        sl = QVBoxLayout(side)
        sl.setContentsMargins(14, 20, 14, 14)
        sl.setSpacing(10)
        top = QHBoxLayout()
        top.setContentsMargins(8, 0, 4, 0)
        self.app_title = QLabel(objectName="appTitle")
        top.addWidget(self.app_title, 1)
        self.add_btn = QPushButton("+", objectName="add")
        self.add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.add_btn.clicked.connect(self._add_menu)
        top.addWidget(self.add_btn)
        sl.addLayout(top)
        sl.addSpacing(6)
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        inner = QWidget()
        self.list = QVBoxLayout(inner)
        self.list.setContentsMargins(0, 0, 0, 0)
        self.list.setSpacing(2)
        self.list.addStretch()
        area.setWidget(inner)
        sl.addWidget(area, 1)
        self.gear = QPushButton(objectName="gear")
        self.gear.setIconSize(QSize(18, 18))
        self.gear.setCursor(Qt.CursorShape.PointingHandCursor)
        self.gear.clicked.connect(self._open_settings)
        sl.addWidget(self.gear)
        lay.addWidget(side)

        # ---- ayrıntı
        self.stack = QStackedWidget(objectName="detail")
        self.empty = EmptyState(self.new_recording, self.add_files)
        self.stack.addWidget(self.empty)
        lay.addWidget(self.stack, 1)

        for it in self.lib.items:
            self._add_row(it, top=False)
        QShortcut(QKeySequence("Ctrl+R"), self, activated=self._shortcut_record)
        try:  # "Sistem" seçiliyken işletim sistemi teması değişirse uygula
            QGuiApplication.styleHints().colorSchemeChanged.connect(lambda *_: self._apply_theme())
        except AttributeError:
            pass
        if self.lib.items:
            self.select(self.lib.items[0])
        self.retranslate()

    def _int(self, key, default, n):
        try:
            v = int(self.settings.value(key, default))
        except (TypeError, ValueError):
            v = default
        return v if 0 <= v < n else default

    # --- liste ----------------------------------------------------------
    def _add_row(self, it, top=True):
        row = ItemRow(it)
        row.clicked.connect(lambda: self.select(it))
        self.rows[it.id] = row
        if top:
            self.list.insertWidget(0, row)
        else:
            self.list.insertWidget(self.list.count() - 1, row)
        return row

    def _view(self, it):
        if it.id not in self.views:
            v = ItemView(it, self.lib, self.settings, lambda: self.folder)
            v.other_recording = lambda v=v: any(o.recording() for _, o in self.views.values() if o is not v)
            v.row_status.connect(lambda text, kind, it=it: self.rows[it.id].set_status(text, kind))
            v.row_refresh.connect(lambda it=it: self.rows[it.id].refresh())
            v.closed.connect(self._on_closed)
            v.add_audio.connect(lambda p: self.add_files([p]))
            v.close_page.connect(lambda: self.select(None))
            area = QScrollArea()
            area.setWidgetResizable(True)
            area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            area.setWidget(v)
            self.stack.addWidget(area)
            self.views[it.id] = (area, v)
        return self.views[it.id]

    def select(self, it):
        self.current = it
        for iid, row in self.rows.items():
            row.set_selected(it is not None and iid == it.id)
        if it is None:
            self.empty.retranslate(bool(self.lib.items))
            self.stack.setCurrentWidget(self.empty)
            return
        area, _ = self._view(it)
        self.stack.setCurrentWidget(area)

    def _recording_view(self):
        return next((v for _, v in self.views.values() if v.recording()), None)

    def new_recording(self):
        """Her zaman listeye yeni bir kayıt ekler (başlatılmamış olanlar kapanışta kendiliğinden düşer)."""
        it = Item("rec", self.lib.next_rec_title())
        it.new = True
        self.lib.items.insert(0, it)
        self._add_row(it)
        self.select(it)

    def add_files(self, paths=None):
        if not paths:
            exts = " ".join("*" + x for x in sorted(AUDIO_EXT))
            paths, _ = QFileDialog.getOpenFileNames(
                self, tr("file_dialog"), str(Path.home()),
                f"{tr('filter_audio')} ({exts});;{tr('filter_all')} (*)")
        last = None
        for p in paths:
            p = Path(p)
            if not p.is_file():
                continue
            dur, _ = probe_audio(str(p))
            if dur is None and p.suffix.lower() not in AUDIO_EXT:
                QMessageBox.warning(self, tr("error_title"), tr("unsupported", name=p.name))
                continue
            existing = next((i for i in self.lib.items if i.audio == p), None)
            if existing:
                last = existing
                continue
            it = Item("file", p.stem, p, duration=dur, saved=True)
            sidecar = p.with_suffix(".txt")  # daha önce yazıya dökülmüşse metni getir
            if sidecar.exists():
                it.text = sidecar.read_text(encoding="utf-8", errors="replace")
                self.lib.write_text(it)
            self.lib.add(it)
            self._add_row(it)
            last = it
        if last:
            self.select(last)

    def _on_closed(self, it):
        if it.new and it.title == tr("rec_title", n=self.lib.rec_counter):
            self.lib.rec_counter -= 1  # başlatılmadan silinen son kaydın numarası boşa gitmesin
        row = self.rows.pop(it.id, None)
        if row:
            row.setParent(None)
            row.deleteLater()
        area, view = self.views.pop(it.id, (None, None))
        if area:
            self.stack.removeWidget(area)
            area.deleteLater()
        if it in self.lib.items:
            self.lib.items.remove(it)
        if self.current is it:
            self.select(self.lib.items[0] if self.lib.items else None)

    def _add_menu(self):
        menu = QMenu(self)
        c = colors()
        a_rec = menu.addAction(glyph("mic", c["red"]), tr("new_recording"))
        a_file = menu.addAction(glyph("wave", c["accent"]), tr("add_file"))
        chosen = menu.exec(self.add_btn.mapToGlobal(self.add_btn.rect().bottomLeft()))
        if chosen is a_rec:
            self.new_recording()
        elif chosen is a_file:
            self.add_files()

    def _shortcut_record(self):
        v = self.views.get(self.current.id, (None, None))[1] if self.current else None
        if v and v.item.kind == "rec" and v.rec_state in ("new", "loading", "recording", "paused"):
            v.toggle_record()
        else:
            self.new_recording()

    # --- sürükle bırak --------------------------------------------------
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        self.add_files([u.toLocalFile() for u in e.mimeData().urls()])

    # --- ayarlar / tema / dil -------------------------------------------
    def _open_settings(self):
        SettingsDialog(self).exec()

    def set_theme(self, i):
        self.theme_index = i
        self.settings.setValue("theme", i)
        self._apply_theme()

    def _apply_theme(self):
        apply_theme(QApplication.instance(), THEME_CHOICES[self.theme_index][1])
        self.empty.retranslate()
        self.gear.setIcon(glyph("gear", colors()["muted"]))
        for _, v in self.views.values():
            v.refresh_icons()
        for row in self.rows.values():
            row.refresh()
        self.update()

    def advanced_changed(self):
        for _, v in self.views.values():
            v._layout_state()

    def set_ui_lang(self, code):
        i18n.set_lang(code)
        self.settings.setValue("ui_lang", code)
        self.retranslate()
        for dlg in self.findChildren(SettingsDialog):
            dlg.retranslate()

    def retranslate(self):
        self.setWindowTitle(tr("app_title"))
        self.app_title.setText(tr("app_title"))
        self.add_btn.setToolTip(tr("add_tip"))
        self.gear.setText("  " + tr("settings"))
        self.gear.setIcon(glyph("gear", colors()["muted"]))
        self.empty.retranslate()
        for row in self.rows.values():
            row.refresh()
        for _, v in self.views.values():
            v.retranslate()

    def closeEvent(self, e):
        views = [v for _, v in self.views.values()]
        if any(v.busy() for v in views):
            if QMessageBox.question(self, tr("quit_title"), tr("quit_body")) \
                    != QMessageBox.StandardButton.Yes:
                e.ignore()
                return
        for v in views:
            v.stop_for_quit()
        unsaved = self.lib.unsaved()
        if unsaved:  # kaydedilmemiş kayıtlar: sakla (sonraki açılışta listede) / sil / vazgeç
            box = QMessageBox(QMessageBox.Icon.Question, tr("quit_title"),
                              tr("quit_unsaved", n=len(unsaved)), parent=self)
            keep = box.addButton(tr("quit_keep"), QMessageBox.ButtonRole.AcceptRole)
            delete = box.addButton(tr("quit_delete"), QMessageBox.ButtonRole.DestructiveRole)
            box.addButton(QMessageBox.StandardButton.Cancel)
            box.setDefaultButton(keep)
            box.exec()
            if box.clickedButton() is delete:
                for it in unsaved:
                    self.lib.remove(it, delete_files=True)
            elif box.clickedButton() is not keep:
                e.ignore()
                return
        self.lib.items = [i for i in self.lib.items if not i.new]
        self.lib.save_index()
        e.accept()


def _default_ui_lang():
    """İlk açılışta arayüz dili Türkçe; Ayarlar'dan değiştirilebilir ve hatırlanır."""
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
    from audio import Microphone

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
    w = MainWindow()
    w._apply_theme()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
