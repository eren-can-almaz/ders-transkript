#!/bin/sh
# Ders Transkript'i uygulama menüsüne ekler (yönetici izni gerekmez). Klasörü taşırsanız yeniden çalıştırın.
# Kaldırmak için: rm ~/.local/share/applications/ders-transkript.desktop
DIR="$(cd "$(dirname "$0")" && pwd)"
APPS="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
mkdir -p "$APPS"
cat > "$APPS/ders-transkript.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=Ders Transkript
Comment=Ders kayıtlarını internetsiz metne çevirir
Exec="$DIR/DersTranskript"
Icon=$DIR/icon.png
Terminal=false
Categories=Office;AudioVideo;
StartupWMClass=DersTranskript
DESKTOP
chmod +x "$APPS/ders-transkript.desktop" "$DIR/DersTranskript"
command -v update-desktop-database >/dev/null && update-desktop-database "$APPS" 2>/dev/null
echo "Eklendi: uygulama menüsünde \"Ders Transkript\" olarak görünür."
echo "Doğrudan çalıştırmak için: \"$DIR/DersTranskript\""
