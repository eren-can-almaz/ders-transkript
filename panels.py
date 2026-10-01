"""İki çalışma paneli: ses dosyası çevirme ve canlı dinleme. Birbirinden bağımsız çalışırlar."""
import math
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np
from PyQt6.QtCore import QSize, Qt, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices, QKeySequence, QShortcut
from PyQt6.QtMultimedia import QAudio, QAudioFormat, QAudioSource, QMediaDevices
from PyQt6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFileDialog, QGridLayout, QHBoxLayout, QLabel, QMessageBox,
    QProgressBar, QPushButton, QVBoxLayout, QWidget,
)

from core import (AUDIO_EXT, CHUNK_SEC, MODES, QUALITY, SR, FileWorker, LiveWorker, fmt_time, probe_audio,
                  recordings_dir)
from i18n import tr
from theme import current_colors, media_icon
from takes import Take, TakesCard, unsaved_dir
from widgets import Collapsible, DropZone, Segmented, SettingsBlock, StatCard, TranscriptCard, make_card, repolish

FILE_STEPS = ["step_model", "step_read", "step_transcribe"]


def set_button(btn, key, danger):
    btn.setText(tr(key))
    btn.setObjectName("danger" if danger else "primary")
    repolish(btn)


class FilePanel(QWidget):
    """Bir ses dosyasını baştan sona metne çevirir; ilerlemeyi ayrıntılı gösterir."""
    tab_status = pyqtSignal(str)   # sekme etiketine eklenecek durum

    def __init__(self):
        super().__init__()
        self.audio_path = None
        self.worker = None
        self._t_start = None
        self._t_start_tr = time.time()
        self._t_upd = self._eta_at_upd = None
        self._step = -1
        self._render_step = lambda: ""  # dil değişince durum satırını yeniden yazmak için
        self._render_note = lambda: ""

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(14)

        self.drop = DropZone()
        self.drop.fileDropped.connect(self.set_file)
        lay.addWidget(self.drop)

        settings, s = make_card()
        self.opts = SettingsBlock()
        s.addLayout(self.opts)
        row = QHBoxLayout()
        self.ts = QCheckBox()
        row.addWidget(self.ts)
        row.addStretch()
        self.start_btn = QPushButton(objectName="primary")
        self.start_btn.setMinimumWidth(170)
        self.start_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.start_btn.setEnabled(False)
        self.start_btn.clicked.connect(self.start)
        row.addWidget(self.start_btn)
        s.addLayout(row)
        lay.addWidget(settings)

        self.card = StatCard(["k_audio", "k_chunks", "k_elapsed", "k_eta"])
        self.card.hide()
        lay.addWidget(self.card)

        self.out = TranscriptCard("placeholder_file", "transkript.txt")
        self.out.on_saved = lambda p: self._note(lambda: tr("saved", path=p))
        lay.addWidget(self.out, 1)

        self.ticker = QTimer(self)
        self.ticker.timeout.connect(self._tick)
        self.retranslate()

    def busy(self):
        return self.worker is not None

    # --- akış -----------------------------------------------------------
    def set_file(self, path):
        if not path or not os.path.isfile(path):
            return
        if Path(path).suffix.lower() not in AUDIO_EXT:
            QMessageBox.warning(self, tr("unsupported_title"), tr("unsupported_body"))
        self.audio_path = path
        self.drop.show_file(path, *probe_audio(path))
        self.out.default_path = str(Path(path).with_suffix(".txt"))
        self.start_btn.setEnabled(self.worker is None)

    def start(self):
        if self.worker is not None:  # iptal düğmesi olarak çalışıyor
            self.worker.cancel()
            self.start_btn.setEnabled(False)
            self._note(lambda: tr("cancelling"))
            return
        if not self.audio_path:
            return
        self.out.clear()
        self.card.reset()
        self.card.show()
        self._note(lambda: "")
        self._t_start = time.time()
        self._t_upd = self._eta_at_upd = None
        w = self.worker = FileWorker(self.audio_path, self.opts.model_name(), self.opts.language(),
                                     self.ts.isChecked(), self.opts.threads())
        w.step.connect(self.on_step)
        w.info.connect(lambda k, v: self._note(lambda: tr(k, v=v)))
        w.progress.connect(self.on_progress)
        w.segment.connect(self.out.append)
        w.finished_ok.connect(self.on_done)
        w.failed.connect(self.on_fail)
        w.finished.connect(self.on_thread_end)
        self._set_running(True)
        self.ticker.start(1000)
        w.start()

    def _set_step_text(self, render):
        self._render_step = render
        self.card.step.setText(render())

    def _note(self, render):
        self._render_note = render
        self.card.note.setText(render())

    def on_step(self, i):
        self._step = i
        self._set_step_text(lambda: tr("step_fmt", i=i + 1, n=len(FILE_STEPS), name=tr(FILE_STEPS[i])))
        if i < 2:
            self.card.bar.setRange(0, 0)  # süresi belirsiz adım: kayan çubuk
            self.tab_status.emit("●")
        else:
            self.card.bar.setRange(0, 1000)
            self.card.bar.setValue(0)
            self.card.pct.setText("%0")
            self._t_start_tr = time.time()

    def on_progress(self, done, total):
        frac = min(done / total, 1.0) if total > 0 else 0.0
        pct = int(frac * 100)
        self.card.bar.setValue(int(frac * 1000))
        self.card.pct.setText(f"%{pct}")
        self.tab_status.emit(f"%{pct}")
        n_total = max(1, math.ceil(total / CHUNK_SEC))
        n_done = n_total if done >= total else min(n_total - 1, int(done // CHUNK_SEC))
        self._chunks = (n_done, n_total)
        self.card.set("k_audio", f"{fmt_time(done)} / {fmt_time(total)}")
        self.card.set("k_chunks", tr("chunks_fmt", done=n_done, total=n_total, left=n_total - n_done))
        elapsed = time.time() - self._t_start_tr
        if frac > 0.03 and elapsed > 5:
            self._eta_at_upd = elapsed / frac - elapsed
            self._t_upd = time.time()
        self._tick()

    def _tick(self):
        if self._t_start is None:
            return
        self.card.set("k_elapsed", fmt_time(time.time() - self._t_start))
        if self._eta_at_upd is None:
            self.card.set("k_eta", tr("eta_calc") if self._step == 2 else "—")
        else:
            left = max(0.0, self._eta_at_upd - (time.time() - self._t_upd))
            self.card.set("k_eta", f"~{fmt_time(left)}")

    def on_done(self, elapsed):
        c = self.card
        c.bar.setRange(0, 1000)
        c.bar.setValue(1000)
        c.pct.setText("%100")
        self._set_step_text(lambda: tr("done_fmt", t=fmt_time(elapsed)))
        c.set("k_eta", "00:00")
        out = Path(self.audio_path).with_suffix(".txt")
        try:
            out.write_text(self.out.plain(), encoding="utf-8")
            self._note(lambda: tr("autosaved", path=out))
        except OSError:
            pass
        self.tab_status.emit("✓")
        QApplication.alert(self.window())  # görev çubuğunda simgeyi yakıp söndür

    def on_fail(self, msg):
        self._set_step_text(lambda: tr("error"))
        QMessageBox.critical(self, tr("error_title"), msg)

    def on_thread_end(self):
        cancelled = self.worker.cancelled
        self.worker = None
        self.ticker.stop()
        self._t_start = None
        if cancelled:
            self._set_step_text(lambda: tr("cancelled"))
            self._note(lambda: "")
            self.card.bar.setRange(0, 1000)
            self.tab_status.emit("")
        self._set_running(False)

    def _set_running(self, running):
        set_button(self.start_btn, "cancel" if running else "start_file", running)
        self.start_btn.setEnabled(running or self.audio_path is not None)
        for w in self.opts.widgets() + [self.ts, self.drop]:
            w.setEnabled(not running)

    def stop_for_quit(self):
        if self.worker is not None:
            self.worker.cancel()
            self.worker.wait(3000)

    def retranslate(self):
        self.drop.retranslate()
        self.opts.retranslate()
        self.ts.setText(tr("timestamps"))
        set_button(self.start_btn, "cancel" if self.busy() else "start_file", self.busy())
        self.card.retranslate()
        self.card.step.setText(self._render_step())
        self.card.note.setText(self._render_note())
        if self._step == 2 and hasattr(self, "_chunks"):
            d, t = self._chunks
            self.card.set("k_chunks", tr("chunks_fmt", done=d, total=t, left=t - d))
        self._tick()
        self.out.retranslate()

    def save_settings(self, st):
        self.opts.save(st, "file/")
        st.setValue("file/ts", self.ts.isChecked())

    def load_settings(self, st):
        self.opts.load(st, "file/")
        self.ts.setChecked(st.value("file/ts", False, type=bool))


class Microphone:
    """Seçili mikrofondan sesi okur, 16 kHz mono float32'ye çevirip `on_audio`'ya verir."""
    _DTYPES = {
        QAudioFormat.SampleFormat.UInt8: (np.uint8, lambda a: (a.astype(np.float32) - 128) / 128),
        QAudioFormat.SampleFormat.Int16: (np.int16, lambda a: a.astype(np.float32) / 32768),
        QAudioFormat.SampleFormat.Int32: (np.int32, lambda a: a.astype(np.float32) / 2147483648),
        QAudioFormat.SampleFormat.Float: (np.float32, lambda a: a),
    }

    def __init__(self, device, on_audio, parent):
        fmt = QAudioFormat()
        fmt.setSampleRate(SR)
        fmt.setChannelCount(1)
        fmt.setSampleFormat(QAudioFormat.SampleFormat.Int16)
        if not device.isFormatSupported(fmt):
            fmt = device.preferredFormat()  # cihaz desteklemiyorsa kendi formatında al, sonra dönüştür
        self.fmt = fmt
        self.dtype, self.to_float = self._DTYPES.get(fmt.sampleFormat(), self._DTYPES[QAudioFormat.SampleFormat.Int16])
        self.frame_bytes = fmt.bytesPerFrame()
        self.on_audio = on_audio
        self.rest = b""
        self.source = QAudioSource(device, fmt, parent)
        self.source.setBufferSize(fmt.bytesForDuration(200_000))  # ~200 ms
        self.io = self.source.start()
        if self.io is None or self.source.error() != QAudio.Error.NoError:
            raise RuntimeError(tr("mic_error"))
        self.io.readyRead.connect(self._read)

    def _read(self):
        data = self.rest + bytes(self.io.readAll())
        usable = len(data) - len(data) % self.frame_bytes
        self.rest = data[usable:]
        if not usable:
            return
        a = self.to_float(np.frombuffer(data[:usable], self.dtype))
        ch = self.fmt.channelCount()
        if ch > 1:
            a = a.reshape(-1, ch).mean(axis=1)
        rate = self.fmt.sampleRate()
        if rate != SR:
            n = int(round(len(a) * SR / rate))
            a = np.interp(np.linspace(0, len(a) - 1, n), np.arange(len(a)), a).astype(np.float32)
        self.on_audio(a)

    def stop(self):
        self.source.stop()


REC_MODES = ["rm_both", "rm_record", "rm_text"]  # kaydet+yaz / yalnızca kaydet / yalnızca yaz


class LivePanel(QWidget):
    """Ses kaydedici + canlı transkript. Tek düğmeyle kayıt; isteğe bağlı canlı metin."""
    tab_status = pyqtSignal(str)
    transcribe_request = pyqtSignal(str)   # kaydı dosya panelinde yazıya dök
    LAG_WARN = 25.0  # sn; gecikme bunu aşarsa işlemcinin yetişemediği uyarısı

    def __init__(self):
        super().__init__()
        self.worker = None
        self.mic = None
        self.paused = False
        self.captured = 0.0
        self.processed = 0.0
        self.folder = recordings_dir()
        self._state = "idle"     # idle | loading | recording | paused | finishing | done
        self._render_note = lambda: ""
        self._devices = []

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(14)

        # ---- kaydedici kartı
        rec, r = make_card()
        top = QHBoxLayout()
        top.setSpacing(14)
        self.rec_btn = QPushButton(objectName="recBtn")
        self.rec_btn.setIconSize(QSize(40, 40))
        self.rec_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.rec_btn.clicked.connect(self.toggle)
        self.pause_btn = QPushButton(objectName="roundBtn")
        self.pause_btn.setIconSize(QSize(24, 24))
        self.pause_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.pause_btn.clicked.connect(self.toggle_pause)
        self.pause_btn.hide()
        clock = QVBoxLayout()
        clock.setSpacing(0)
        self.state_lbl = QLabel(objectName="recState")
        self.timer_lbl = QLabel("00:00", objectName="timer")
        clock.addWidget(self.state_lbl)
        clock.addWidget(self.timer_lbl)
        top.addWidget(self.rec_btn)
        top.addWidget(self.pause_btn)
        top.addLayout(clock)
        top.addStretch()
        lvl = QVBoxLayout()
        lvl.setSpacing(6)
        self.level_title = QLabel(objectName="k")
        self.meter = QProgressBar(objectName="meter")
        self.meter.setTextVisible(False)
        self.meter.setFixedSize(170, 6)
        self.meter.setRange(0, 100)
        lvl.addStretch()
        lvl.addWidget(self.level_title)
        lvl.addWidget(self.meter)
        lag = QHBoxLayout()
        self.lag_title = QLabel(objectName="k")
        self.lag_val = QLabel("—", objectName="v")
        lag.addWidget(self.lag_title)
        lag.addWidget(self.lag_val)
        lag.addStretch()
        lvl.addSpacing(4)
        lvl.addLayout(lag)
        lvl.addStretch()
        top.addLayout(lvl)
        r.addLayout(top)

        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(6)
        self.mic_title = QLabel(objectName="section")
        self.mic_combo = QComboBox()
        self.refresh_btn = QPushButton("↻", objectName="icon")
        self.refresh_btn.clicked.connect(self.refresh_devices)
        grid.addWidget(self.mic_title, 0, 0)
        grid.addWidget(self.mic_combo, 1, 0)
        grid.addWidget(self.refresh_btn, 1, 1)
        grid.setColumnStretch(0, 1)
        r.addLayout(grid)

        self.mode_title = QLabel(objectName="section")
        self.rec_mode = Segmented(REC_MODES)
        self.rec_mode.changed.connect(self._on_mode)
        self.mode_hint = QLabel(objectName="hint")
        self.mode_hint.setWordWrap(True)
        r.addWidget(self.mode_title)
        r.addWidget(self.rec_mode, alignment=Qt.AlignmentFlag.AlignLeft)
        r.addWidget(self.mode_hint)

        frow = QHBoxLayout()
        frow.setSpacing(6)
        self.folder_title = QLabel(objectName="section")
        self.folder_lbl = QLabel(objectName="path")
        self.folder_change = QPushButton(objectName="link")
        self.folder_change.clicked.connect(self.choose_folder)
        self.folder_open = QPushButton(objectName="link")
        self.folder_open.clicked.connect(lambda: self._open(self.folder))
        frow.addWidget(self.folder_title)
        frow.addSpacing(6)
        frow.addWidget(self.folder_lbl, 1)
        frow.addWidget(self.folder_change)
        frow.addWidget(self.folder_open)
        r.addLayout(frow)

        self.warn = QLabel(objectName="warn")
        self.warn.setWordWrap(True)
        self.warn.hide()
        r.addWidget(self.warn)
        self.note = QLabel(objectName="hint")
        self.note.setWordWrap(True)
        self.note.hide()
        r.addWidget(self.note)

        lay.addWidget(rec)

        # ---- bu oturumun kayıtları (Kaydet / Sil)
        self.takes = TakesCard(lambda: self.folder)
        self.takes.selected.connect(self._show_take)
        self.takes.transcribe.connect(self.transcribe_request)
        lay.addWidget(self.takes)
        self.viewing = None  # transkript kartında gösterilen kayıt

        # ---- yazıya dökme ayarları (açılır-kapanır; kapalıyken özet satırı)
        self.tr_card = Collapsible()
        t = self.tr_card.body_layout
        self.opts = SettingsBlock()
        t.addLayout(self.opts)
        self.ts = QCheckBox()
        self.preview = QCheckBox()
        self.preview.setChecked(True)
        t.addWidget(self.ts)
        t.addWidget(self.preview)
        for sig in (self.opts.quality.changed, self.opts.mode.changed, self.opts.lang.currentIndexChanged,
                    self.preview.toggled):
            sig.connect(self._update_summary)
        lay.addWidget(self.tr_card)

        self.out = TranscriptCard("placeholder_live", "canli_transkript.txt")
        self.out.on_saved = lambda p: self._set_note(lambda: tr("saved", path=p))
        lay.addWidget(self.out, 1)

        self.ticker = QTimer(self)
        self.ticker.timeout.connect(self._tick)
        self.blink = QTimer(self)
        self.blink.timeout.connect(self._blink)
        self.media = QMediaDevices(self)
        self.media.audioInputsChanged.connect(self.refresh_devices)
        QShortcut(QKeySequence("Ctrl+R"), self, activated=self.toggle)
        self.refresh_devices()
        self.retranslate()

    def busy(self):
        return self.worker is not None

    # --- yardımcılar ----------------------------------------------------
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
        if self.worker is None:
            self.rec_btn.setEnabled(bool(self._devices))

    def choose_folder(self):
        d = QFileDialog.getExistingDirectory(self, tr("folder_dialog"), str(self.folder))
        if d:
            self.folder = Path(d)
            self._show_folder()

    def _show_folder(self):
        home = str(Path.home())
        text = str(self.folder)
        if text.startswith(home):
            text = "~" + text[len(home):]
        fm = self.folder_lbl.fontMetrics()
        self.folder_lbl.setText(fm.elidedText(text, Qt.TextElideMode.ElideMiddle, 320))
        self.folder_lbl.setToolTip(str(self.folder))

    @staticmethod
    def _open(path):
        Path(path).mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def _mode(self):
        i = self.rec_mode.index
        return i in (0, 1), i in (0, 2)  # (kaydet, yazıya dök)

    def _on_mode(self, *_):
        _, transcribe = self._mode()
        self.mode_hint.setText(tr(REC_MODES[self.rec_mode.index] + "_desc"))
        self.tr_card.setVisible(transcribe)
        self.tr_card.setEnabled(self.worker is None)
        self.out.placeholder_key = "placeholder_live" if transcribe else "placeholder_record_only"
        self.out.retranslate()

    def refresh_icons(self):
        """Kayıt/duraklat simgeleri: durum ve temaya göre."""
        if hasattr(self, "takes"):
            self.takes.refresh_icons()
        c = current_colors()
        recording = self._state in ("loading", "recording", "paused")
        self.rec_btn.setIcon(media_icon("stop" if recording else "record", c["live"]))
        self.rec_btn.setToolTip(tr("rec_stop_tip" if recording else "rec_start_tip"))
        self.pause_btn.setIcon(media_icon("play" if self.paused else "pause", c["text"]))
        self.pause_btn.setToolTip(tr("resume_tip" if self.paused else "pause_tip"))

    # --- akış -----------------------------------------------------------
    def toggle(self):
        if self._state in ("loading", "recording", "paused"):
            self.stop()
        elif self.worker is None:
            self._check_permission_then_start()

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
        if not self._devices:
            return
        record, transcribe = self._mode()
        device = self._devices[self.mic_combo.currentIndex()]
        self._store_edits()
        self.viewing = None
        self.takes.select(None)
        # önce geçici klasöre: listede Kaydet'e basılınca kalıcı yere taşınır
        self.stem = datetime.now().strftime("%Y-%m-%d %H-%M-%S")  # noktasız: uzantı sanılmasın
        self.base = unsaved_dir() / self.stem
        quiet = self.opts.mode.index == 0
        w = self.worker = LiveWorker(
            self.opts.model_name(), self.opts.language(), self.ts.isChecked(), self.opts.threads(),
            record_base=self.base if record else None, transcribe=transcribe,
            preview=self.preview.isChecked(), draft_interval=1.5 if quiet else 1.0)
        w.ready.connect(lambda: self._set_state("recording") if self._state == "loading" else None)
        w.segment.connect(self.out.append)
        w.draft.connect(self.out.set_draft)
        w.processed.connect(self._on_processed)
        w.info.connect(lambda k, v: self._set_note(lambda: tr(k, v=v)))
        w.finished_ok.connect(self._on_done)
        w.failed.connect(self._on_fail)
        w.finished.connect(self._on_thread_end)
        self.out.clear()
        self.captured = self.processed = 0.0
        self.paused = False
        self._set_note(lambda: "")
        try:
            # mikrofon hemen açılır: model yüklenirken gelen ses kuyrukta bekler, kaybolmaz
            self.mic = Microphone(device, self._on_audio, self)
        except Exception as e:
            self.worker = None
            QMessageBox.critical(self, tr("error_title"), f"{tr('mic_error')}\n{e}")
            return
        self._set_state("loading" if transcribe else "recording")
        self._set_running(True)
        self.ticker.start(500)
        self.blink.start(650)
        w.start()

    def toggle_pause(self):
        if self._state not in ("recording", "paused", "loading"):
            return
        self.paused = not self.paused
        if self.paused:
            self.meter.setValue(0)
            if self.worker:
                self.worker.flush()  # duraklarken birikeni hemen kesinleştir
            self._set_state("paused")
        else:
            self._set_state("recording")

    def stop(self):
        if self.mic:
            self.mic.stop()
            self.mic = None
        self.paused = False
        self.meter.setValue(0)
        self._set_state("finishing")
        self.rec_btn.setEnabled(False)
        self.pause_btn.hide()
        self.worker.stop()

    def _on_audio(self, a):
        if self.paused:
            return
        self.captured += len(a) / SR
        rms = float(np.sqrt((a ** 2).mean())) if len(a) else 0.0
        db = 20 * math.log10(rms + 1e-9)
        self.meter.setValue(int(max(0, min(100, (db + 60) / 60 * 100))))
        if self.worker:
            self.worker.feed(a)

    def _on_processed(self, sec):
        self.processed = sec

    def _tick(self):
        self.timer_lbl.setText(fmt_time(self.captured))
        if self._state in ("recording", "paused", "loading"):
            _, transcribe = self._mode()
            lag = max(0.0, self.captured - self.processed)
            self.lag_val.setText(tr("lag_fmt", s=f"{lag:.0f}") if transcribe and self._state != "loading" else "—")
            self.warn.setVisible(transcribe and lag > self.LAG_WARN)
            icon = "❚❚" if self.paused else "●"
            self.tab_status.emit(f"{icon} {fmt_time(self.captured)}")

    def _blink(self):
        if self._state == "recording":
            on = self.state_lbl.property("on") != "true"
            self.state_lbl.setProperty("on", "true" if on else "false")
            repolish(self.state_lbl)

    def _on_done(self, rec_path):
        self._set_state("done")
        text = self.out.plain()
        if not rec_path and not text.strip():
            return  # ne ses ne metin: listeye eklenecek bir şey yok
        take = Take(self.stem, rec_path or None, text, self.captured)
        try:
            take.write_text()
        except OSError:
            pass
        self.viewing = take
        self.takes.add(take)

    def _store_edits(self):
        """Transkript kartındaki düzenlemeleri gösterilen kayda geri yaz."""
        if self.viewing is not None and self.worker is None:
            self.takes.update_text(self.viewing, self.out.plain())

    def _show_take(self, take):
        if self.worker is not None or take is self.viewing:
            return  # kayıt sürerken canlı metin ekranda kalır
        self._store_edits()
        self.viewing = take
        self.out.clear()
        if take is not None:
            self.out.append(take.text)

    def _on_fail(self, msg):
        if self.mic:
            self.mic.stop()
            self.mic = None
        self._set_state("idle")
        QMessageBox.critical(self, tr("error_title"), msg)

    def _on_thread_end(self):
        self.worker = None
        self.ticker.stop()
        self.blink.stop()
        self.warn.hide()
        self.tab_status.emit("")
        if self._state not in ("done", "idle"):
            self._set_state("idle")
        self._set_running(False)

    def _set_state(self, state):
        self._state = state
        _, transcribe = self._mode()
        key = {"idle": "st_ready", "loading": "st_loading",
               "recording": "st_recording" if self._mode()[0] else "st_live",
               "paused": "st_paused", "finishing": "st_finishing",
               "done": "st_saved" if self._mode()[0] else "st_done"}[state]
        self.state_lbl.setText(tr(key))
        self.state_lbl.setProperty("on", "true" if state in ("recording", "loading") else "false")
        repolish(self.state_lbl)
        self.pause_btn.setVisible(state in ("recording", "paused", "loading"))
        self.refresh_icons()

    def _set_note(self, render):
        self._render_note = render
        text = render()
        self.note.setText(text)
        self.note.setVisible(bool(text))

    def _update_summary(self, *_):
        o = self.opts
        parts = [o.lang.currentText(), tr(QUALITY[o.quality.index][1]), tr(MODES[o.mode.index][0])]
        if self.preview.isChecked():
            parts.append(tr("preview_short"))
        self.tr_card.set_text(tr("sec_transcription"), "  ·  ".join(parts))

    def _set_running(self, running):
        self.rec_btn.setEnabled(running or bool(self._devices))
        for w in [self.rec_mode, self.mic_combo, self.refresh_btn, self.folder_change]:
            w.setEnabled(not running)
        self.tr_card.setEnabled(not running)
        self.refresh_icons()

    def stop_for_quit(self):
        if self.worker is not None:
            if self.mic:
                self.mic.stop()
            self.worker.stop()
            self.worker.wait(15000)  # son parça çevrilip kayıt dosyası kapatılsın
            QApplication.processEvents()  # bitiş sinyalleri işlensin: kayıt listeye girsin
        self._store_edits()

    def retranslate(self):
        self.level_title.setText(tr("k_level"))
        self.mic_title.setText(tr("sec_mic"))
        self.refresh_btn.setToolTip(tr("refresh_tip"))
        if not self._devices:
            self.mic_combo.setItemText(0, tr("no_mic"))
        self.mode_title.setText(tr("sec_rec_mode"))
        self.rec_mode.retranslate()
        self.folder_title.setText(tr("sec_folder"))
        self.folder_change.setText(tr("change_folder"))
        self.folder_open.setText(tr("open_folder"))
        self._show_folder()
        self.opts.retranslate()
        self.ts.setText(tr("timestamps"))
        self.preview.setText(tr("preview"))
        self.lag_title.setText(tr("k_lag"))
        self.warn.setText(tr("lag_warn"))
        self._set_note(self._render_note)
        self._update_summary()
        self._on_mode()
        self._set_state(self._state)
        self.takes.retranslate()

    def save_settings(self, st):
        self.opts.save(st, "live/")
        st.setValue("live/ts", self.ts.isChecked())
        st.setValue("live/preview", self.preview.isChecked())
        st.setValue("live/recmode", self.rec_mode.index)
        st.setValue("live/folder", str(self.folder))

    def load_settings(self, st):
        self.opts.load(st, "live/")
        self.ts.setChecked(st.value("live/ts", False, type=bool))
        self.preview.setChecked(st.value("live/preview", True, type=bool))
        try:
            m = int(st.value("live/recmode", 0))
        except (TypeError, ValueError):
            m = 0
        self.rec_mode.set_index(m if 0 <= m < len(REC_MODES) else 0)
        folder = st.value("live/folder", "")
        if folder:
            self.folder = Path(folder)
        self.retranslate()
