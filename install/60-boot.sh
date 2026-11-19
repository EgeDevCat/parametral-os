#!/usr/bin/env bash
# 60-boot.sh — systemd-boot with both kernels and a rolling fallback.
set -Eeuo pipefail
[ "$(id -u)" -eq 0 ] || { echo "run as root" >&2; exit 1; }
source /etc/parametral/snapshot.env
[ -n "${PARAMETRAL_DEV:-}" ] || { echo "PARAMETRAL_DEV missing from /etc/parametral/snapshot.env" >&2; exit 1; }

echo "==> installing systemd-boot on the ESP"
bootctl --path=/boot install

cat > /boot/loader/loader.conf <<'EOF'
default  parametral.conf
timeout  4
console-mode max
editor   no
auto-entries yes
auto-firmware yes
EOF

CMDLINE_COMMON="rw add_efi_memmap quiet nowatchdog"
if [ "${PARAMETRAL_LUKS:-0}" = "1" ]; then
  CMDLINE_COMMON="cryptdevice=UUID=${PARAMETRAL_LUKS_UUID}:cryptroot root=/dev/mapper/cryptroot $CMDLINE_COMMON"
else
  CMDLINE_COMMON="root=${PARAMETRAL_DEV} $CMDLINE_COMMON"
fi

write_entry() {
  local file="$1" title="$2" kernel="$3" initrd="$4"
  cat > "/boot/loader/entries/$file" <<EOF
title   $title
linux   /$kernel
initrd  /$initrd
options rootflags=subvol=@ $CMDLINE_COMMON
EOF
}

echo "==> entries: main, backup kernel, fallback initramfs"
write_entry parametral.conf        "ParametralOS (linux)"      vmlinuz-linux     initramfs-linux.img
write_entry parametral-lts.conf    "ParametralOS — backup kernel (linux-lts)" vmlinuz-linux-lts initramfs-linux-lts.img
write_entry parametral-fallback.conf "ParametralOS (fallback initramfs)" vmlinuz-linux initramfs-linux-fallback.img

ls -l /boot/vmlinuz-* /boot/initramfs-* | sed 's/^/  /'
ls -l /boot/loader/entries | sed 's/^/  /'

echo "==> kernel command line for reference"
printf '  %s\n' "$CMDLINE_COMMON"
