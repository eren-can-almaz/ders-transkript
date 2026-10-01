"""Bu oturumun kayıtları: durdurulan her kayıt geçici olarak listelenir; Kaydet ile kalıcı bir
yere taşınır, Sil ile tamamen silinir.

Geçici dosyalar kullanıcı veri klasöründeki `unsaved/` altında durur; program çökerse bir
sonraki açılışta liste bu klasörden geri yüklenir.
"""
import shutil
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import QSize, Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
from PyQt6.QtWidgets import (
    QFileDialog, QFrame, QHBoxLayout, QLabel, QMessageBox, QPushButton, QScrollArea,
    QVBoxLayout, QWidget,
)

from core import fmt_time, probe_audio, user_data_dir
from i18n import tr
from theme import current_colors, media_icon
from widgets import repolish

AUDIO_SUFFIXES = (".m4a", ".wav")


def unsaved_dir() -> Path:
    d = user_data_dir() / "unsaved"
    d.mkdir(parents=True, exist_ok=True)
    return d


class Take:
    """Bir kayıt: ses dosyası (yoksa None) + transkript. `saved_to` doluysa kalıcı kaydedilmiş."""

    def __init__(self, stem, audio=None, text="", duration=None, created=None):
        self.stem = stem                  # geçici dosya adı (uzantısız)
        self.audio = Path(audio) if audio else None
        self.text = text
        self.duration = duration
        self.created = created or datetime.now()
        self.saved_to = None              # kaydedildiyse ses/metin dosyasının yeni yolu

    @property
    def txt_path(self):
        return unsaved_dir() / (self.stem + ".txt")

    def write_text(self):
        if self.saved_to is None and self.text.strip():
            self.txt_path.write_text(self.text, encoding="utf-8")

    def delete_files(self):
        for p in (self.audio, self.txt_path):
            if p and p.exists() and self.saved_to is None:
                p.unlink()

    @staticmethod
    def recover():
        """Önceki oturumdan kalan (kaydedilmemiş) kayıtları geri yükler."""
        d = unsaved_dir()
        stems = sorted({p.stem for p in d.iterdir() if p.suffix in AUDIO_SUFFIXES + (".txt",)})
        takes = []
        for stem in stems:
            audio = next((d / (stem + s) for s in AUDIO_SUFFIXES if (d / (stem + s)).exists()), None)
            txt = d / (stem + ".txt")
            text = txt.read_text(encoding="utf-8") if txt.exists() else ""
            dur = probe_audio(str(audio))[0] if audio else None
            src = audio or txt
            created = datetime.fromtimestamp(src.stat().st_mtime)
            takes.append(Take(stem, audio, text, dur, created))
        return takes


class TakeRow(QFrame):
    """Listede bir satır: ▶  başlık · süre / transkript önizlemesi   [Kaydet] [Sil]."""
    clicked = pyqtSignal(object)
    play = pyqtSignal(object)
    save = pyqtSignal(object)
    delete = pyqtSignal(object)
    transcribe = pyqtSignal(object)
    reveal = pyqtSignal(object)

    def __init__(self, take):
        super().__init__(objectName="takeRow")
        self.take = take
        self.playing = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(10)
        self.play_btn = QPushButton(objectName="roundSmall")
        self.play_btn.setIconSize(QSize(16, 16))
        self.play_btn.clicked.connect(lambda: self.play.emit(self.take))
        self.play_btn.setVisible(take.audio is not None)
        lay.addWidget(self.play_btn)
        texts = QVBoxLayout()
        texts.setSpacing(1)
        self.title = QLabel(objectName="takeTitle")
        self.preview = QLabel(objectName="hint")
        texts.addWidget(self.title)
        texts.addWidget(self.preview)
        lay.addLayout(texts, 1)
        self.transcribe_btn = QPushButton(objectName="link")
        self.transcribe_btn.clicked.connect(lambda: self.transcribe.emit(self.take))
        self.save_btn = QPushButton(objectName="primarySmall")
        self.save_btn.clicked.connect(lambda: self.save.emit(self.take))
        self.del_btn = QPushButton(objectName="dangerSmall")
        self.del_btn.clicked.connect(lambda: self.delete.emit(self.take))
        self.reveal_btn = QPushButton(objectName="link")
        self.reveal_btn.clicked.connect(lambda: self.reveal.emit(self.take))
        for b in (self.transcribe_btn, self.reveal_btn, self.save_btn, self.del_btn):
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            lay.addWidget(b)
        self.refresh()

    def mousePressEvent(self, e):
        self.clicked.emit(self.take)

    def set_selected(self, on):
        self.setProperty("selected", "true" if on else "false")
        repolish(self)

    def refresh(self):
        t = self.take
        when = t.created.strftime("%H:%M")
        dur = f"  ·  {fmt_time(t.duration)}" if t.duration else ""
        name = t.saved_to.stem if t.saved_to else f"{tr('rec_prefix')} {when}"
        self.title.setText(f"{'✓  ' if t.saved_to else ''}{name}{dur}")
        first = " ".join(t.text.split())
        if not first:
            first = tr("take_no_text") if t.audio else ""
        self.preview.setText(self.preview.fontMetrics().elidedText(first, Qt.TextElideMode.ElideRight, 420))
        saved = t.saved_to is not None
        self.save_btn.setVisible(not saved)
        self.del_btn.setText(tr("take_remove") if saved else tr("take_delete"))
        self.save_btn.setText(tr("take_save"))
        self.reveal_btn.setText(tr("show_in_folder"))
        self.reveal_btn.setVisible(saved)
        self.transcribe_btn.setText(tr("transcribe_this"))
        self.transcribe_btn.setVisible(t.audio is not None)
        self.play_btn.setToolTip(tr("take_play"))
        c = current_colors()
        self.play_btn.setIcon(media_icon("pause" if self.playing else "play", c["text"]))


class TakesCard(QFrame):
    """Oturum kayıtları listesi + ortak oynatıcı."""
    selected = pyqtSignal(object)        # transkripti göstermek için
    transcribe = pyqtSignal(str)         # ses dosyasını dosya panelinde yazıya dök

    def __init__(self, folder_getter):
        super().__init__(objectName="card")
        self.folder_getter = folder_getter
        self.takes = []
        self.rows = {}
        self.current = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 14, 18, 14)
        lay.setSpacing(8)
        head = QHBoxLayout()
        self.title = QLabel(objectName="section")
        self.hint = QLabel(objectName="hint")
        head.addWidget(self.title)
        head.addSpacing(6)
        head.addWidget(self.hint, 1)
        lay.addLayout(head)
        self.area = QScrollArea()
        self.area.setWidgetResizable(True)
        self.area.setFrameShape(QScrollArea.Shape.NoFrame)
        self.area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        inner = QWidget()
        self.list = QVBoxLayout(inner)
        self.list.setContentsMargins(0, 0, 0, 0)
        self.list.setSpacing(4)
        self.list.addStretch()
        self.area.setWidget(inner)
        lay.addWidget(self.area)
        self.player = QMediaPlayer(self)
        self.audio_out = QAudioOutput(self)
        self.player.setAudioOutput(self.audio_out)
        self.player.playbackStateChanged.connect(self._on_playback)
        self._playing = None
        for t in Take.recover():
            self.add(t, select=False)
        self.retranslate()

    # --- liste ----------------------------------------------------------
    def add(self, take, select=True):
        row = TakeRow(take)
        row.clicked.connect(self.select)
        row.play.connect(self.toggle_play)
        row.save.connect(self.save_take)
        row.delete.connect(self.delete_take)
        row.transcribe.connect(lambda t: self.transcribe.emit(str(t.audio)))
        row.reveal.connect(lambda t: QDesktopServices.openUrl(QUrl.fromLocalFile(str(t.saved_to.parent))))
        self.takes.insert(0, take)
        self.rows[id(take)] = row
        self.list.insertWidget(0, row)  # en yeni üstte
        self._update()
        if select:
            self.select(take)

    def select(self, take):
        self.current = take
        for t in self.takes:
            self.rows[id(t)].set_selected(t is take)
        self.selected.emit(take)

    def unsaved(self):
        return [t for t in self.takes if t.saved_to is None]

    def _update(self):
        n = len(self.takes)
        self.setVisible(n > 0)
        self.area.setFixedHeight(min(n, 3) * 58 + 4)  # 3 satır görünür, fazlası kaydırılır
        k = len(self.unsaved())
        self.hint.setText(tr("takes_unsaved", n=k) if k else "")

    def update_text(self, take, text):
        """Transkript kartında düzenlenen metni kayda geri yaz."""
        if take.text != text:
            take.text = text
            take.write_text()
            self.rows[id(take)].refresh()

    # --- eylemler -------------------------------------------------------
    def save_take(self, take):
        folder = Path(self.folder_getter())
        folder.mkdir(parents=True, exist_ok=True)
        suffix = take.audio.suffix if take.audio else ".txt"
        default = folder / f"{tr('rec_prefix')} {take.created.strftime('%Y-%m-%d %H-%M')}{suffix}"
        flt = f"{tr('filter_audio')} (*{suffix})" if take.audio else f"{tr('filter_text')} (*.txt)"
        path, _ = QFileDialog.getSaveFileName(self, tr("take_save"), str(default), flt)
        if not path:
            return
        dest = Path(path)
        if dest.suffix.lower() != suffix:
            dest = dest.with_name(dest.name + suffix)
        if self._playing is take:
            self.player.stop()
        if take.audio:
            shutil.move(str(take.audio), dest)
            if take.text.strip():
                dest.with_suffix(".txt").write_text(take.text, encoding="utf-8")
            if take.txt_path.exists():
                take.txt_path.unlink()
            take.audio = dest
        else:
            dest.write_text(take.text, encoding="utf-8")
            if take.txt_path.exists():
                take.txt_path.unlink()
        take.saved_to = dest
        self.rows[id(take)].refresh()
        self._update()

    def delete_take(self, take):
        if take.saved_to is None:
            ans = QMessageBox.question(self, tr("take_delete"), tr("take_delete_q"),
                                       QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                       QMessageBox.StandardButton.No)
            if ans != QMessageBox.StandardButton.Yes:
                return
        if self._playing is take:
            self.player.stop()
            self.player.setSource(QUrl())
        take.delete_files()
        row = self.rows.pop(id(take))
        self.takes.remove(take)
        row.setParent(None)
        row.deleteLater()
        if self.current is take:
            self.current = None
            self.selected.emit(None)
        self._update()

    def delete_all_unsaved(self):
        self.player.stop()
        self.player.setSource(QUrl())
        for t in self.unsaved():
            t.delete_files()

    def toggle_play(self, take):
        if self._playing is take and self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
            return
        if self._playing is not take:
            self.player.setSource(QUrl.fromLocalFile(str(take.audio)))
            self._playing = take
        self.player.play()

    def _on_playback(self, state):
        for t in self.takes:
            row = self.rows[id(t)]
            row.playing = t is self._playing and state == QMediaPlayer.PlaybackState.PlayingState
            row.refresh()

    def refresh_icons(self):
        for row in self.rows.values():
            row.refresh()

    def retranslate(self):
        self.title.setText(tr("takes_title"))
        for row in self.rows.values():
            row.refresh()
        self._update()
