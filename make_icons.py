"""assets/ altına uygulama ikonlarını üretir: icon.png, icon.ico (Windows), icon.icns (macOS).

ICO ve ICNS biçimleri PNG gömülü olarak yazılıyor; ek kütüphane gerekmez.
Çalıştırma: python make_icons.py
"""
import struct
import sys
from pathlib import Path

from PyQt6.QtCore import QBuffer, QIODevice
from PyQt6.QtGui import QGuiApplication

from theme import icon_pixmap

OUT = Path(__file__).resolve().parent / "assets"


def png_bytes(size):
    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    icon_pixmap(size).save(buf, "PNG")
    return bytes(buf.data())


def write_ico(path, sizes=(16, 24, 32, 48, 64, 128, 256)):
    images = [png_bytes(s) for s in sizes]
    header = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    entries, data = b"", b""
    for s, img in zip(sizes, images):
        dim = 0 if s >= 256 else s  # 0 = 256 piksel
        entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(img), offset + len(data))
        data += img
    path.write_bytes(header + entries + data)


def write_icns(path):
    chunks = b""
    for code, s in [(b"icp4", 16), (b"icp5", 32), (b"icp6", 64), (b"ic07", 128),
                    (b"ic08", 256), (b"ic09", 512), (b"ic10", 1024)]:
        img = png_bytes(s)
        chunks += code + struct.pack(">I", 8 + len(img)) + img
    path.write_bytes(b"icns" + struct.pack(">I", 8 + len(chunks)) + chunks)


if __name__ == "__main__":
    app = QGuiApplication(sys.argv)
    OUT.mkdir(exist_ok=True)
    (OUT / "icon.png").write_bytes(png_bytes(512))
    write_ico(OUT / "icon.ico")
    write_icns(OUT / "icon.icns")
    for f in sorted(OUT.iterdir()):
        print(f.name, f.stat().st_size, "bayt")
