"""Görünüm: açık/koyu tema renkleri, stil dosyası ve uygulama ikonu."""
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QGuiApplication

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
        "warn": "#b54708", "live": "#d92d20",
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
        "warn": "#fdb022", "live": "#f97066",
    },
}
_current_theme = "light"
THEME_CHOICES = [("theme_system", "system"), ("theme_light", "light"), ("theme_dark", "dark")]

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

QFrame#segbox[tabs="true"] QPushButton#seg {{ padding: 7px 18px; font-size: 13px; }}
QPushButton#toggle {{ padding: 6px 12px; color: {muted}; }}
QPushButton#toggle:checked {{ background: {accent_soft}; color: {accent}; border-color: {accent}; }}
QPushButton#icon {{ padding: 6px 10px; min-width: 0; }}
QProgressBar#meter {{ background: {track}; border-radius: 3px; }}
QProgressBar#meter::chunk {{ background: {ok}; border-radius: 3px; }}
QLabel#liveDot {{ color: {live}; font-size: 14px; font-weight: 700; }}
QLabel#warn {{ color: {warn}; font-size: 12px; font-weight: 600; }}
QComboBox#small {{ min-width: 90px; padding: 3px 26px 3px 8px; font-size: 12px; }}

QPushButton#recBtn {{
    background: {card}; border: 2px solid {border_strong}; border-radius: 32px;
    min-width: 64px; max-width: 64px; min-height: 64px; max-height: 64px; padding: 0;
}}
QPushButton#recBtn:hover {{ border-color: {live}; background: {hover}; }}
QPushButton#recBtn:disabled {{ background: {disabled_bg}; border-color: {border}; }}
QPushButton#roundBtn {{
    background: {card}; border: 1px solid {border_strong}; border-radius: 22px;
    min-width: 44px; max-width: 44px; min-height: 44px; max-height: 44px; padding: 0;
}}
QPushButton#roundBtn:hover {{ background: {hover}; }}
QLabel#timer {{ font-size: 30px; font-weight: 700; font-family: "SF Mono", "Cascadia Mono", Consolas, "DejaVu Sans Mono", monospace; }}
QLabel#recState {{ color: {muted}; font-size: 12px; font-weight: 700; letter-spacing: 0.8px; }}
QLabel#recState[on="true"] {{ color: {live}; }}
QLabel#path {{ color: {muted}; font-size: 12px; }}
QPushButton#collapse {{
    background: transparent; border: none; padding: 2px 0; text-align: left;
    color: {muted}; font-size: 12px; font-weight: 700;
}}
QPushButton#collapse:hover {{ color: {text}; background: transparent; }}
QScrollArea, QScrollArea > QWidget > QWidget {{ background: transparent; border: none; }}
QFrame#takeRow {{ background: transparent; border: 1px solid transparent; border-radius: 8px; }}
QFrame#takeRow:hover {{ background: {hover}; }}
QFrame#takeRow[selected="true"] {{ background: {accent_soft}; border-color: {accent}; }}
QLabel#takeTitle {{ font-weight: 600; }}
QPushButton#roundSmall {{
    background: {card}; border: 1px solid {border_strong}; border-radius: 15px;
    min-width: 30px; max-width: 30px; min-height: 30px; max-height: 30px; padding: 0;
}}
QPushButton#primarySmall {{ background: {accent}; color: {on_accent}; border: none; padding: 5px 12px; }}
QPushButton#primarySmall:hover {{ background: {accent_hover}; }}
QPushButton#dangerSmall {{ background: transparent; color: {danger}; border: 1px solid {danger_border}; padding: 5px 12px; }}
QPushButton#dangerSmall:hover {{ background: {danger_hover}; }}
QPushButton#link {{ background: transparent; border: none; color: {accent}; padding: 2px 4px; font-weight: 600; }}
QPushButton#link:hover {{ text-decoration: underline; background: transparent; }}
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

    global _current_theme
    theme = choice if choice in THEMES else ("dark" if system_is_dark() else "light")
    _current_theme = theme
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


def media_icon(kind, color, size=64):
    """Kayıt düğmesi simgeleri: 'record' (dolu daire), 'stop' (kare), 'pause' (iki çubuk), 'play' (üçgen)."""
    from PyQt6.QtCore import QPointF, QRectF
    from PyQt6.QtGui import QColor, QIcon, QPainter, QPixmap, QPolygonF

    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(color))
    u = size / 64
    if kind == "record":
        p.drawEllipse(QRectF(14 * u, 14 * u, 36 * u, 36 * u))
    elif kind == "stop":
        p.drawRoundedRect(QRectF(19 * u, 19 * u, 26 * u, 26 * u), 5 * u, 5 * u)
    elif kind == "pause":
        p.drawRoundedRect(QRectF(19 * u, 16 * u, 9 * u, 32 * u), 3 * u, 3 * u)
        p.drawRoundedRect(QRectF(36 * u, 16 * u, 9 * u, 32 * u), 3 * u, 3 * u)
    elif kind == "play":
        p.drawPolygon(QPolygonF([QPointF(22 * u, 15 * u), QPointF(50 * u, 32 * u), QPointF(22 * u, 49 * u)]))
    p.end()
    return QIcon(pm)


def current_colors():
    """Şu an uygulanan temanın renkleri (simgeleri temaya göre çizmek için)."""
    return THEMES[_current_theme]
