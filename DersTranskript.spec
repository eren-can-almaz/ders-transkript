# PyInstaller tanımı: `pyinstaller --noconfirm DersTranskript.spec`
# Windows çıktısı: dist/DersTranskript/DersTranskript.exe
# macOS çıktısı:   dist/DersTranskript.app
# models/ klasörü varsa pakete gömülür (macOS'ta imza bozulmasın diye sonradan eklenmemeli).
import os
import sys
from PyInstaller.utils.hooks import collect_all

datas, binaries, hiddenimports = [], [], []
for pkg in ("faster_whisper", "ctranslate2", "av", "onnxruntime", "tokenizers"):
    d, b, h = collect_all(pkg)
    datas += d; binaries += b; hiddenimports += h
if os.path.isdir("models"):
    datas.append(("models", "models"))

a = Analysis(
    ["transkript.py"],
    datas=datas, binaries=binaries, hiddenimports=hiddenimports,
    excludes=["tkinter", "matplotlib", "scipy", "torch", "PyQt5", "PySide6"],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="DersTranskript",
          console=False, icon="assets/icon.ico" if sys.platform == "win32" else None)
coll = COLLECT(exe, a.binaries, a.datas, name="DersTranskript")

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="DersTranskript.app",
        bundle_identifier="com.derstranskript.app",
        icon="assets/icon.icns",
        info_plist={
            "CFBundleDisplayName": "Ders Transkript",
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "11.0",
        },
    )
