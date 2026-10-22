#!/usr/bin/env bash
set -e

echo "Removendo YouTube Widget..."
rm -f "$HOME/.local/bin/youtube-widget"
rm -f "$HOME/.local/share/applications/youtube-widget.desktop"
rm -rf "$HOME/.local/share/youtube-widget"
rm -f "$HOME/.local/share/icons/hicolor/scalable/apps/youtube-widget.svg"
rm -rf "$HOME/.local/share/gnome-shell/extensions/youtube-widget@marcelo"

if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true
fi

echo "YouTube Widget removido com sucesso."
