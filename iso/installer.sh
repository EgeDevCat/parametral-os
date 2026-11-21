#!/usr/bin/env bash
# Parametral OS live helper.
#
# This file sits at the root of the ISO. The archiso `script=` argument (or the manual
# fallback printed on the live shell) runs it. It locates the payload relative to itself,
# so the same file works from /run/archiso/bootmnt, a manually mounted /mnt, or a USB stick.
set -u

export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"

# Stay on the first virtual console: the wizard is a TUI.
if [ -c /dev/tty1 ] && [ "$(tty 2>/dev/null || true)" != "/dev/tty1" ]; then
  exec </dev/tty1 >/dev/tty1 2>&1
fi

clear 2>/dev/null || true
printf '\n  Parametral OS kurulumu basliyor...\n\n'
exec python3 "$DIR/parametral/install/parametral-install" "$@"
