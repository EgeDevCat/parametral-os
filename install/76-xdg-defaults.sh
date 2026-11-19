#!/usr/bin/env bash
# 76-xdg-defaults — make Parametral the default look for every account on the image.
#
# Per-user KDE config (~/.config/kdeglobals) overrides these, which is what we want: a user
# who changes the theme keeps their choice, and a fresh account gets ours. Written to
# /etc/xdg because KConfig reads it as the fallback layer.
set -eu

[ "${1:-}" = "--help" ] && { echo "usage: 76-xdg-defaults.sh"; exit 0; }

echo "==> /etc/xdg defaults (theme, cursor, fonts, Konsole)"

install -d /etc/xdg /etc/gtk-3.0 /etc/gtk-4.0

cat > /etc/xdg/kdeglobals <<'EOF'
[General]
ColorScheme=Parametral
font=Noto Sans,10,-1,5,50,0,0,0,0,0
fixed=Noto Sans Mono,10,-1,5,50,0,0,0,0,0
menuFont=Noto Sans,10,-1,5,50,0,0,0,0,0
toolBarFont=Noto Sans,10,-1,5,50,0,0,0,0,0
smallestReadableFont=Noto Sans,8,-1,5,50,0,0,0,0,0

[KDE]
LookAndFeelPackage=org.parametral.desktop
widgetStyle=Breeze
SingleClick=false

[Icons]
Theme=breeze-dark

[Mouse]
cursorTheme=Parametral
cursorSize=24
EOF

cat > /etc/xdg/kcminputrc <<'EOF'
[Mouse]
cursorTheme=Parametral
cursorSize=24
EOF

cat > /etc/xdg/plasmarc <<'EOF'
[Theme]
name=breeze-dark
EOF

cat > /etc/xdg/konsolerc <<'EOF'
[Desktop Entry]
DefaultProfile=Parametral.profile
EOF


# Lock screen: the greeter renders "wallpaper" from this image path. Set it here so the lock
# screen is branded on every account without touching QML (the Breeze lockscreen is fine,
# only its background was generic).
cat > /etc/xdg/kscreenlockerrc <<'EOF'
[Daemon]
Autolock=false

[Greeter][Wallpaper][org.kde.image][General]
Image=/usr/share/wallpapers/Parametral/contents/images/2560x1440.png
EOF

# GTK apps (and anything using the Xcursor theme through GTK)
for ini in /etc/gtk-3.0/settings.ini /etc/gtk-4.0/settings.ini; do
  cat > "$ini" <<'EOF'
[Settings]
gtk-theme-name=Breeze-Dark
gtk-icon-theme-name=breeze-dark
gtk-cursor-theme-name=Parametral
gtk-cursor-theme-size=24
gtk-font-name=Noto Sans 10
EOF
done

# X11 default cursor for clients that ask for "default"
install -d /usr/share/icons/default
printf '[Icon Theme]\nInherits=Parametral\n' > /usr/share/icons/default/index.theme

echo "==> done"
