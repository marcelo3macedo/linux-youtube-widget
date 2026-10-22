#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="$HOME/.local/bin"
APP_DIR="$HOME/.local/share/applications"
ICON_DIR="$HOME/.local/share/icons/hicolor/scalable/apps"
EXT_DIR="$HOME/.local/share/gnome-shell/extensions/youtube-widget@marcelo"

echo "=================================================="
echo "    Instalador do YouTube Widget para Linux      "
echo "=================================================="

# 1. Instalar Desktop Widget & Launcher
echo "[1/4] Instalando Desktop Widget (GTK4/Adwaita)..."
mkdir -p "$BIN_DIR" "$APP_DIR" "$ICON_DIR"

# Copiar ícone do aplicativo
cp "$SCRIPT_DIR/app/icons/youtube-widget.svg" "$ICON_DIR/youtube-widget.svg"

# Criar wrapper no ~/.local/bin
cat << 'EOF' > "$BIN_DIR/youtube-widget"
#!/usr/bin/env bash
APP_PATH="$(dirname "$(readlink -f "$0")")/../share/youtube-widget"
if [ ! -d "$APP_PATH" ]; then
    APP_PATH="/main/2_personal/plugins/youtube-widget/app"
fi
python3 "$APP_PATH/youtube_widget.py" "$@"
EOF
chmod +x "$BIN_DIR/youtube-widget"

# Criar cópia dos arquivos do app em ~/.local/share/youtube-widget
mkdir -p "$HOME/.local/share/youtube-widget"
cp -r "$SCRIPT_DIR/app/"* "$HOME/.local/share/youtube-widget/"
chmod +x "$HOME/.local/share/youtube-widget/youtube_widget.py"

# Atualizar arquivo .desktop
sed "s|/main/2_personal/plugins/youtube-widget/app/youtube_widget.py|$HOME/.local/share/youtube-widget/youtube_widget.py|g; s|/main/2_personal/plugins/youtube-widget/app/icons/youtube-widget.svg|youtube-widget|g" \
    "$SCRIPT_DIR/desktop/youtube-widget.desktop" > "$APP_DIR/youtube-widget.desktop"
chmod +x "$APP_DIR/youtube-widget.desktop"

# Atualizar banco de dados de aplicativos
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$APP_DIR" 2>/dev/null || true
fi

echo "[2/4] Instalando GNOME Shell Extension..."
mkdir -p "$EXT_DIR"
cp -r "$SCRIPT_DIR/gnome-extension/"* "$EXT_DIR/"

echo "[3/4] Ativando GNOME Shell Extension..."
if command -v gnome-extensions >/dev/null 2>&1; then
    gnome-extensions enable youtube-widget@marcelo 2>/dev/null || echo "Dica: Pode ser necessário reiniciar a sessão do GNOME (ou reiniciar o shell) para a extensão aparecer."
fi

echo "[4/4] Instalação concluída com sucesso!"
echo ""
echo "Como usar:"
echo " 1. Aplicativo Desktop (Mini-Widget):"
echo "    - Procure por 'YouTube Widget' no menu de aplicativos do Ubuntu/GNOME"
echo "    - Ou execute direto no terminal: youtube-widget"
echo ""
echo " 2. Extensão do Painel Superior (Top Bar):"
echo "    - Já foi instalada em $EXT_DIR"
echo "    - No Wayland, faça logout e login novamente para o GNOME carregar novas extensões"
echo "    - Depois ative no app 'Extensões' do GNOME ou com: gnome-extensions enable youtube-widget@marcelo"
echo "=================================================="
