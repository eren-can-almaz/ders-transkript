#!/bin/bash
# Mac'te doğrudan derlemek için (Python 3.12 kurulu olmalı, models/ klasörü burada olmalı).
set -e
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pyinstaller --noconfirm DersTranskript.spec
codesign --force --deep --sign - dist/DersTranskript.app
echo "Hazır: dist/DersTranskript.app  (Uygulamalar klasörüne sürükleyin)"
