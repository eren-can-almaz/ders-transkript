@echo off
REM Windows bilgisayarda doğrudan derlemek için (Python 3.12 kurulu olmalı, models\ klasörü burada olmalı).
python -m venv .venv
call .venv\Scripts\activate
pip install -r requirements.txt
pyinstaller --noconfirm DersTranskript.spec
echo.
echo Hazir: dist\DersTranskript\DersTranskript.exe
pause
