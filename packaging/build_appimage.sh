#!/usr/bin/env bash
# Linux: wrap the PyInstaller folder (dist/SpaceChargeSimulator) into an AppImage.
# Usage (repository root, after pyinstaller):  bash packaging/build_appimage.sh [version]
# Downloads appimagetool (AppImage project, GitHub releases) into build/ the first time.
set -euo pipefail
VERSION="${1:-dev}"
APPDIR=build/AppDir
TOOL=build/appimagetool-x86_64.AppImage

rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/lib" dist
cp -r dist/SpaceChargeSimulator "$APPDIR/usr/lib/"
cp app/icon.png "$APPDIR/space-charge-simulator.png"
cat > "$APPDIR/space-charge-simulator.desktop" <<DESK
[Desktop Entry]
Type=Application
Name=Space-Charge Simulator
Comment=Impulse corona space charge in a rod-plane gap
Exec=SpaceChargeSimulator
Icon=space-charge-simulator
Categories=Science;Education;
Terminal=false
DESK
cat > "$APPDIR/AppRun" <<'RUN'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
exec "$HERE/usr/lib/SpaceChargeSimulator/SpaceChargeSimulator" "$@"
RUN
chmod +x "$APPDIR/AppRun"

if [ ! -x "$TOOL" ]; then
    curl -sSL -o "$TOOL" https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage
    chmod +x "$TOOL"
fi
# --appimage-extract-and-run: works without FUSE (CI machines)
ARCH=x86_64 "$TOOL" --appimage-extract-and-run "$APPDIR" "dist/SpaceChargeSimulator-${VERSION}-x86_64.AppImage"
echo "built dist/SpaceChargeSimulator-${VERSION}-x86_64.AppImage"
