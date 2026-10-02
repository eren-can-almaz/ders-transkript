# PyInstaller tanımı: `pyinstaller --noconfirm DersTranskript.spec`
# Windows çıktısı: dist/DersTranskript/DersTranskript.exe
# macOS çıktısı:   dist/DersTranskript.app
# models/ klasörü varsa pakete gömülür (macOS'ta imza bozulmasın diye sonradan eklenmemeli).
import os
import platform
import sys
from PyInstaller.utils.hooks import collect_all

datas, binaries, hiddenimports = [], [], []
for pkg in ("faster_whisper", "ctranslate2", "av", "onnxruntime", "tokenizers"):
    d, b, h = collect_all(pkg)
    datas += d; binaries += b; hiddenimports += h
if os.path.isdir("models"):
    datas.append(("models", "models"))
if sys.platform.startswith("linux"):  # Qt'nin xcb eklentisi bunu ister; çoğu dağıtımda varsayılan kurulu değil
    for lib in ("/usr/lib/x86_64-linux-gnu/libxcb-cursor.so.0",):
        if os.path.exists(lib):
            binaries.append((lib, "."))

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
            # av/onnxruntime tekerlekleri: Apple Silicon macOS 14+, Intel macOS 13+
            "LSMinimumSystemVersion": "14.0" if platform.machine() == "arm64" else "13.0",
            # Canlı dinleme için zorunlu: bu açıklama yoksa macOS mikrofon erişimini reddeder.
            "NSMicrophoneUsageDescription": "Canlı dinleme modunda konuşmayı metne çevirmek için mikrofon kullanılır. Ses bilgisayarınızdan dışarı gönderilmez.",
        },
    )
