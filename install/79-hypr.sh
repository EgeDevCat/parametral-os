#!/usr/bin/env bash
# 79-hypr — the Parametral session: Hyprland as the compositor, our bar, our palette.
#
# Why Hyprland as the primary session: the whole desktop is a text config plus an IPC socket
# (hyprctl), which is exactly what an AI-driven system needs to read, change and undo. KDE
# stays installed as the safe session.
set -eu

[ "${1:-}" = "--help" ] && { echo "usage: 79-hypr.sh"; exit 0; }

SRC="${SRC:-/opt/parametral-src}"

echo "==> Hyprland paketleri"
pacman -S --noconfirm --needed \
  hyprland swaybg hypridle hyprlock waybar fuzzel quickshell \
  xdg-desktop-portal-hyprland polkit-kde-agent

echo "==> Parametral oturum yapılandırması"
install -d /etc/parametral/hypr
install -m 0644 "$SRC/branding/hypr/parametral.conf"  /etc/parametral/hypr/parametral.conf
install -m 0644 "$SRC/branding/hypr/waybar.jsonc"     /etc/parametral/hypr/waybar.jsonc
install -m 0644 "$SRC/branding/hypr/waybar.css"       /etc/parametral/hypr/waybar.css
install -Dm 0755 "$SRC/branding/hypr/parametral-launcher" /usr/local/bin/parametral-launcher

echo "==> Parametral Shell (Quickshell/QML)"
install -d /usr/share/parametral/shell
install -m 0644 "$SRC/shell/shell.qml" /usr/share/parametral/shell/shell.qml

# The session user must be able to read the config: a 0700 /etc/parametral makes Hyprland
# start with "cannot open ...: Permission denied" and silently fall back to its defaults.
chmod 755 /etc/parametral /etc/parametral/hypr
chmod 644 /etc/parametral/hypr/* 2>/dev/null || true

echo "==> Oturum girdisi (SDDM'de görünür)"
install -d /usr/share/wayland-sessions
cat > /usr/share/wayland-sessions/parametral.desktop <<'EOF'
[Desktop Entry]
Name=Parametral
Comment=Hyprland ile Parametral OS oturumu
Exec=Hyprland --config /etc/parametral/hypr/parametral.conf
Type=Application
DesktopNames=Hyprland
EOF

echo "==> done"
echo "    SDDM'de 'Parametral' oturumunu seç, ya da: Hyprland --config /etc/parametral/hypr/parametral.conf"
