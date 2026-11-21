#!/usr/bin/env bash
# Carried into the live root by iso/build.sh through a one-line archiso hook.
#
# The archiso initramfs mounts the medium at /run/archiso/bootmnt, but that mount is not
# guaranteed to survive into the live root on every firmware/medium combination. The hook
# also records `archisodevice` in /root/parametral-medium, so this script can mount the ISO
# itself if the path is gone.
set -u

export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

medium="$(cat /root/parametral-medium 2>/dev/null || true)"
[ -n "$medium" ] || medium=/dev/sr0
mnt=/mnt/parametral-iso
mkdir -p "$mnt"

for _ in $(seq 1 30); do
  if [ -f /run/archiso/bootmnt/installer.sh ]; then
    mnt=/run/archiso/bootmnt
    break
  fi
  if mountpoint -q "$mnt" || mount -o ro "$medium" "$mnt" 2>/dev/null; then
    break
  fi
  sleep 1
done

if [ ! -f "$mnt/installer.sh" ]; then
  printf '\n  Parametral ISO bulunamadi.\n'
  printf '  Elle: mount -o ro %s /mnt && bash /mnt/installer.sh\n\n' "$medium"
  exit 1
fi

printf '\n  Parametral OS kurulumu basliyor...\n\n'
exec bash "$mnt/installer.sh"
