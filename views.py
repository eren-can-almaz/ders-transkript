"""Bir öğenin ayrıntı sayfası (sağ taraf).

Mikrofon kaydı:  yeni → (● başlat) → kaydediliyor ⇄ duraklatıldı → (■ bitir) → bitti
Ses dosyası:     hazır → (Yazıya dök) → yazıya dökülüyor → bitti
Bitmiş her öğede: başlık, tarih · süre, oynatıcı, Yazıya dök, transkript, Kaydet / Sil.
Her sayfanın işçisi bağımsızdır: bir dosya yazıya dökülürken başka bir sayfada kayıt yapılabilir.
"""
import math
import time
from pathlib import Path

import numpy as np
from PyQt6.QtCore import QSize, Qt, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtMultimedia import QMediaDevices
from PyQt6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QProgressBar, QPushButton, QSizePolicy, QVBoxLayout, QWidget,
)

from audio import Microphone
from core import SR, FileWorker, LiveWorker, fmt_time
from i18n import fmt_date, tr
from library import unsaved_dir
from theme import colors, glyph
from ui_parts import Options, PlayerBar, RecordButton, TranscriptBox, Waveform, repolish

STEPS = ["step_model", "step_read", "step_transcribe"]


class ItemView(QWidget):
    row_status = pyqtSignal(str, str)   # (metin, tür) — kenar çubuğu rozeti
    row_refresh = pyqtSignal()          # başlık / süre değişti
    closed = pyqtSignal(object)         # öğe listeden kalktı
    LAG_WARN = 25.0

    def __init__(self, item, library, settings, folder_getter):
        super().__init__()
        self.item = item
        self.lib = library
        self.settings = settings
        self.folder_getter = folder_getter
        self.rec_state = "new" if item.new else "done"   # new | loading | recording | paused | finishing | done
        self.live_worker = None
        self.file_worker = None
        self.mic = None
        self.paused = False
        self.captured = self.processed = 0.0
        self._devices = []
        self._t_start = self._t_upd = self._eta = None
        self._step = -1
        self._note = ""
        self.other_recording = lambda: False  # ana pencere bağlar

        lay = QVBoxLayout(self)
        lay.setContentsMargins(44, 32, 44, 28)
        lay.setSpacing(18)

        # ---- başlık
        head = QHBoxLayout()
        head.setSpacing(8)
        self.title = QLineEdit(item.title, objectName="titleEdit")
        self.title.editingFinished.connect(self._rename)
        head.addWidget(self.title, 1)
        self.reveal_btn = QPushButton(objectName="plain")
        self.reveal_btn.clicked.connect(self._reveal)
        self.save_btn = QPushButton(objectName="primary")
        self.save_btn.clicked.connect(self.save)
        self.delete_btn = QPushButton(objectName="destructive")
        self.delete_btn.clicked.connect(self.delete)
        for b in (self.reveal_btn, self.save_btn, self.delete_btn):
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            head.addWidget(b, alignment=Qt.AlignmentFlag.AlignVCenter)
        lay.addLayout(head)
        self.meta = QLabel(objectName="meta")
        self.meta.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)  # uzun yol sayfayı genişletmesin
        lay.addWidget(self.meta)

        # ---- kaydedici (yalnızca kayıt oturumunda)
        self.rec_block = QWidget()
        rb = QVBoxLayout(self.rec_block)
        rb.setContentsMargins(0, 12, 0, 0)
        rb.setSpacing(10)
        self.wave = Waveform()
        rb.addWidget(self.wave)
        self.timer = QLabel("00:00", objectName="timer")
        self.timer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        rb.addWidget(self.timer)
        self.status = QLabel(objectName="status")
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        rb.addWidget(self.status)
        controls = QHBoxLayout()
        controls.setSpacing(28)
        controls.addStretch()
        self.pause_btn = QPushButton(objectName="round")
        self.pause_btn.setIconSize(QSize(22, 22))
        self.pause_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.pause_btn.clicked.connect(self.toggle_pause)
        self.rec_btn = RecordButton()
        self.rec_btn.clicked.connect(self.toggle_record)
        self._spacer = QWidget()
        self._spacer.setFixedSize(44, 44)  # düğmeyi ortada tutmak için duraklat düğmesiyle simetrik
        controls.addWidget(self.pause_btn, alignment=Qt.AlignmentFlag.AlignVCenter)
        controls.addWidget(self.rec_btn)
        controls.addWidget(self._spacer)
        controls.addStretch()
        rb.addSpacing(6)
        rb.addLayout(controls)
        rb.addSpacing(6)
        live_row = QHBoxLayout()
        live_row.addStretch()
        self.live_text = QCheckBox(objectName="switch")
        self.live_text.setChecked(settings.value("rec/live", True, type=bool))
        self.live_text.setCursor(Qt.CursorShape.PointingHandCursor)
        self.live_text.toggled.connect(self._on_live_toggle)
        live_row.addWidget(self.live_text)
        live_row.addStretch()
        rb.addLayout(live_row)
        self.live_hint = QLabel(objectName="faint")
        self.live_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.live_hint.setWordWrap(True)
        rb.addWidget(self.live_hint)
        self.lag = QLabel(objectName="faint")
        self.lag.setAlignment(Qt.AlignmentFlag.AlignCenter)
        rb.addWidget(self.lag)
        self.warn = QLabel(objectName="warn")
        self.warn.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.warn.setWordWrap(True)
        self.warn.hide()
        rb.addWidget(self.warn)
        lay.addWidget(self.rec_block)

        # ---- oynatıcı + yazıya dök (bitmiş öğelerde)
        self.player = PlayerBar()
        lay.addWidget(self.player)
        self.tr_row = QWidget()
        tl = QHBoxLayout(self.tr_row)
        tl.setContentsMargins(0, 0, 0, 0)
        tl.setSpacing(10)
        self.tr_btn = QPushButton(objectName="primary")
        self.tr_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.tr_btn.clicked.connect(self.transcribe)
        tl.addWidget(self.tr_btn)
        tl.addStretch()
        lay.addWidget(self.tr_row)

        # ---- seçenekler (açılır)
        self.opt_btn = QPushButton(objectName="plain")
        self.opt_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.opt_btn.clicked.connect(lambda: self._show_options(not self.opt_panel.isVisible()))
        tl.addWidget(self.opt_btn)
        self.opt_panel = QFrame(objectName="box")
        op = QVBoxLayout(self.opt_panel)
        op.setContentsMargins(20, 16, 20, 16)
        op.setSpacing(12)
        mic_row = QHBoxLayout()
        self.mic_label = QLabel(objectName="faint")
        self.mic_combo = QComboBox()
        mic_row.addWidget(self.mic_label)
        mic_row.addWidget(self.mic_combo, 1)
        self.mic_widget = QWidget()
        self.mic_widget.setLayout(mic_row)
        mic_row.setContentsMargins(0, 0, 0, 0)
        op.addWidget(self.mic_widget)
        self.opts = Options()
        self.opts.load(settings)
        self.opts.changed.connect(lambda: self.opts.save(settings))
        op.addWidget(self.opts)
        self.opt_panel.hide()
        lay.addWidget(self.opt_panel)

        # ---- ilerleme (yazıya dökerken)
        self.prog = QWidget()
        pl = QVBoxLayout(self.prog)
        pl.setContentsMargins(0, 0, 0, 0)
        pl.setSpacing(8)
        prow = QHBoxLayout()
        self.prog_step = QLabel(objectName="muted")
        self.prog_pct = QLabel(objectName="sectionTitle")
        prow.addWidget(self.prog_step)
        prow.addStretch()
        prow.addWidget(self.prog_pct)
        pl.addLayout(prow)
        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        pl.addWidget(self.bar)
        self.prog_info = QLabel(objectName="faint")
        self.prog_info.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        pl.addWidget(self.prog_info)
        self.prog.hide()
        lay.addWidget(self.prog)

        # ---- transkript
        self.box = TranscriptBox()
        self.box.set_text(item.text)
        self.box.edited.connect(lambda: self._save_timer.start(800))
        lay.addWidget(self.box, 1)
        self._save_timer = QTimer(self, singleShot=True)
        self._save_timer.timeout.connect(self._store_text)
        self.note = QLabel(objectName="faint")
        self.note.setWordWrap(True)
        lay.addWidget(self.note)

        self.ticker = QTimer(self)
        self.ticker.timeout.connect(self._tick)
        self.media = QMediaDevices(self)
        self.media.audioInputsChanged.connect(self.refresh_devices)
        self.refresh_devices()
        self.retranslate()

    # ================================================================ genel
    def busy(self):
        return self.live_worker is not None or self.file_worker is not None or \
            self.rec_state in ("loading", "recording", "paused", "finishing")

    def recording(self):
        return self.rec_state in ("loading", "recording", "paused", "finishing")

    def _layout_state(self):
        it = self.item
        session = it.kind == "rec" and self.rec_state != "done"
        self.rec_block.setVisible(session)
        self.mic_widget.setVisible(session)
        has_audio = it.audio is not None and not session
        self.player.setVisible(has_audio)
        self.tr_row.setVisible(has_audio or (session and self.rec_state == "new"))
        if session and self.rec_state != "new":
            self.opt_panel.hide()
        self.tr_btn.setVisible(has_audio)
        if has_audio and self.player.path != it.audio:
            self.player.set_source(it.audio, it.duration)
        live_on = session and self.live_text.isChecked()
        self.box.setVisible(bool(it.text.strip()) or live_on or self.file_worker is not None
                            or (session and self.rec_state != "new" and self.live_text.isChecked()))
        self.box.set_placeholder("placeholder_live" if session else
                                 "placeholder_file" if self.file_worker else "placeholder_none")
        # başlıktaki eylemler
        unsaved_rec = it.kind == "rec" and not it.saved
        self.save_btn.setVisible(unsaved_rec and self.rec_state == "done")
        self.reveal_btn.setVisible(bool(it.audio) and (it.saved or it.kind == "file"))
        self.delete_btn.setVisible(not self.recording())
        self.delete_btn.setText(tr("delete") if unsaved_rec else tr("remove"))
        self.tr_btn.setText(tr("retranscribe") if it.text.strip() else tr("transcribe"))
        self.tr_btn.setEnabled(self.file_worker is None)
        if self.file_worker is not None:
            self.tr_btn.setText(tr("cancel"))
            self.tr_btn.setEnabled(not self.file_worker.cancelled)
        self.tr_btn.setObjectName("destructive" if self.file_worker else "primary")
        repolish(self.tr_btn)
        self.title.setReadOnly(self.recording())
        self._render_meta()

    def _render_meta(self):
        it = self.item
        parts = [fmt_date(it.created)]
        if it.duration:
            parts.append(fmt_time(it.duration))
        if it.kind == "rec" and self.rec_state == "done":
            parts.append(tr("saved_in", path=self._short(it.audio.parent)) if it.saved else tr("badge_unsaved"))
        elif it.kind == "file" and it.audio:
            parts.append(self._short(it.audio.parent))
        self.meta.setText("  ·  ".join(parts))

    @staticmethod
    def _short(path, limit=48):
        s, home = str(path), str(Path.home())
        s = "~" + s[len(home):] if s.startswith(home) else s
        return s if len(s) <= limit else s[: limit // 2 - 1] + "…" + s[-(limit // 2):]

    def _show_options(self, on):
        self.opt_panel.setVisible(on)
        self.opt_btn.setText(("▾  " if on else "▸  ") + tr("options"))

    def _set_note(self, text):
        self._note = text
        self.note.setText(text)
        self.note.setVisible(bool(text))

    def retranslate(self):
        self.save_btn.setText(tr("save"))
        self.reveal_btn.setText(tr("show_in_folder"))
        self.mic_label.setText(tr("mic"))
        if not self._devices:
            self.mic_combo.setItemText(0, tr("no_mic"))
        self.live_text.setText(tr("live_text"))
        self.warn.setText(tr("lag_warn"))
        self.opts.retranslate()
        self.box.retranslate()
        self._show_options(self.opt_panel.isVisible())
        self._render_rec()
        self._layout_state()

    # ================================================================ kayıt
    def refresh_devices(self):
        cur = self.mic_combo.currentText()
        self._devices = list(QMediaDevices.audioInputs())
        default = QMediaDevices.defaultAudioInput()
        self.mic_combo.clear()
        for d in self._devices:
            self.mic_combo.addItem(d.description())
        if not self._devices:
            self.mic_combo.addItem(tr("no_mic"))
        idx = self.mic_combo.findText(cur)
        if idx < 0:
            idx = next((i for i, d in enumerate(self._devices) if d == default), 0)
        self.mic_combo.setCurrentIndex(idx)
        self.rec_btn.setEnabled(bool(self._devices) or self.recording())

    def _on_live_toggle(self, on):
        self.settings.setValue("rec/live", on)
        self._render_rec()
        self._layout_state()

    def _render_rec(self):
        st = self.rec_state
        c = colors()
        self.status.setText({"new": tr("rec_ready"), "loading": tr("st_loading"), "recording": tr("st_recording"),
                             "paused": tr("st_paused"), "finishing": tr("st_finishing")}.get(st, ""))
        self.status.setProperty("on", "true" if st in ("recording", "loading") else "false")
        repolish(self.status)
        active = st in ("loading", "recording", "paused")
        self.pause_btn.setVisible(active)
        self._spacer.setVisible(active)
        self.pause_btn.setIcon(glyph("play" if self.paused else "pause", c["text"]))
        self.pause_btn.setToolTip(tr("resume_tip" if self.paused else "pause_tip"))
        self.rec_btn.setToolTip(tr("rec_stop_tip" if active else "rec_start_tip"))
        self.rec_btn.setEnabled(st != "finishing" and (bool(self._devices) or active))
        self.live_text.setEnabled(st == "new")
        self.live_hint.setText(tr("live_text_on" if self.live_text.isChecked() else "live_text_off"))
        self.live_hint.setVisible(st == "new")
        self.lag.setVisible(active and self.live_text.isChecked() and st != "loading")
        self.wave.set_active(st == "recording")
        self.wave.setVisible(st != "new")  # başlamadan boş dalga (ve orta çizgisi) gösterme

    def toggle_record(self):
        if self.rec_state == "new":
            self._check_permission_then_start()
        elif self.rec_state in ("loading", "recording", "paused"):
            self.finish()

    def _check_permission_then_start(self):
        """macOS mikrofon izni ister; diğer sistemlerde doğrudan başlar."""
        try:
            from PyQt6.QtCore import QMicrophonePermission
        except ImportError:
            return self.start()
        app = QApplication.instance()
        perm = QMicrophonePermission()
        status = app.checkPermission(perm)
        if status == Qt.PermissionStatus.Granted:
            return self.start()
        if status == Qt.PermissionStatus.Undetermined:
            app.requestPermission(perm, self, lambda p: self._check_permission_then_start()
                                  if app.checkPermission(p) != Qt.PermissionStatus.Undetermined else None)
            return
        QMessageBox.warning(self, tr("error_title"), tr("mic_denied"))

    def start(self):
        if not self._devices or self.rec_state != "new":
            return
        if self.other_recording():  # tek mikrofon: aynı anda tek kayıt
            QMessageBox.information(self, tr("new_recording"), tr("rec_busy"))
            return
        device = self._devices[self.mic_combo.currentIndex()]
        live = self.live_text.isChecked()
        base = unsaved_dir() / self.item.id
        w = self.live_worker = LiveWorker(
            self.opts.model_name(), self.opts.language(), self.opts.timestamps(), self.opts.threads(),
            record_base=base, transcribe=live, preview=True,
            draft_interval=1.5 if self.opts.is_quiet() else 1.0)
        w.ready.connect(lambda: self._set_rec_state("recording") if self.rec_state == "loading" else None)
        w.segment.connect(self.box.append)
        w.draft.connect(self.box.set_draft)
        w.processed.connect(lambda s: setattr(self, "processed", s))
        w.info.connect(lambda k, v: self._set_note(tr(k, v=v)))
        w.finished_ok.connect(self._on_rec_done)
        w.failed.connect(self._on_rec_fail)
        w.finished.connect(self._on_rec_thread_end)
        try:
            # mikrofon hemen açılır: model yüklenirken gelen ses kuyrukta bekler, kaybolmaz
            self.mic = Microphone(device, self._on_audio, self)
        except Exception as e:
            self.live_worker = None
            QMessageBox.critical(self, tr("error_title"), f"{tr('mic_error')}\n{e}")
            return
        self.captured = self.processed = 0.0
        self.paused = False
        self.wave.clear()
        self.box.set_text("")
        self.rec_btn.set_recording(True)
        self._show_options(False)
        self._set_rec_state("loading" if live else "recording")
        self.ticker.start(200)
        w.start()

    def toggle_pause(self):
        if self.rec_state not in ("recording", "paused", "loading"):
            return
        self.paused = not self.paused
        if self.paused and self.live_worker:
            self.live_worker.flush()  # duraklarken birikeni hemen kesinleştir
        self._set_rec_state("paused" if self.paused else "recording")

    def finish(self):
        if self.mic:
            self.mic.stop()
            self.mic = None
        self.paused = False
        self.rec_btn.set_recording(False)
        self._set_rec_state("finishing")
        self.live_worker.stop()

    def _on_audio(self, a):
        if self.paused:
            return
        self.captured += len(a) / SR
        rms = float(np.sqrt((a ** 2).mean())) if len(a) else 0.0
        db = 20 * math.log10(rms + 1e-9)
        self.wave.add((db + 55) / 50)
        if self.live_worker:
            self.live_worker.feed(a)

    def _tick(self):
        if self.recording():
            self.timer.setText(fmt_time(self.captured))
            lag = max(0.0, self.captured - self.processed)
            self.lag.setText(tr("lag_fmt", s=f"{lag:.0f}"))
            self.warn.setVisible(self.live_text.isChecked() and lag > self.LAG_WARN)
            self.row_status.emit(("❚❚ " if self.paused else "● ") + fmt_time(self.captured), "rec")
        elif self.file_worker is not None:
            self._tick_file()

    def _set_rec_state(self, st):
        self.rec_state = st
        self._render_rec()
        self._layout_state()

    def _on_rec_done(self, rec_path):
        it = self.item
        it.new = False
        it.audio = Path(rec_path) if rec_path else None
        it.duration = self.captured
        it.text = self.box.plain()
        if it.audio is None:  # ses dosyası oluşmadı: öğe anlamsız
            self.lib.remove(it, delete_files=True)
            self.closed.emit(it)
            return
        self.lib.write_text(it)
        self.lib.save_index()
        self.rec_state = "done"
        self.row_status.emit("", "")
        self.row_refresh.emit()
        self._render_rec()
        self._layout_state()

    def _on_rec_fail(self, msg):
        if self.mic:
            self.mic.stop()
            self.mic = None
        QMessageBox.critical(self, tr("error_title"), msg)

    def _on_rec_thread_end(self):
        self.live_worker = None
        self.ticker.stop()
        self.warn.hide()
        if self.rec_state != "done":  # hata: yeniden başlatılabilsin
            self.rec_btn.set_recording(False)
            self.row_status.emit("", "")
            self._set_rec_state("new")

    # ================================================================ yazıya dökme
    def transcribe(self):
        if self.file_worker is not None:
            self.file_worker.cancel()
            self.tr_btn.setEnabled(False)
            self.prog_step.setText(tr("cancelling"))
            return
        if self.item.text.strip():
            if QMessageBox.question(self, tr("retranscribe"), tr("replace_q")) != QMessageBox.StandardButton.Yes:
                return
        w = self.file_worker = FileWorker(str(self.item.audio), self.opts.model_name(), self.opts.language(),
                                          self.opts.timestamps(), self.opts.threads())
        w.step.connect(self._on_step)
        w.info.connect(lambda k, v: self._set_note(tr(k, v=v)))
        w.progress.connect(self._on_progress)
        w.segment.connect(self.box.append)
        w.finished_ok.connect(self._on_tr_done)
        w.failed.connect(lambda m: QMessageBox.critical(self, tr("error_title"), m))
        w.finished.connect(self._on_tr_thread_end)
        self._backup_text = self.item.text
        self.box.set_text("")
        self._set_note("")
        self._t_start = time.time()
        self._t_upd = self._eta = None
        self.prog.show()
        self.bar.setRange(0, 0)
        self.prog_pct.setText("")
        self.prog_info.setText("")
        self._show_options(False)
        self.ticker.start(1000)
        self._layout_state()
        w.start()

    def _on_step(self, i):
        self._step = i
        self.prog_step.setText(tr(STEPS[i]) + "…")
        if i == 2:
            self.bar.setRange(0, 1000)
            self.bar.setValue(0)
            self._t_tr = time.time()
        self.row_status.emit("…", "busy")

    def _on_progress(self, done, total):
        frac = min(done / total, 1.0) if total > 0 else 0.0
        self.bar.setValue(int(frac * 1000))
        self.prog_pct.setText(f"%{int(frac * 100)}")
        self.row_status.emit(f"%{int(frac * 100)}", "busy")
        self._prog_audio = tr("progress_fmt", done=fmt_time(done), total=fmt_time(total))
        elapsed = time.time() - self._t_tr
        if frac > 0.03 and elapsed > 5:
            self._eta = elapsed / frac - elapsed
            self._t_upd = time.time()
        self._tick_file()

    def _tick_file(self):
        if self._step != 2:
            return
        if self._eta is None:
            eta = tr("eta_calc")
        else:
            eta = tr("eta_fmt", t=fmt_time(max(0.0, self._eta - (time.time() - self._t_upd))))
        self.prog_info.setText(f"{getattr(self, '_prog_audio', '')}   ·   {eta}")

    def _on_tr_done(self, elapsed):
        it = self.item
        it.text = self.box.plain()
        self.lib.write_text(it)
        if it.audio and (it.kind == "file" or it.saved):  # ses dosyasının yanına da .txt bırak
            try:
                it.audio.with_suffix(".txt").write_text(it.text, encoding="utf-8")
            except OSError:
                pass
        self._set_note(tr("done_fmt", t=fmt_time(elapsed)))
        QApplication.alert(self.window())

    def _on_tr_thread_end(self):
        w = self.file_worker
        self.file_worker = None
        self.ticker.stop()
        self.prog.hide()
        self._step = -1
        if w.cancelled:  # iptal: eski metni geri getir
            self.box.set_text(self._backup_text)
            self._set_note(tr("cancelled"))
        self.row_status.emit("", "")
        self._layout_state()

    # ================================================================ eylemler
    def _store_text(self):
        if self.recording() or self.file_worker is not None:
            return
        self.item.text = self.box.plain()
        self.lib.write_text(self.item)
        if self.item.saved and self.item.audio:
            try:
                self.item.audio.with_suffix(".txt").write_text(self.item.text, encoding="utf-8")
            except OSError:
                pass

    def _rename(self):
        name = self.title.text().strip()
        if not name:
            self.title.setText(self.item.title)
            return
        if name != self.item.title:
            self.item.title = name
            self.lib.save_index()
            self.row_refresh.emit()

    def _reveal(self):
        if self.item.audio:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.item.audio.parent)))

    def save(self):
        it = self.item
        self._rename()
        self._store_text()
        folder = Path(self.folder_getter())
        folder.mkdir(parents=True, exist_ok=True)
        safe = "".join(ch for ch in it.title if ch not in '\\/:*?"<>|').strip() or "Kayit"
        default = folder / f"{safe}{it.audio.suffix}"
        path, _ = QFileDialog.getSaveFileName(self, tr("save"), str(default),
                                              f"{tr('filter_audio')} (*{it.audio.suffix})")
        if not path:
            return
        dest = Path(path)
        if dest.suffix.lower() != it.audio.suffix:
            dest = dest.with_name(dest.name + it.audio.suffix)
        self.player.release()
        self.lib.save_recording(it, dest)
        self.title.setText(it.title)
        self.row_refresh.emit()
        self._layout_state()

    def delete(self):
        it = self.item
        unsaved = it.kind == "rec" and not it.saved
        if it.new:  # hiç başlatılmamış boş kayıt: sormadan kaldır
            self.lib.remove(it, delete_files=False)
            self.closed.emit(it)
            return
        if unsaved and QMessageBox.question(
                self, tr("delete"), tr("delete_q"),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        self.player.release()
        self.lib.remove(it, delete_files=unsaved)
        self.closed.emit(it)

    def stop_for_quit(self):
        if self.live_worker is not None:
            if self.mic:
                self.mic.stop()
            self.live_worker.stop()
            self.live_worker.wait(15000)  # son parça çevrilip ses dosyası kapatılsın
            QApplication.processEvents()  # bitiş sinyalleri işlensin: kayıt listeye girsin
        if self.file_worker is not None:
            self.file_worker.cancel()
            self.file_worker.wait(3000)
        self._store_text()
        self.player.release()

    def refresh_icons(self):
        self._render_rec()
        self.player.refresh_icons()
