"""İki çalışma paneli: ses dosyası çevirme ve canlı dinleme. Birbirinden bağımsız çalışırlar."""
import math
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtMultimedia import QAudio, QAudioFormat, QAudioSource, QMediaDevices
from PyQt6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QGridLayout, QHBoxLayout, QLabel, QMessageBox,
    QProgressBar, QPushButton, QVBoxLayout, QWidget,
)

from core import (AUDIO_EXT, CHUNK_SEC, SR, FileWorker, LiveWorker, fmt_time, probe_audio,
                  recordings_dir)
from i18n import tr
from widgets import DropZone, SettingsBlock, StatCard, TranscriptCard, make_card, repolish

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


class LivePanel(QWidget):
    """Mikrofonu dinler ve konuşulanı birkaç saniye gecikmeyle yazar."""
    tab_status = pyqtSignal(str)
    LAG_WARN = 25.0  # sn; gecikme bunu aşarsa işlemcinin yetişemediği uyarısı

    def __init__(self):
        super().__init__()
        self.worker = None
        self.mic = None
        self.captured = 0.0
        self.processed = 0.0
        self.level = 0.0
        self._t_start = None
        self._state = "ready"           # ready | loading | listening | finishing | stopped
        self._stopped_after = 0.0
        self._render_note = lambda: ""
        self._devices = []

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(14)

        # ayarlar
        settings, s = make_card()
        mic_row = QGridLayout()
        mic_row.setHorizontalSpacing(8)
        mic_row.setVerticalSpacing(8)
        self.mic_title = QLabel(objectName="section")
        self.mic_combo = QComboBox()
        self.refresh_btn = QPushButton("↻", objectName="icon")
        self.refresh_btn.clicked.connect(self.refresh_devices)
        mic_row.addWidget(self.mic_title, 0, 0)
        mic_row.addWidget(self.mic_combo, 1, 0)
        mic_row.addWidget(self.refresh_btn, 1, 1)
        mic_row.setColumnStretch(0, 1)
        s.addLayout(mic_row)
        self.opts = SettingsBlock()
        s.addLayout(self.opts)
        row = QHBoxLayout()
        checks = QVBoxLayout()
        checks.setSpacing(6)
        self.ts = QCheckBox()
        self.keep = QCheckBox()
        self.keep.setChecked(True)
        checks.addWidget(self.ts)
        checks.addWidget(self.keep)
        row.addLayout(checks)
        row.addStretch()
        self.start_btn = QPushButton(objectName="primary")
        self.start_btn.setMinimumWidth(170)
        self.start_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.start_btn.clicked.connect(self.toggle)
        row.addWidget(self.start_btn, alignment=Qt.AlignmentFlag.AlignBottom)
        s.addLayout(row)
        lay.addWidget(settings)

        # durum
        status, st = make_card()
        top = QHBoxLayout()
        self.dot = QLabel("●", objectName="liveDot")
        self.dot.hide()
        self.state_lbl = QLabel(objectName="step")
        self.state_lbl.setWordWrap(True)
        top.addWidget(self.dot)
        top.addWidget(self.state_lbl, 1)
        st.addLayout(top)
        grid = QGridLayout()
        grid.setHorizontalSpacing(28)
        grid.setVerticalSpacing(2)
        self.k_titles = {}
        self.k_vals = {}
        for col, key in enumerate(["k_listen", "k_lag"]):
            t, v = QLabel(objectName="k"), QLabel("—", objectName="v")
            grid.addWidget(t, 0, col)
            grid.addWidget(v, 1, col)
            self.k_titles[key], self.k_vals[key] = t, v
        self.k_titles["k_level"] = QLabel(objectName="k")
        self.meter = QProgressBar(objectName="meter")
        self.meter.setTextVisible(False)
        self.meter.setFixedHeight(6)
        self.meter.setRange(0, 100)
        lv = QVBoxLayout()
        lv.setSpacing(6)
        lv.addWidget(self.k_titles["k_level"])
        lv.addWidget(self.meter)
        grid.addLayout(lv, 0, 2, 2, 1)
        grid.setColumnStretch(2, 1)
        st.addLayout(grid)
        self.warn = QLabel(objectName="warn")
        self.warn.setWordWrap(True)
        self.warn.hide()
        st.addWidget(self.warn)
        self.note = QLabel(objectName="hint")
        self.note.setWordWrap(True)
        st.addWidget(self.note)
        lay.addWidget(status)

        self.out = TranscriptCard("placeholder_live", "canli_transkript.txt")
        self.out.on_saved = lambda p: self._set_note(lambda: tr("saved", path=p))
        lay.addWidget(self.out, 1)

        self.ticker = QTimer(self)
        self.ticker.timeout.connect(self._tick)
        self.blink = QTimer(self)
        self.blink.timeout.connect(lambda: self.dot.setVisible(not self.dot.isVisible())
                                   if self._state == "listening" else None)
        self.media = QMediaDevices(self)
        self.media.audioInputsChanged.connect(self.refresh_devices)
        self.refresh_devices()
        self.retranslate()

    def busy(self):
        return self.worker is not None

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
            self.start_btn.setEnabled(bool(self._devices))

    # --- akış -----------------------------------------------------------
    def toggle(self):
        if self.worker is None:
            self._check_permission_then_start()
        else:
            self.stop()

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
        device = self._devices[self.mic_combo.currentIndex()]
        record_base = None
        stamp = datetime.now().strftime("%Y-%m-%d %H-%M")  # noktasız: uzantı sanılmasın
        self.base = recordings_dir() / f"{tr('tab_live')} {stamp}"
        if self.keep.isChecked():
            record_base = self.base
        w = self.worker = LiveWorker(self.opts.model_name(), self.opts.language(),
                                     self.ts.isChecked(), self.opts.threads(), record_base)
        w.ready.connect(lambda: self._set_state("listening"))
        w.segment.connect(self.out.append)
        w.processed.connect(self._on_processed)
        w.info.connect(lambda k, v: self._set_note(lambda: tr(k, v=v)))
        w.finished_ok.connect(self._on_done)
        w.failed.connect(self._on_fail)
        w.finished.connect(self._on_thread_end)
        self.out.clear()
        self.captured = self.processed = 0.0
        self._set_note(lambda: "")
        try:
            # mikrofon hemen açılır: model yüklenirken gelen ses kuyrukta bekler, kaybolmaz
            self.mic = Microphone(device, self._on_audio, self)
        except Exception as e:
            self.worker = None
            QMessageBox.critical(self, tr("error_title"), f"{tr('mic_error')}\n{e}")
            return
        self._t_start = time.time()
        self._set_state("loading")
        self._set_running(True)
        self.ticker.start(500)
        self.blink.start(700)
        w.start()

    def stop(self):
        if self.mic:
            self.mic.stop()
            self.mic = None
        self._stopped_after = self.captured
        self.meter.setValue(0)
        self._set_state("finishing")
        self.start_btn.setEnabled(False)
        self.worker.stop()

    def _on_audio(self, a):
        self.captured += len(a) / SR
        rms = float(np.sqrt((a ** 2).mean())) if len(a) else 0.0
        db = 20 * math.log10(rms + 1e-9)
        self.meter.setValue(int(max(0, min(100, (db + 60) / 60 * 100))))
        if self.worker:
            self.worker.feed(a)

    def _on_processed(self, sec):
        self.processed = sec

    def _tick(self):
        if self._state in ("loading", "listening"):
            self.k_vals["k_listen"].setText(fmt_time(self.captured))
            lag = max(0.0, self.captured - self.processed)
            self.k_vals["k_lag"].setText(tr("lag_fmt", s=f"{lag:.0f}") if self._state == "listening" else "—")
            self.warn.setVisible(lag > self.LAG_WARN)
            self.tab_status.emit(f"● {fmt_time(self.captured)}")

    def _on_done(self, rec_path):
        txt = self.out.plain()
        saved = []
        if txt.strip():
            try:
                self.base.parent.mkdir(parents=True, exist_ok=True)
                out = self.base.parent / (self.base.name + ".txt")
                out.write_text(txt, encoding="utf-8")
                saved.append(tr("autosaved", path=out))
            except OSError:
                pass
        if rec_path:
            saved.append(tr("recording_saved", path=rec_path))
        self._set_note(lambda: "\n".join(saved))
        self._set_state("stopped")

    def _on_fail(self, msg):
        if self.mic:
            self.mic.stop()
            self.mic = None
        self._set_state("ready")
        QMessageBox.critical(self, tr("error_title"), msg)

    def _on_thread_end(self):
        self.worker = None
        self.ticker.stop()
        self.blink.stop()
        self.dot.hide()
        self.warn.hide()
        self.tab_status.emit("")
        self._set_running(False)

    def _set_state(self, state):
        self._state = state
        self.dot.setVisible(state in ("listening", "loading"))
        texts = {
            "ready": lambda: tr("live_ready"),
            "loading": lambda: tr("live_loading"),
            "listening": lambda: tr("live_listening"),
            "finishing": lambda: tr("live_finishing"),
            "stopped": lambda: tr("live_stopped", t=fmt_time(self._stopped_after)),
        }
        if state == "stopped":
            self.k_vals["k_lag"].setText("—")
        self.state_lbl.setText(texts[state]())

    def _set_note(self, render):
        self._render_note = render
        self.note.setText(render())

    def _set_running(self, running):
        set_button(self.start_btn, "stop_live" if running else "start_live", running)
        self.start_btn.setEnabled(running or bool(self._devices))
        for w in self.opts.widgets() + [self.ts, self.keep, self.mic_combo, self.refresh_btn]:
            w.setEnabled(not running)

    def stop_for_quit(self):
        if self.worker is not None:
            if self.mic:
                self.mic.stop()
            self.worker.stop()
            self.worker.wait(15000)  # son parça çevrilip kayıt dosyası kapatılsın

    def retranslate(self):
        self.mic_title.setText(tr("sec_mic"))
        self.refresh_btn.setToolTip(tr("refresh_tip"))
        if not self._devices:
            self.mic_combo.setItemText(0, tr("no_mic"))
        self.opts.retranslate()
        self.ts.setText(tr("timestamps"))
        self.keep.setText(tr("save_recording"))
        set_button(self.start_btn, "stop_live" if self.busy() else "start_live", self.busy())
        for k, t in self.k_titles.items():
            t.setText(tr(k))
        self.warn.setText(tr("lag_warn"))
        self._set_state(self._state)
        self.note.setText(self._render_note())
        self.out.retranslate()

    def save_settings(self, st):
        self.opts.save(st, "live/")
        st.setValue("live/ts", self.ts.isChecked())
        st.setValue("live/keep", self.keep.isChecked())

    def load_settings(self, st):
        self.opts.load(st, "live/")
        self.ts.setChecked(st.value("live/ts", False, type=bool))
        self.keep.setChecked(st.value("live/keep", True, type=bool))
