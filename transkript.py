"""Ders Transkript — ses kaydını offline olarak metne çeviren sade masaüstü uygulaması.

faster-whisper (CPU, int8) + PyQt6. Modeller uygulamanın yanındaki `models/`
klasöründe tutulur; klasörde model varsa internet gerekmez.
"""
import os
import sys
import time
from pathlib import Path

from PyQt6.QtCore import QSettings, Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QFont, QGuiApplication
from PyQt6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel,
    QMainWindow, QMessageBox, QProgressBar, QPlainTextEdit, QPushButton,
    QVBoxLayout, QWidget,
)

AUDIO_EXT = {".mp3", ".m4a", ".wav", ".aac", ".ogg", ".opus", ".flac", ".wma",
             ".amr", ".3gp", ".mp4", ".webm", ".mkv", ".mov"}

QUALITY = [  # (görünen ad, faster-whisper modeli, açıklama)
    ("Standart", "small", "Daha hızlı biter; net, gürültüsüz kayıtlar için yeterli."),
    ("Yüksek", "large-v3-turbo", "Önerilen. Ders kayıtlarında belirgin şekilde daha az hata yapar."),
]
QUALITY_DEFAULT = 1

LANGUAGES = [("Otomatik algıla", None), ("Türkçe", "tr"), ("Deutsch", "de"), ("English", "en")]

PARAGRAPH_GAP = 2.0  # saniye; bu kadar sessizlikten sonra yeni paragraf
CHUNK_SEC = 30.0     # Whisper sesi 30 sn'lik parçalar halinde işler

_N_CPU = os.cpu_count() or 4
MODES = [  # (görünen ad, thread sayısı, açıklama)
    ("Sessiz", max(2, _N_CPU // 4),
     "İşlemcinin yaklaşık dörtte birini kullanır; bu sırada bilgisayarda rahatça başka iş yapılabilir."),
    ("Dengeli", max(3, _N_CPU // 2),
     "İşlemcinin yaklaşık yarısını kullanır; hız ile rahatlık arasında orta yol."),
    ("Hızlı", max(4, _N_CPU * 3 // 4),
     "İşlemcinin büyük kısmını kullanır; bu sürede bilgisayar yavaşlayabilir."),
]
STEPS = ["Model yükleniyor", "Ses dosyası okunuyor", "Metne çevriliyor"]


def lower_priority():
    """Süreci düşük öncelikle çalıştır: bilgisayarda başka iş yapılırken işlemci önce ona verilir."""
    try:
        if sys.platform == "win32":
            import ctypes
            BELOW_NORMAL_PRIORITY_CLASS = 0x4000
            k32 = ctypes.windll.kernel32
            k32.SetPriorityClass(k32.GetCurrentProcess(), BELOW_NORMAL_PRIORITY_CLASS)
        else:
            os.nice(10)
    except Exception:
        pass


def app_dir() -> Path:
    """Exe içinde çalışırken exe'nin klasörü, aksi halde betiğin klasörü."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def user_data_dir() -> Path:
    """İndirilen modeller için yazılabilir klasör (uygulama klasörü salt-okunur olabilir)."""
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "DersTranskript" / "models"


def model_path(name: str) -> Path:
    """Modeli olası konumlarda arar; bulunamazsa indirileceği yeri döndürür.

    Windows: exe'nin yanındaki models/  ·  macOS: DersTranskript.app/Contents/Resources/models/
    """
    candidates = [app_dir() / "models"]
    if getattr(sys, "frozen", False):
        candidates += [Path(getattr(sys, "_MEIPASS", app_dir())) / "models",
                       app_dir().parent / "Resources" / "models"]
    candidates.append(user_data_dir())
    for d in candidates:
        if (d / name / "model.bin").exists():
            return d / name
    return (user_data_dir() if getattr(sys, "frozen", False) else app_dir() / "models") / name


def decode_audio(path: str, sr: int = 16000):
    """Dosyayı 16 kHz mono float32 diziye çevirir (PyAV ile; harici ffmpeg gerekmez).

    faster-whisper'ın kendi decode_audio'su yeni PyAV sürümleriyle uyumsuz olduğu için
    çözme işlemi burada yapılıyor.
    """
    import av
    import numpy as np

    chunks = []
    resampler = av.AudioResampler(format="s16", layout="mono", rate=sr)
    with av.open(path) as container:
        stream = container.streams.audio[0]
        for frame in container.decode(stream):
            for f in resampler.resample(frame):
                chunks.append(f.to_ndarray().reshape(-1))
        for f in resampler.resample(None):
            chunks.append(f.to_ndarray().reshape(-1))
    if not chunks:
        raise ValueError("Dosyada ses bulunamadı.")
    return np.concatenate(chunks).astype(np.float32) / 32768.0


def fmt_time(sec: float) -> str:
    sec = int(sec)
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{h:d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


class TranscribeWorker(QThread):
    step = pyqtSignal(int)               # 0..len(STEPS)-1
    status = pyqtSignal(str)             # ek bilgi (algılanan dil, indirme vb.)
    progress = pyqtSignal(float, float)  # işlenen ses (sn), toplam ses (sn)
    segment = pyqtSignal(str)            # eklenecek metin parçası
    finished_ok = pyqtSignal(float)      # geçen süre
    failed = pyqtSignal(str)

    def __init__(self, audio_path, model_name, language, timestamps, threads):
        super().__init__()
        self.audio_path = audio_path
        self.model_name = model_name
        self.language = language
        self.timestamps = timestamps
        self.threads = threads
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def run(self):
        try:
            from faster_whisper import WhisperModel
            from faster_whisper.utils import download_model

            t0 = time.time()
            self.step.emit(0)
            mpath = model_path(self.model_name)
            if not (mpath / "model.bin").exists():
                self.status.emit("Model ilk kez indiriliyor (bir kerelik, internet gerekir)…")
                download_model(self.model_name, output_dir=str(mpath))
            model = WhisperModel(str(mpath), device="cpu", compute_type="int8",
                                 cpu_threads=self.threads)
            if self._cancel:
                return

            self.step.emit(1)
            audio = decode_audio(self.audio_path)
            if self._cancel:
                return

            self.step.emit(2)
            segments, info = model.transcribe(
                audio,
                language=self.language,
                beam_size=5,
                vad_filter=True,  # sessiz bölümleri atlar, hız + halüsinasyon azalır
                vad_parameters={"min_silence_duration_ms": 500},
            )
            duration = info.duration or 1.0
            self.progress.emit(0.0, duration)
            if not self.language:
                self.status.emit(f"Algılanan dil: {info.language}")

            last_end = None
            for seg in segments:
                if self._cancel:
                    return
                self.progress.emit(min(seg.end, duration), duration)
                text = seg.text.strip()
                if not text:
                    continue
                if self.timestamps:
                    piece = ("\n" if last_end is not None else "") + f"[{fmt_time(seg.start)}] {text}"
                elif last_end is None:
                    piece = text
                elif seg.start - last_end > PARAGRAPH_GAP:
                    piece = "\n\n" + text
                else:
                    piece = " " + text
                last_end = seg.end
                self.segment.emit(piece)

            self.progress.emit(duration, duration)
            self.finished_ok.emit(time.time() - t0)
        except Exception as e:  # kullanıcıya göster
            self.failed.emit(f"{type(e).__name__}: {e}")


# ---------------------------------------------------------------- görünüm
BRAND = "#3f51d8"  # ikon rengi (temadan bağımsız)

THEMES = {
    "light": {
        "bg": "#f4f5f8", "card": "#ffffff", "border": "#e3e6ec", "border_strong": "#cfd4dd",
        "text": "#121826", "muted": "#5f6878", "faint": "#8b93a3",
        "accent": "#3f51d8", "accent_hover": "#3443bd", "accent_soft": "#eef0fd",
        "accent_disabled": "#b6bdee", "on_accent": "#ffffff", "ok": "#12805c", "ok_soft": "#e7f6ef",
        "hover": "#f1f3f7", "seg_bg": "#eceef3", "track": "#e8eaf0",
        "scroll": "#d3d7df", "scroll_hover": "#b9bfca", "selection": "#cdd3fb",
        "disabled_bg": "#f7f8fa", "disabled_text": "#a9afbb",
        "danger": "#b42318", "danger_border": "#f1b8b2", "danger_hover": "#fef3f2",
    },
    "dark": {
        "bg": "#0f1217", "card": "#171b22", "border": "#262b35", "border_strong": "#353c49",
        "text": "#e8ebf1", "muted": "#a2aabb", "faint": "#7d8597",
        "accent": "#7183ff", "accent_hover": "#8494ff", "accent_soft": "#1e2443",
        "accent_disabled": "#353c6b", "on_accent": "#0b0e1a", "ok": "#41c98f", "ok_soft": "#11291f",
        "hover": "#1f242d", "seg_bg": "#0f1217", "track": "#262b35",
        "scroll": "#353c49", "scroll_hover": "#4a5262", "selection": "#34408c",
        "disabled_bg": "#14171d", "disabled_text": "#5c6475",
        "danger": "#ff8a80", "danger_border": "#5c2c2c", "danger_hover": "#2a1717",
    },
}
THEME_CHOICES = [("Sistem", "system"), ("Açık", "light"), ("Koyu", "dark")]

STYLE = """
* {{ font-size: 13px; color: {text}; }}
QMainWindow, QWidget#root {{ background: {bg}; }}
QLabel {{ background: transparent; }}
QLabel#title {{ font-size: 20px; font-weight: 700; }}
QLabel#subtitle, QLabel#muted {{ color: {muted}; }}
QLabel#badge {{
    color: {ok}; background: {ok_soft}; border-radius: 11px;
    padding: 3px 10px; font-size: 12px; font-weight: 600;
}}
QLabel#section {{ color: {faint}; font-size: 11px; font-weight: 700; letter-spacing: 0.6px; }}
QLabel#hint {{ color: {muted}; font-size: 12px; }}
QFrame#sep {{ background: {border}; border: none; }}

QFrame#card {{ background: {card}; border: 1px solid {border}; border-radius: 12px; }}
QFrame#drop {{ background: {card}; border: 1.5px dashed {border_strong}; border-radius: 12px; }}
QFrame#drop[hover="true"] {{ border-color: {accent}; background: {accent_soft}; }}
QLabel#fileName {{ font-size: 14px; font-weight: 600; }}

QPushButton {{
    background: {card}; border: 1px solid {border_strong}; border-radius: 8px;
    padding: 7px 14px; font-weight: 600;
}}
QPushButton:hover {{ background: {hover}; }}
QPushButton:disabled {{ color: {disabled_text}; border-color: {border}; background: {disabled_bg}; }}
QPushButton#primary {{ background: {accent}; color: {on_accent}; border: none; padding: 9px 22px; }}
QPushButton#primary:hover {{ background: {accent_hover}; }}
QPushButton#primary:disabled {{ background: {accent_disabled}; color: {on_accent}; }}
QPushButton#danger {{ background: {card}; color: {danger}; border: 1px solid {danger_border}; padding: 9px 22px; }}
QPushButton#danger:hover {{ background: {danger_hover}; }}
QPushButton#copy {{ background: {accent}; color: {on_accent}; border: none; }}
QPushButton#copy:hover {{ background: {accent_hover}; }}
QPushButton#copy:disabled {{ background: {accent_disabled}; color: {on_accent}; }}
QPushButton#copy[done="true"] {{ background: {ok}; }}

QFrame#segbox {{ background: {seg_bg}; border: 1px solid {border}; border-radius: 8px; }}
QPushButton#seg {{
    background: transparent; border: none; border-radius: 6px; padding: 6px 16px;
    color: {muted}; font-weight: 600;
}}
QPushButton#seg:hover {{ color: {text}; background: transparent; }}
QPushButton#seg:checked {{ background: {card}; color: {accent}; border: 1px solid {border_strong}; }}
QPushButton#seg:disabled {{ color: {disabled_text}; }}
QFrame#segbox[small="true"] QPushButton#seg {{ padding: 3px 10px; font-size: 12px; }}

QComboBox {{
    background: {card}; border: 1px solid {border_strong}; border-radius: 8px;
    padding: 6px 30px 6px 10px; min-width: 130px;
}}
QComboBox:disabled {{ color: {disabled_text}; }}
QComboBox::drop-down {{ border: none; width: 26px; }}
QComboBox::down-arrow {{ image: url({ARROW_PNG}); width: 10px; height: 10px; }}
QComboBox QAbstractItemView {{
    background: {card}; border: 1px solid {border}; selection-background-color: {accent_soft};
    selection-color: {text}; outline: none; padding: 4px;
}}
QCheckBox {{ spacing: 8px; color: {muted}; }}
QCheckBox::indicator {{ width: 16px; height: 16px; border: 1px solid {border_strong}; border-radius: 4px; background: {card}; }}
QCheckBox::indicator:checked {{ background: {accent}; border-color: {accent}; image: url({CHECK_PNG}); }}

QProgressBar {{ background: {track}; border: none; border-radius: 4px; }}
QProgressBar::chunk {{ background: {accent}; border-radius: 4px; }}
QLabel#step {{ font-size: 14px; font-weight: 600; }}
QLabel#pct {{ color: {accent}; font-size: 24px; font-weight: 700; }}
QLabel#k {{ color: {faint}; font-size: 11px; font-weight: 600; }}
QLabel#v {{ font-size: 14px; font-weight: 600; }}

QPlainTextEdit {{
    background: transparent; border: none; padding: 4px 6px;
    selection-background-color: {selection}; font-size: 14px;
}}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {scroll}; border-radius: 4px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {scroll_hover}; }}
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{ background: none; height: 0; }}
QMessageBox, QFileDialog, QDialog {{ background: {card}; }}
"""


def _make_assets(theme):
    """Stil dosyasının kullandığı küçük ikonları çizer (harici dosya gerekmesin diye)."""
    from PyQt6.QtGui import QColor, QPainter, QPen, QPixmap, QPolygonF
    from PyQt6.QtCore import QPointF
    import tempfile

    c = THEMES[theme]
    d = Path(tempfile.gettempdir()) / "ders_transkript_ui"
    d.mkdir(exist_ok=True)

    def draw(name, color, points, width):
        pm = QPixmap(20, 20)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(QColor(color), width, cap=Qt.PenCapStyle.RoundCap, join=Qt.PenJoinStyle.RoundJoin))
        p.drawPolyline(QPolygonF([QPointF(x, y) for x, y in points]))
        p.end()
        path = d / f"{name}_{theme}.png"
        pm.save(str(path))
        return path.as_posix()

    return {
        "ARROW_PNG": draw("arrow", c["muted"], [(4, 7), (10, 13), (16, 7)], 2.4),
        "CHECK_PNG": draw("check", c["on_accent"], [(4.5, 10.5), (8.5, 14.5), (15.5, 6)], 2.6),
    }


def system_is_dark():
    try:
        return QGuiApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark
    except Exception:
        return False


def apply_theme(app, choice):
    """choice: 'system' | 'light' | 'dark'. Stil dosyası + palet (diyaloglar için) uygulanır."""
    from PyQt6.QtGui import QColor, QPalette

    theme = choice if choice in THEMES else ("dark" if system_is_dark() else "light")
    c = THEMES[theme]
    pal = QPalette()
    for role, key in [(QPalette.ColorRole.Window, "bg"), (QPalette.ColorRole.Base, "card"),
                      (QPalette.ColorRole.AlternateBase, "hover"), (QPalette.ColorRole.Button, "card"),
                      (QPalette.ColorRole.Text, "text"), (QPalette.ColorRole.WindowText, "text"),
                      (QPalette.ColorRole.ButtonText, "text"), (QPalette.ColorRole.PlaceholderText, "faint"),
                      (QPalette.ColorRole.Highlight, "selection"), (QPalette.ColorRole.HighlightedText, "text"),
                      (QPalette.ColorRole.ToolTipBase, "card"), (QPalette.ColorRole.ToolTipText, "text")]:
        pal.setColor(role, QColor(c[key]))
    app.setPalette(pal)
    app.setStyleSheet(STYLE.format(**c, **_make_assets(theme)))
    return theme


def icon_pixmap(size=256):
    """Uygulama ikonu: lacivert yuvarlak kare içinde ses dalgası (256 birimlik çizim ölçeklenir)."""
    from PyQt6.QtGui import QColor, QPainter, QPixmap
    from PyQt6.QtCore import QRectF

    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.scale(size / 256, size / 256)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(BRAND))
    p.drawRoundedRect(QRectF(8, 8, 240, 240), 56, 56)
    p.setBrush(QColor("white"))
    for i, h in enumerate([60, 120, 170, 100, 140, 70]):
        x = 46 + i * 30
        p.drawRoundedRect(QRectF(x, 128 - h / 2, 16, h), 8, 8)
    p.end()
    return pm


def app_icon():
    from PyQt6.QtGui import QIcon
    return QIcon(icon_pixmap(256))


def probe_audio(path):
    """(süre sn veya None, boyut bayt) — dosya seçilince bilgi göstermek için."""
    size = os.path.getsize(path)
    try:
        import av
        with av.open(path) as c:
            dur = c.duration / 1_000_000 if c.duration else None
    except Exception:
        dur = None
    return dur, size


class Segmented(QFrame):
    """Yan yana seçilebilen düğmeler (iOS tarzı segment kontrol)."""
    changed = pyqtSignal(int)

    def __init__(self, items, default=0):
        super().__init__(objectName="segbox")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(3, 3, 3, 3)
        lay.setSpacing(2)
        self.items = items
        self.buttons = []
        for i, label in enumerate(items):
            b = QPushButton(label, objectName="seg")
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _=False, i=i: self.set_index(i))
            lay.addWidget(b)
            self.buttons.append(b)
        self.set_index(default)

    def set_index(self, i):
        for j, b in enumerate(self.buttons):
            b.setChecked(i == j)
        self.index = i
        self.changed.emit(i)


class DropZone(QFrame):
    fileDropped = pyqtSignal(str)

    def __init__(self):
        super().__init__(objectName="drop")
        self.setAcceptDrops(True)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(18, 14, 18, 14)
        lay.setSpacing(14)

        self.icon = QLabel()
        self.icon.setPixmap(app_icon().pixmap(40, 40))
        lay.addWidget(self.icon)

        texts = QVBoxLayout()
        texts.setSpacing(2)
        self.name = QLabel("Ses kaydını buraya sürükleyin", objectName="fileName")
        self.info = QLabel("veya dosya seçin  ·  MP3, M4A, WAV, OGG, OPUS ve video dosyaları",
                           objectName="muted")
        texts.addWidget(self.name)
        texts.addWidget(self.info)
        lay.addLayout(texts, 1)

        self.btn = QPushButton("Dosya seç")
        self.btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn.clicked.connect(self.choose)
        lay.addWidget(self.btn)

    def show_file(self, path, dur, size):
        self.name.setText(Path(path).name)
        parts = []
        if dur:
            m = int(dur // 60)
            parts.append(f"{m} dk {int(dur % 60)} sn" if m else f"{int(dur)} sn")
        parts.append(f"{size / 1_048_576:.1f} MB")
        self.info.setText("  ·  ".join(parts))
        self.btn.setText("Değiştir")

    def _set_hover(self, on):
        self.setProperty("hover", "true" if on else "false")
        self.style().unpolish(self)
        self.style().polish(self)

    def choose(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Ses dosyası seç", str(Path.home()),
            "Ses/Video (" + " ".join("*" + x for x in sorted(AUDIO_EXT)) + ");;Tüm dosyalar (*)")
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


def card():
    f = QFrame(objectName="card")
    lay = QVBoxLayout(f)
    lay.setContentsMargins(18, 16, 18, 16)
    lay.setSpacing(12)
    return f, lay


class ProgressCard(QFrame):
    """Adım, yüzde, işlenen ses, parça sayısı, geçen/kalan süre."""

    def __init__(self):
        super().__init__(objectName="card")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 14, 18, 14)
        lay.setSpacing(10)

        top = QHBoxLayout()
        self.step = QLabel("", objectName="step")
        self.pct = QLabel("", objectName="pct")
        top.addWidget(self.step)
        top.addStretch()
        top.addWidget(self.pct)
        lay.addLayout(top)

        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(8)
        lay.addWidget(self.bar)

        grid = QGridLayout()
        grid.setHorizontalSpacing(32)
        grid.setVerticalSpacing(2)
        self.vals = {}
        for col, (key, title) in enumerate([("audio", "İŞLENEN SES"), ("chunks", "PARÇA"),
                                            ("elapsed", "GEÇEN SÜRE"), ("eta", "KALAN SÜRE")]):
            grid.addWidget(QLabel(title, objectName="k"), 0, col)
            v = QLabel("—", objectName="v")
            grid.addWidget(v, 1, col)
            self.vals[key] = v
        grid.setColumnStretch(4, 1)
        lay.addLayout(grid)

        self.note = QLabel("", objectName="hint")
        lay.addWidget(self.note)

    def set(self, key, text):
        self.vals[key].setText(text)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Ders Transkript")
        self.setWindowIcon(app_icon())
        self.resize(920, 880)
        self.setMinimumSize(760, 640)
        self.audio_path = None
        self.worker = None
        self._t_start = None       # işin başladığı an
        self._t_start_tr = time.time()  # 3. adımın başladığı an
        self._t_upd = None         # son ilerleme güncellemesinin anı
        self._eta_at_upd = None    # o andaki kalan süre tahmini
        self._step = -1

        root = QWidget(objectName="root")
        self.setCentralWidget(root)
        lay = QVBoxLayout(root)
        lay.setContentsMargins(28, 22, 28, 22)
        lay.setSpacing(14)

        # başlık
        head = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(2)
        titles.addWidget(QLabel("Ders Transkript", objectName="title"))
        titles.addWidget(QLabel("Ders kayıtlarını metne çevirir.", objectName="subtitle"))
        head.addLayout(titles)
        head.addStretch()
        right = QVBoxLayout()
        right.setSpacing(8)
        right.addWidget(QLabel("●  İnternetsiz çalışır", objectName="badge"),
                        alignment=Qt.AlignmentFlag.AlignRight)
        self.theme = Segmented([t[0] for t in THEME_CHOICES], default=0)
        self.theme.setProperty("small", "true")
        right.addWidget(self.theme, alignment=Qt.AlignmentFlag.AlignRight)
        head.addLayout(right)
        lay.addLayout(head)

        # dosya
        self.drop = DropZone()
        self.drop.fileDropped.connect(self.set_file)
        lay.addWidget(self.drop)

        # ayarlar
        settings, s = card()
        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(12)

        grid.addWidget(QLabel("DİL", objectName="section"), 0, 0)
        self.lang = QComboBox()
        for name, code in LANGUAGES:
            self.lang.addItem(name, code)
        grid.addWidget(self.lang, 1, 0)

        grid.addWidget(QLabel("DOĞRULUK", objectName="section"), 0, 1)
        self.quality = Segmented([q[0] for q in QUALITY], default=QUALITY_DEFAULT)
        grid.addWidget(self.quality, 1, 1)

        grid.addWidget(QLabel("ÇALIŞMA MODU", objectName="section"), 0, 2)
        self.mode = Segmented([m[0] for m in MODES], default=0)
        grid.addWidget(self.mode, 1, 2)
        grid.setColumnStretch(3, 1)
        s.addLayout(grid)

        self.hint = QLabel("", objectName="hint")
        self.hint.setWordWrap(True)
        s.addWidget(self.hint)
        self.quality.changed.connect(self._update_hint)
        self.mode.changed.connect(self._update_hint)
        self._update_hint()

        row = QHBoxLayout()
        self.ts = QCheckBox("Zaman damgaları ekle  [12:34]")
        row.addWidget(self.ts)
        row.addStretch()
        self.start_btn = QPushButton("Transkripte çevir", objectName="primary")
        self.start_btn.setMinimumWidth(180)
        self.start_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.start_btn.setEnabled(False)
        self.start_btn.clicked.connect(self.start)
        row.addWidget(self.start_btn)
        s.addLayout(row)
        lay.addWidget(settings)

        # ilerleme
        self.card = ProgressCard()
        self.card.hide()
        lay.addWidget(self.card)

        # transkript
        tcard, t = card()
        t.setSpacing(8)
        bar = QHBoxLayout()
        bar.addWidget(QLabel("TRANSKRİPT", objectName="section"))
        self.words = QLabel("", objectName="hint")
        bar.addSpacing(6)
        bar.addWidget(self.words)
        bar.addStretch()
        self.save_btn = QPushButton("Kaydet (.txt)")
        self.save_btn.clicked.connect(self.save)
        bar.addWidget(self.save_btn)
        self.copy_btn = QPushButton("Tümünü kopyala", objectName="copy")
        self.copy_btn.setMinimumWidth(150)
        self.copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.copy_btn.clicked.connect(self.copy)
        bar.addWidget(self.copy_btn)
        t.addLayout(bar)
        line = QFrame(objectName="sep")
        line.setFixedHeight(1)
        t.addWidget(line)
        self.text = QPlainTextEdit()
        self.text.setPlaceholderText("Transkript burada görünecek. Çevrildikçe metin akarak eklenir.")
        self.text.textChanged.connect(self._update_buttons)
        t.addWidget(self.text, 1)
        lay.addWidget(tcard, 1)
        self._update_buttons()

        self.ticker = QTimer(self)  # geçen/kalan süreyi her saniye günceller
        self.ticker.timeout.connect(self._tick)

        # son kullanılan ayarları geri yükle
        self.settings = QSettings("DersTranskript", "DersTranskript")
        self.theme.set_index(self._load("theme", 0, len(THEME_CHOICES)))
        self.quality.set_index(self._load("quality", QUALITY_DEFAULT, len(QUALITY)))
        self.mode.set_index(self._load("mode", 0, len(MODES)))
        self.lang.setCurrentIndex(self._load("lang", 0, len(LANGUAGES)))
        self.theme.changed.connect(self._on_theme)
        try:  # "Sistem" seçiliyken işletim sistemi teması değişirse uygula
            QGuiApplication.styleHints().colorSchemeChanged.connect(lambda *_: self._on_theme())
        except AttributeError:
            pass

    def _load(self, key, default, n):
        try:
            v = int(self.settings.value(key, default))
        except (TypeError, ValueError):
            v = default
        return v if 0 <= v < n else default

    def _save_settings(self):
        for key, v in [("theme", self.theme.index), ("quality", self.quality.index),
                       ("mode", self.mode.index), ("lang", self.lang.currentIndex())]:
            self.settings.setValue(key, v)

    def _on_theme(self, *_):
        apply_theme(QApplication.instance(), THEME_CHOICES[self.theme.index][1])

    def _update_hint(self, *_):
        if not hasattr(self, "hint"):
            return
        q = QUALITY[self.quality.index]
        m = MODES[self.mode.index]
        self.hint.setText(f"<b>{q[0]}:</b> {q[2]}<br><b>{m[0]}:</b> {m[2]}")

    # --- akış -----------------------------------------------------------
    def set_file(self, path):
        if not path or not os.path.isfile(path):
            return
        if Path(path).suffix.lower() not in AUDIO_EXT:
            QMessageBox.warning(self, "Desteklenmeyen dosya",
                                "Bu bir ses dosyası gibi görünmüyor. Yine de denenecek.")
        self.audio_path = path
        self.drop.show_file(path, *probe_audio(path))
        self.start_btn.setEnabled(self.worker is None)

    def start(self):
        if self.worker is not None:  # iptal butonu olarak çalışıyor
            self.worker.cancel()
            self.start_btn.setEnabled(False)
            self.card.note.setText("İptal ediliyor… (o anki parça bitince durur)")
            return
        if not self.audio_path:
            return
        self.text.clear()
        c = self.card
        for k in c.vals:
            c.set(k, "—")
        c.note.setText("")
        c.pct.setText("")
        c.show()
        self._t_start = time.time()
        self._t_upd = self._eta_at_upd = None
        self.worker = TranscribeWorker(self.audio_path, QUALITY[self.quality.index][1],
                                       self.lang.currentData(), self.ts.isChecked(),
                                       MODES[self.mode.index][1])
        self.worker.step.connect(self.on_step)
        self.worker.status.connect(c.note.setText)
        self.worker.progress.connect(self.on_progress)
        self.worker.segment.connect(self.on_segment)
        self.worker.finished_ok.connect(self.on_done)
        self.worker.failed.connect(self.on_fail)
        self.worker.finished.connect(self.on_thread_end)
        self._set_running(True)
        self.ticker.start(1000)
        self.worker.start()

    def on_step(self, i):
        self._step = i
        self.card.step.setText(f"Adım {i + 1}/{len(STEPS)}  ·  {STEPS[i]}…")
        if i < 2:
            self.card.bar.setRange(0, 0)  # süresi belirsiz adım: kayan çubuk
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
        self.setWindowTitle(f"%{pct} — Ders Transkript")
        n_total = max(1, int(-(-total // CHUNK_SEC)))
        n_done = n_total if done >= total else min(n_total - 1, int(done // CHUNK_SEC))
        self.card.set("audio", f"{fmt_time(done)} / {fmt_time(total)}")
        self.card.set("chunks", f"{n_done} / {n_total}  ({n_total - n_done} kaldı)")
        elapsed = time.time() - self._t_start_tr
        if frac > 0.03 and elapsed > 5:
            self._eta_at_upd = elapsed / frac - elapsed
            self._t_upd = time.time()
        self._tick()

    def _tick(self):
        if self._t_start is None:
            return
        self.card.set("elapsed", fmt_time(time.time() - self._t_start))
        if self._eta_at_upd is None:
            self.card.set("eta", "hesaplanıyor…" if self._step == 2 else "—")
        else:
            left = max(0.0, self._eta_at_upd - (time.time() - self._t_upd))
            self.card.set("eta", f"~{fmt_time(left)}")

    def on_segment(self, piece):
        sb = self.text.verticalScrollBar()
        at_bottom = sb.value() >= sb.maximum() - 4  # kullanıcı yukarı kaydırdıysa zıplatma
        cur = self.text.textCursor()
        cur.movePosition(cur.MoveOperation.End)
        cur.insertText(piece)
        if at_bottom:
            sb.setValue(sb.maximum())

    def on_done(self, elapsed):
        c = self.card
        c.bar.setRange(0, 1000)
        c.bar.setValue(1000)
        c.pct.setText("%100")
        c.step.setText(f"✓  Tamamlandı  ·  {fmt_time(elapsed)} sürdü")
        c.set("eta", "00:00")
        self.setWindowTitle("✓ Bitti — Ders Transkript")
        out = Path(self.audio_path).with_suffix(".txt")
        try:
            out.write_text(self.text.toPlainText(), encoding="utf-8")
            c.note.setText(f"Otomatik kaydedildi: {out}")
        except OSError:
            pass
        QApplication.alert(self)  # görev çubuğunda simgeyi yakıp söndür

    def on_fail(self, msg):
        self.card.step.setText("Hata oluştu.")
        QMessageBox.critical(self, "Hata", msg)

    def on_thread_end(self):
        cancelled = self.worker._cancel
        self.worker = None
        self.ticker.stop()
        self._t_start = None
        if cancelled:
            self.card.step.setText("İptal edildi.")
            self.card.note.setText("")
            self.card.bar.setRange(0, 1000)
            self.setWindowTitle("Ders Transkript")
        self._set_running(False)

    def _set_running(self, running):
        self.start_btn.setText("İptal et" if running else "Transkripte çevir")
        self.start_btn.setObjectName("danger" if running else "primary")
        self.start_btn.style().unpolish(self.start_btn)
        self.start_btn.style().polish(self.start_btn)
        self.start_btn.setEnabled(running or self.audio_path is not None)
        for w in (self.lang, self.quality, self.mode, self.ts, self.drop):
            w.setEnabled(not running)

    # --- çıktı ----------------------------------------------------------
    def _update_buttons(self):
        txt = self.text.toPlainText()
        has = bool(txt.strip())
        self.copy_btn.setEnabled(has)
        self.save_btn.setEnabled(has)
        self.words.setText(f"·  {len(txt.split())} kelime" if has else "")

    def _set_copy_done(self, done):
        self.copy_btn.setText("✓  Kopyalandı" if done else "Tümünü kopyala")
        self.copy_btn.setProperty("done", "true" if done else "false")
        self.copy_btn.style().unpolish(self.copy_btn)
        self.copy_btn.style().polish(self.copy_btn)

    def copy(self):
        QGuiApplication.clipboard().setText(self.text.toPlainText())
        self._set_copy_done(True)
        QTimer.singleShot(1800, lambda: self._set_copy_done(False))

    def save(self):
        default = str(Path(self.audio_path).with_suffix(".txt")) if self.audio_path else "transkript.txt"
        path, _ = QFileDialog.getSaveFileName(self, "Kaydet", default, "Metin (*.txt)")
        if path:
            Path(path).write_text(self.text.toPlainText(), encoding="utf-8")
            self.card.note.setText(f"Kaydedildi: {path}")

    def closeEvent(self, e):
        if self.worker is not None:
            if QMessageBox.question(self, "Çıkış", "Transkript devam ediyor. Çıkılsın mı?") \
                    != QMessageBox.StandardButton.Yes:
                e.ignore()
                return
            self.worker.cancel()
            self.worker.wait(3000)
        self._save_settings()
        e.accept()


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
    for _, name, _ in QUALITY:
        path = model_path(name)
        print(f"model {name}: {path} -> {'VAR' if (path / 'model.bin').exists() else 'YOK'}", flush=True)
    path = model_path("small")
    model = WhisperModel(str(path), device="cpu", compute_type="int8", cpu_threads=MODES[0][1])
    data = decode_audio(audio)[: 16000 * 30]
    segs, info = model.transcribe(data, beam_size=1, vad_filter=True)
    text = " ".join(s.text.strip() for s in segs)
    print(f"ses {len(data) / 16000:.1f} sn, dil {info.language}: {text[:200]!r}", flush=True)
    print("SELFTEST OK", flush=True)


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
