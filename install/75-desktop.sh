#!/usr/bin/env bash
# 75-desktop.sh — the desktop identity: wallpaper, KDE palette, Dolphin, splash assets.
# Run inside the installed system (arch-chroot) after 40-users.sh; needs no network.
set -Eeuo pipefail
[ "$(id -u)" -eq 0 ] || { echo "run as root" >&2; exit 1; }
SRC="$(cd "$(dirname "$0")/.." && pwd)"

echo "==> wallpapers"
install -d /usr/share/wallpapers/Parametral/contents/images
install -m 0644 "$SRC/branding/wallpapers/parametral-dark.png" \
  /usr/share/wallpapers/Parametral/contents/images/2560x1440.png
install -m 0644 "$SRC/branding/wallpapers/parametral-light.png" \
  /usr/share/wallpapers/Parametral/contents/images/2560x1440-light.png
cat > /usr/share/wallpapers/Parametral/metadata.json <<'EOF'
{"KPlugin": {"Id": "Parametral", "Name": "Parametral"}, "X-KDE-PluginInfo-Name": "Parametral"}
EOF

echo "==> KDE colour scheme"
install -d /usr/share/color-schemes
install -m 0644 "$SRC/branding/kde/Parametral.colors" /usr/share/color-schemes/Parametral.colors

echo "==> per-user defaults (applied to every human account that exists)"
for home in /home/*; do
  [ -d "$home" ] || continue
  user="$(basename "$home")"
  [ "$user" = "lost+found" ] && continue
  id "$user" >/dev/null 2>&1 || continue

  cfg="$home/.config"
  install -d -o "$user" -g "$user" -m 0700 "$cfg"

  # palette: append the [Colors:*] groups (KConfig lets the last section win)
  touch "$cfg/kdeglobals"
  if ! grep -q '^ColorScheme=Parametral' "$cfg/kdeglobals"; then
    cat "$SRC/branding/kde/kdeglobals-snippet.ini" >> "$cfg/kdeglobals"
  fi

  # Dolphin: compact, readable, follows the system palette
  cat > "$cfg/dolphinrc" <<'EOF'
[DetailsMode]
PreviewSize=32

[General]
Version=203
ViewPropsTimestamp=2026,11,19,20,0,0

[MainWindow]
MenuBar=Disabled

[KDE]
SingleClickOpens=false

[CompactMode]
FontSize=12

[IconsMode]
PreviewSize=48
EOF

  chown -R "$user:$user" "$cfg"
  echo "    $user: palette + dolphin"
done

echo "==> done — the palette and wallpaper take effect at next login"
