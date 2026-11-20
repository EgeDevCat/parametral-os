#!/usr/bin/env bash
# Parametral desktop session: Hyprland + UWSM + Noctalia.
#
# Noctalia (MIT, noctalia.dev) is the shell. We ship it, we theme it, we start it — we do not
# reimplement it. Our own Quickshell surfaces stay in the tree as experiments and are not started.

set -euo pipefail

SRC="${SRC:-/opt/parametral}"
PARAMETRAL_USER="${PARAMETRAL_USER:-}"

echo "==> Paketler: Noctalia ve yardımcıları"
pacman -S --needed --noconfirm \
    noctalia uwsm xdg-desktop-portal-hyprland wl-clipboard grim slurp \
    qt6ct adw-gtk-theme papirus-icon-theme ttf-ibm-plex inter-font >/dev/null

echo "==> Hyprland modülleri (tek dosya değil: variables/environment/monitors/inputs/appearance/binds/windowrules/workspaces/shell)"
install -d /etc/parametral/hypr
for module in variables environment monitors inputs appearance binds windowrules workspaces shell; do
    install -m 0644 "$SRC/branding/hypr/$module.lua" "/etc/parametral/hypr/$module.lua"
done
install -m 0644 "$SRC/branding/hypr/parametral.lua" /etc/parametral/hypr/parametral.lua
chmod 755 /etc/parametral /etc/parametral/hypr
chmod 644 /etc/parametral/hypr/*.lua

echo "==> Oturum başlatıcı (yazılım GL yalnız GPU'suz makinelerde)"
install -m 0755 "$SRC/branding/hypr/parametral-session" /usr/local/bin/parametral-session

echo "==> Oturum girdisi: uwsm start (CachyOS'un yaptığı gibi)"
install -d /usr/share/wayland-sessions
cat > /usr/share/wayland-sessions/parametral.desktop <<'EOF'
[Desktop Entry]
Name=Parametral
Comment=Hyprland ve Noctalia ile Parametral OS oturumu
Exec=/usr/local/bin/parametral-session
Type=Application
DesktopNames=Hyprland
EOF
chmod 644 /usr/share/wayland-sessions/parametral.desktop

echo "==> Noctalia yapılandırması ve Parametral paleti"
install_noctalia_config() {
    local home="$1"
    [ -d "$home" ] || return 0
    install -d "$home/.config/noctalia/palettes"
    install -m 0644 "$SRC/branding/noctalia/config.toml" "$home/.config/noctalia/config.toml"
    install -m 0644 "$SRC/branding/noctalia/palettes/Parametral.json" "$home/.config/noctalia/palettes/Parametral.json"
    chown -R "$(stat -c %U "$home"):$(stat -c %G "$home")" "$home/.config/noctalia" 2>/dev/null || true
}

install_noctalia_config /etc/skel
if [ -n "$PARAMETRAL_USER" ] && [ -d "/home/$PARAMETRAL_USER" ]; then
    install_noctalia_config "/home/$PARAMETRAL_USER"
fi

echo "==> Launcher mark (stock Noctalia logosu yerine bizim gauge)"
install -d /usr/share/icons/hicolor/scalable/apps
install -m 0644 "$SRC/branding/icons/parametral-start.svg" \
    /usr/share/icons/hicolor/scalable/apps/parametral-start.svg

echo "==> tr_TR.UTF-8 locale"
if ! locale -a | grep -qi '^tr_TR.utf8$'; then
    sed -i 's/^#\s*\(tr_TR.UTF-8 UTF-8\)/\1/' /etc/locale.gen 2>/dev/null || true
    grep -q '^tr_TR.UTF-8 UTF-8' /etc/locale.gen 2>/dev/null || echo 'tr_TR.UTF-8 UTF-8' >> /etc/locale.gen
    locale-gen
fi

echo "==> done"
