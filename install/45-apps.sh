#!/usr/bin/env bash
# 45-apps — the applications a desktop is expected to have on first boot.
#
# Kept deliberately small: a browser, an image viewer, a PDF reader, a text editor beyond
# Kate's scope, and the archive tool. Everything else is meant to come from Nix, per app,
# per profile. Firefox is here because a machine without a browser is not usable on day one.
set -eu

[ "${1:-}" = "--help" ] && { echo "usage: 45-apps.sh"; exit 0; }

echo "==> temel uygulamalar"
pacman -S --noconfirm --needed \
  firefox \
  gwenview \
  okular \
  ark \
  spectacle \
  ffmpegthumbs \
  kdegraphics-thumbnailers

echo "==> Firefox varsayılan tarayıcı"
if command -v xdg-settings >/dev/null 2>&1; then
  xdg-settings set default-web-browser firefox.desktop 2>/dev/null || true
fi

echo "==> done"
