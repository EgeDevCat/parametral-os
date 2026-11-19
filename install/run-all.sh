#!/usr/bin/env bash
# run-all.sh — one-shot install for a throwaway test VM (no LUKS, known passwords).
# A real install runs the steps by hand from docs/INSTALL-ARCH.md.
set -Eeuo pipefail
DISK="${1:-/dev/sda}"
SRC="$(cd "$(dirname "$0")/.." && pwd)"

echo "=== 10 preflight"
bash "$SRC/install/10-preflight.sh" "$DISK" --yes
echo "=== 20 disk (no LUKS: test VM only)"
bash "$SRC/install/20-disk.sh" "$DISK" --yes --no-luks
echo "=== 30 bootstrap (both kernels, nix)"
bash "$SRC/install/30-bootstrap.sh"
echo "=== 35 nix (package manager)"
bash "$SRC/install/35-nix.sh"
echo "=== payload into the installed system"
mkdir -p /mnt/opt
cp -r "$SRC" /mnt/opt/parametral-src
echo "=== 40 users (in chroot — must target the installed system, not the live ISO)"
arch-chroot /mnt bash -c 'cd /opt/parametral-src && bash install/40-users.sh --non-interactive'
echo "=== 65 branding (splash + login)"
bash "$SRC/install/65-branding.sh"
echo "=== 75 desktop identity (in chroot)"
arch-chroot /mnt bash -c 'cd /opt/parametral-src && bash install/75-desktop.sh'
echo "=== 50 snapshots (in chroot)"
arch-chroot /mnt bash -c 'cd /opt/parametral-src && bash install/50-snapshots.sh'
echo "=== 60 boot (in chroot)"
arch-chroot /mnt bash -c 'cd /opt/parametral-src && bash install/60-boot.sh'
echo "=== 70 verify (in chroot)"
arch-chroot /mnt bash -c 'cd /opt/parametral-src && bash install/70-verify.sh'
echo "=== clean unmount (a dirty ESP makes the firmware refuse to boot)"
sync
umount -R /mnt || true
sync
echo "=== INSTALL DONE — poweroff, detach the ISO, boot from the disk"
