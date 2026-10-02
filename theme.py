"""Görünüm: Apple tarzı sade açık/koyu tema, stil dosyası ve çizilen simgeler."""
from pathlib import Path

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QGuiApplication, QIcon, QPainter, QPainterPath, QPen, QPixmap, QPolygonF

BRAND = "#0a7aff"  # uygulama ikonu rengi (temadan bağımsız)

THEMES = {
    "light": {
        "bg": "#ffffff", "side": "#f5f5f7", "fill": "#f2f2f5", "fill2": "#e7e7ec", "sep": "#e4e4e9",
        "text": "#1d1d1f", "muted": "#6e6e73", "faint": "#a1a1a6",
        "accent": "#007aff", "accent_hover": "#0068db", "accent_soft": "#e6f1ff", "on_accent": "#ffffff",
        "red": "#ff3b30", "red_soft": "#ffebe9", "green": "#34c759", "orange": "#ff9500",
        "selection": "#cfe3ff", "row_sel": "#e6e6eb", "disabled": "#c1c1c6", "scroll": "#d1d1d6",
        "ring": "#d9d9de", "shadow": "#00000018",
    },
    "dark": {
        "bg": "#1c1c1e", "side": "#242426", "fill": "#2c2c2e", "fill2": "#3a3a3c", "sep": "#38383a",
        "text": "#f5f5f7", "muted": "#a1a1a6", "faint": "#6e6e73",
        "accent": "#0a84ff", "accent_hover": "#3d9bff", "accent_soft": "#102a47", "on_accent": "#ffffff",
        "red": "#ff453a", "red_soft": "#3b1f1d", "green": "#30d158", "orange": "#ff9f0a",
        "selection": "#264f78", "row_sel": "#3a3a3c", "disabled": "#5a5a5e", "scroll": "#48484a",
        "ring": "#48484a", "shadow": "#00000060",
    },
}
_current_theme = "light"
THEME_CHOICES = [("theme_system", "system"), ("theme_light", "light"), ("theme_dark", "dark")]

STYLE = """
* {{ color: {text}; font-size: 14px; }}
QMainWindow, QWidget#content, QStackedWidget#detail {{ background: {bg}; }}
QDialog {{ background: {bg}; }}
QLabel {{ background: transparent; }}

/* kenar çubuğu */
QFrame#sidebar {{ background: {side}; border: none; border-right: 1px solid {sep}; }}
QLabel#appTitle {{ font-size: 20px; font-weight: 700; }}
QFrame#row {{ background: transparent; border-radius: 10px; }}
QFrame#row:hover {{ background: {fill}; }}
QFrame#row[selected="true"] {{ background: {row_sel}; }}
QLabel#rowTitle {{ font-size: 14px; font-weight: 600; }}
QLabel#rowMeta {{ font-size: 12px; color: {muted}; }}
QLabel#rowBadge {{ font-size: 12px; font-weight: 600; color: {muted}; }}
QLabel#rowBadge[kind="rec"] {{ color: {red}; }}
QLabel#rowBadge[kind="busy"] {{ color: {accent}; }}
QLabel#rowBadge[kind="unsaved"] {{ color: {orange}; }}

/* metin */
QLabel#h1 {{ font-size: 26px; font-weight: 700; }}
QLineEdit#titleEdit {{
    font-size: 26px; font-weight: 700; background: transparent; border: none;
    border-radius: 8px; padding: 2px 6px; margin-left: -6px; selection-background-color: {selection};
}}
QLineEdit#titleEdit:hover {{ background: {fill}; }}
QLineEdit#titleEdit:focus {{ background: {fill}; }}
QLabel#meta {{ color: {muted}; font-size: 13px; }}
QLabel#muted {{ color: {muted}; }}
QLabel#faint {{ color: {faint}; font-size: 12px; }}
QLabel#timer {{ font-size: 54px; font-weight: 300; }}
QLabel#status {{ color: {muted}; font-size: 13px; font-weight: 600; }}
QLabel#status[on="true"] {{ color: {red}; }}
QLabel#emptyTitle {{ font-size: 22px; font-weight: 700; }}
QLabel#sectionTitle {{ font-size: 15px; font-weight: 700; }}
QLabel#warn {{ color: {orange}; font-size: 12px; font-weight: 600; }}

/* düğmeler: dolgulu, renkli-açık (tinted), sade */
QPushButton {{
    background: {fill}; border: none; border-radius: 9px; padding: 8px 16px; font-weight: 600;
}}
QPushButton:hover {{ background: {fill2}; }}
QPushButton:disabled {{ color: {disabled}; background: {fill}; }}
QPushButton#primary {{ background: {accent}; color: {on_accent}; }}
QPushButton#primary:hover {{ background: {accent_hover}; }}
QPushButton#primary:disabled {{ background: {fill2}; color: {disabled}; }}
QPushButton#tinted {{ background: {accent_soft}; color: {accent}; }}
QPushButton#tinted:hover {{ background: {fill2}; }}
QPushButton#tinted[done="true"] {{ color: {green}; }}
QPushButton#destructive {{ background: {red_soft}; color: {red}; }}
QPushButton#destructive:hover {{ background: {fill2}; }}
QPushButton#plain {{ background: transparent; color: {accent}; padding: 6px 8px; }}
QPushButton#plain:hover {{ background: {fill}; }}
QPushButton#add {{
    background: {fill2}; border-radius: 15px; padding: 0; font-size: 20px; font-weight: 400;
    min-width: 30px; max-width: 30px; min-height: 30px; max-height: 30px; color: {text};
}}
QPushButton#add:hover {{ background: {accent}; color: {on_accent}; }}
QPushButton#add::menu-indicator {{ image: none; width: 0; }}
QPushButton#gear {{ background: transparent; color: {muted}; padding: 6px 10px; text-align: left; font-weight: 500; }}
QPushButton#gear:hover {{ background: {fill2}; color: {text}; }}
QPushButton#closePage {{
    background: transparent; color: {faint}; font-size: 22px; font-weight: 300; border-radius: 16px; padding: 0;
    min-width: 32px; max-width: 32px; min-height: 32px; max-height: 32px;
}}
QPushButton#closePage:hover {{ background: {fill}; color: {text}; }}
QPushButton#round {{
    background: {fill}; border-radius: 22px; padding: 0;
    min-width: 44px; max-width: 44px; min-height: 44px; max-height: 44px;
}}
QPushButton#round:hover {{ background: {fill2}; }}
QPushButton#play {{
    background: {accent}; border-radius: 20px; padding: 0;
    min-width: 40px; max-width: 40px; min-height: 40px; max-height: 40px;
}}
QPushButton#play:hover {{ background: {accent_hover}; }}
QPushButton#choice {{ background: {fill}; padding: 14px 18px; text-align: left; font-size: 15px; border-radius: 12px; }}
QPushButton#choice:hover {{ background: {accent_soft}; color: {accent}; }}

/* giriş alanları */
QComboBox {{
    background: {fill}; border: none; border-radius: 8px; padding: 6px 28px 6px 10px; min-width: 110px;
}}
QComboBox:hover {{ background: {fill2}; }}
QComboBox:disabled {{ color: {disabled}; }}
QComboBox::drop-down {{ border: none; width: 24px; }}
QComboBox::down-arrow {{ image: url({ARROW_PNG}); width: 10px; height: 10px; }}
QComboBox QAbstractItemView {{
    background: {bg}; border: 1px solid {sep}; border-radius: 8px; padding: 4px; outline: none;
    selection-background-color: {accent}; selection-color: {on_accent};
}}
QAbstractSpinBox {{
    background: {fill}; border: none; border-radius: 8px; padding: 5px 8px; min-width: 84px;
    selection-background-color: {selection};
}}
QAbstractSpinBox:hover {{ background: {fill2}; }}
QAbstractSpinBox::up-button, QAbstractSpinBox::down-button {{ width: 16px; border: none; background: transparent; }}
QAbstractSpinBox::up-arrow {{ image: url({UP_PNG}); width: 9px; height: 9px; }}
QAbstractSpinBox::down-arrow {{ image: url({ARROW_PNG}); width: 9px; height: 9px; }}
QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator {{ width: 18px; height: 18px; border-radius: 5px; border: 1.5px solid {disabled}; background: {bg}; }}
QCheckBox::indicator:checked {{ background: {accent}; border-color: {accent}; image: url({CHECK_PNG}); }}
QCheckBox#switch {{ spacing: 10px; font-weight: 500; }}
QCheckBox#switch::indicator {{ width: 42px; height: 26px; border: none; background: transparent; image: url({SWITCH_OFF}); }}
QCheckBox#switch::indicator:checked {{ image: url({SWITCH_ON}); }}

QProgressBar {{ background: {fill2}; border: none; border-radius: 2px; max-height: 4px; }}
QProgressBar::chunk {{ background: {accent}; border-radius: 2px; }}
QSlider::groove:horizontal {{ height: 4px; background: {fill2}; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {accent}; border-radius: 2px; }}
QSlider::handle:horizontal {{
    background: #ffffff; border: 1px solid {sep}; width: 14px; height: 14px; margin: -6px 0; border-radius: 7px;
}}

QFrame#box {{ background: {fill}; border-radius: 14px; }}
QFrame#sep {{ background: {sep}; border: none; max-height: 1px; min-height: 1px; }}
QPlainTextEdit {{
    background: transparent; border: none; font-size: 15px; selection-background-color: {selection};
}}
QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 8px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {scroll}; border-radius: 3px; min-height: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{ background: none; height: 0; }}
QMenu {{ background: {bg}; border: 1px solid {sep}; border-radius: 10px; padding: 6px; }}
QMenu::item {{ padding: 8px 20px 8px 12px; border-radius: 6px; }}
QMenu::item:selected {{ background: {accent}; color: {on_accent}; }}
QMenu::item:disabled {{ color: {disabled}; }}
QToolTip {{ background: {fill2}; color: {text}; border: none; padding: 4px 8px; }}
"""


def _make_assets(theme):
    """Stil dosyasının kullandığı küçük görseller (ok, onay işareti, anahtar)."""
    import tempfile

    c = THEMES[theme]
    d = Path(tempfile.gettempdir()) / "ders_transkript_ui"
    d.mkdir(exist_ok=True)

    def save(pm, name):
        path = d / f"{name}_{theme}.png"
        pm.save(str(path))
        return path.as_posix()

    def line(name, color, points, width):
        pm = QPixmap(20, 20)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(QColor(color), width, cap=Qt.PenCapStyle.RoundCap, join=Qt.PenJoinStyle.RoundJoin))
        p.drawPolyline(QPolygonF([QPointF(x, y) for x, y in points]))
        p.end()
        return save(pm, name)

    def switch(name, track, on):
        pm = QPixmap(84, 52)  # 2x: 42x26 gösterilir
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(track))
        p.drawRoundedRect(QRectF(0, 0, 84, 52), 26, 26)
        p.setBrush(QColor(0, 0, 0, 40))
        p.drawEllipse(QRectF((36 if on else 4), 5, 44, 44))
        p.setBrush(QColor("#ffffff"))
        p.drawEllipse(QRectF((36 if on else 4), 4, 44, 44))
        p.end()
        return save(pm, name)

    return {
        "ARROW_PNG": line("arrow", c["muted"], [(5, 8), (10, 13), (15, 8)], 2.2),
        "UP_PNG": line("up", c["muted"], [(5, 12), (10, 7), (15, 12)], 2.2),
        "CHECK_PNG": line("check", c["on_accent"], [(4.5, 10.5), (8.5, 14.5), (15.5, 6)], 2.6),
        "SWITCH_OFF": switch("switch_off", c["fill2"], False),
        "SWITCH_ON": switch("switch_on", c["green"], True),
    }


def system_is_dark():
    try:
        return QGuiApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark
    except Exception:
        return False


def apply_theme(app, choice):
    """choice: 'system' | 'light' | 'dark'. Stil dosyası + palet (diyaloglar için) uygulanır."""
    from PyQt6.QtGui import QPalette

    global _current_theme
    theme = choice if choice in THEMES else ("dark" if system_is_dark() else "light")
    _current_theme = theme
    c = THEMES[theme]
    pal = QPalette()
    for role, key in [(QPalette.ColorRole.Window, "bg"), (QPalette.ColorRole.Base, "bg"),
                      (QPalette.ColorRole.AlternateBase, "fill"), (QPalette.ColorRole.Button, "fill"),
                      (QPalette.ColorRole.Text, "text"), (QPalette.ColorRole.WindowText, "text"),
                      (QPalette.ColorRole.ButtonText, "text"), (QPalette.ColorRole.PlaceholderText, "faint"),
                      (QPalette.ColorRole.Highlight, "accent"), (QPalette.ColorRole.HighlightedText, "on_accent"),
                      (QPalette.ColorRole.ToolTipBase, "fill2"), (QPalette.ColorRole.ToolTipText, "text")]:
        pal.setColor(role, QColor(c[key]))
    app.setPalette(pal)
    app.setStyleSheet(STYLE.format(**c, **_make_assets(theme)))
    return theme


def colors():
    """Şu an uygulanan temanın renkleri (özel çizimler için)."""
    return THEMES[_current_theme]


def icon_pixmap(size=256):
    """Uygulama ikonu: mavi yuvarlak kare içinde ses dalgası (256 birimlik çizim ölçeklenir)."""
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
    return QIcon(icon_pixmap(256))


def glyph(kind, color, size=48):
    """Basit simgeler: record, stop, pause, play, mic (kayıt), wave (ses dosyası), doc, gear."""
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    u = size / 48
    col = QColor(color)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(col)
    if kind == "record":
        p.drawEllipse(QRectF(10 * u, 10 * u, 28 * u, 28 * u))
    elif kind == "stop":
        p.drawRoundedRect(QRectF(14 * u, 14 * u, 20 * u, 20 * u), 4 * u, 4 * u)
    elif kind == "pause":
        p.drawRoundedRect(QRectF(14 * u, 12 * u, 7 * u, 24 * u), 2.5 * u, 2.5 * u)
        p.drawRoundedRect(QRectF(27 * u, 12 * u, 7 * u, 24 * u), 2.5 * u, 2.5 * u)
    elif kind == "play":
        path = QPainterPath()
        path.moveTo(17 * u, 12 * u)
        path.lineTo(36 * u, 24 * u)
        path.lineTo(17 * u, 36 * u)
        path.closeSubpath()
        p.drawPath(path)
    elif kind == "mic":  # dolu kapsül + ayak (SF Symbols "mic.fill" benzeri)
        p.drawRoundedRect(QRectF(17 * u, 5 * u, 14 * u, 24 * u), 7 * u, 7 * u)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(col, 3 * u, cap=Qt.PenCapStyle.RoundCap))
        p.drawArc(QRectF(11 * u, 12 * u, 26 * u, 24 * u), 200 * 16, 140 * 16)
        p.drawLine(QPointF(24 * u, 36 * u), QPointF(24 * u, 42 * u))
        p.drawLine(QPointF(18 * u, 42.5 * u), QPointF(30 * u, 42.5 * u))
    elif kind == "wave":  # ses dosyası: dalga çubukları
        for i, h in enumerate([10, 20, 30, 18, 24, 12]):
            x = 8 * u + i * 5.6 * u
            p.drawRoundedRect(QRectF(x, 24 * u - h * u / 2, 3.4 * u, h * u), 1.7 * u, 1.7 * u)
    elif kind in ("doc", "gear"):
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(col, 3 * u, cap=Qt.PenCapStyle.RoundCap, join=Qt.PenJoinStyle.RoundJoin))
        if kind == "doc":
            p.drawRoundedRect(QRectF(12 * u, 7 * u, 24 * u, 34 * u), 4 * u, 4 * u)
            for y in (17, 24, 31):
                p.drawLine(QPointF(18 * u, y * u), QPointF(30 * u, y * u))
        else:
            p.drawEllipse(QRectF(17 * u, 17 * u, 14 * u, 14 * u))
            import math
            for k in range(8):
                a = k * math.pi / 4
                p.drawLine(QPointF(24 * u + 11 * u * math.cos(a), 24 * u + 11 * u * math.sin(a)),
                           QPointF(24 * u + 15 * u * math.cos(a), 24 * u + 15 * u * math.sin(a)))
    p.end()
    return QIcon(pm)
