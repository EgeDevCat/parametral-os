#!/usr/bin/env bash
# build.sh — turn an official Arch ISO into the bootable Parametral OS installer ISO.
#
#     bash iso/build.sh /path/to/archlinux-YYYY.MM.DD-x86_64.iso [out.iso]
#
# The result boots (BIOS + UEFI), prints a Parametral boot menu, and starts the installer
# automatically. The whole repo is included at /parametral; `installer.sh` at the ISO root is
# the manual fallback.
#
# Needs no root: xorriso, lsinitcpio, cpio, zstd, python3. The Arch ISO is only read, never
# modified. Set SOURCE_DATE_EPOCH for a reproducible volume UUID.
set -Eeuo pipefail

BASE_ISO="${1:-}"
OUT="${2:-parametral-os-$(date -u +%Y.%m.%d)-x86_64.iso}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORK="${WORKDIR:-/tmp/parametral-iso-build}"
SDE="${SOURCE_DATE_EPOCH:-$(date -u +%s)}"
UUID16="$(date -u -d "@$SDE" +%Y%m%d%H%M%S)00"
SEARCH_UUID="$(date -u -d "@$SDE" +%Y-%m-%d-%H-%M-%S)-00"

if [ -z "$BASE_ISO" ]; then
  cat >&2 <<'EOF'
usage: bash iso/build.sh <archlinux.iso> [out.iso]

example:
  bash iso/build.sh ~/Downloads/archlinux-2026.11.01-x86_64.iso \
                    /tmp/parametral-os-v0.1.0-x86_64.iso
EOF
  exit 2
fi
[ -f "$BASE_ISO" ] || { echo "base ISO not found: $BASE_ISO" >&2; exit 2; }
for tool in xorriso lsinitcpio cpio zstd python3 mcopy; do
  command -v "$tool" >/dev/null || { echo "missing tool: $tool" >&2; exit 2; }
done

echo "==> workspace: $WORK"
rm -rf "$WORK"
mkdir -p "$WORK/remaster" "$WORK/payload" "$WORK/initramfs-extract"

echo "==> payload from $ROOT"
tar -C "$ROOT" \
  --exclude='./.git' \
  --exclude='./apps/*/target' \
  --exclude='./proofs/*.txt' \
  --exclude='./bin/seccomp_guard' \
  -cf - . | tar -x -C "$WORK/payload"

# The installer knows how to use prebuilt first-party apps when they are in the payload.
for app in parametral-ai parametral-approvals parametral-snapshots parametral-calculator; do
  built="$ROOT/apps/$app/target/release/$app"
  if [ -x "$built" ]; then
    dest="$WORK/payload/apps/$app/target/release"
    mkdir -p "$dest"
    cp -p "$built" "$dest/$app"
  fi
done

echo "==> boot files from the Arch ISO"
for rel in \
  loader/entries/01-archiso-linux.conf \
  loader/entries/02-archiso-speech-linux.conf \
  loader/loader.conf \
  boot/syslinux/archiso_head.cfg \
  boot/syslinux/archiso_sys-linux.cfg \
  boot/grub/loopback.cfg; do
  mkdir -p "$WORK/remaster/$(dirname "$rel")"
  xorriso -indev "$BASE_ISO" -osirrox on -extract "/$rel" "$WORK/remaster/$rel" >/dev/null 2>&1
done
chmod -R u+w "$WORK/remaster"

# The manual fallback at the ISO root.
install -m 0755 "$ROOT/iso/installer.sh" "$WORK/remaster/installer.sh"

echo "==> UEFI boot image: systemd-boot has its own FAT copy of loader.conf"
mkdir -p "$WORK/efi" "$WORK/efi-patch"
xorriso -osirrox on -indev "$BASE_ISO" -extract_boot_images "$WORK/efi" >/dev/null 2>&1
cp "$WORK/efi/eltorito_img2_uefi.img" "$WORK/efi/efi-parametral.img"
cat > "$WORK/efi-patch/01-archiso-linux.conf" <<EOF
title    Parametral OS installer (x86_64, UEFI)
sort-key 01
linux    /arch/boot/x86_64/vmlinuz-linux
initrd   /arch/boot/x86_64/initramfs-linux.img
options  archisobasedir=arch archisosearchuuid=$SEARCH_UUID script=/root/parametral-installer.sh
EOF
cat > "$WORK/efi-patch/02-archiso-speech-linux.conf" <<EOF
title    Parametral OS installer with speech (x86_64, UEFI)
sort-key 02
linux    /arch/boot/x86_64/vmlinuz-linux
initrd   /arch/boot/x86_64/initramfs-linux.img
options  archisobasedir=arch archisosearchuuid=$SEARCH_UUID accessibility=on script=/root/parametral-installer.sh
EOF
printf 'timeout 10\ndefault 01-archiso-linux.conf\nbeep on\n' > "$WORK/efi-patch/loader.conf"
for entry in 01-archiso-linux.conf 02-archiso-speech-linux.conf; do
  mcopy -o -i "$WORK/efi/efi-parametral.img" "$WORK/efi-patch/$entry" "::/loader/entries/$entry"
done
mcopy -o -i "$WORK/efi/efi-parametral.img" "$WORK/efi-patch/loader.conf" ::/loader/loader.conf

echo "==> live initramfs: carry the launcher into the live root"
xorriso -indev "$BASE_ISO" -osirrox on \
  -extract /arch/boot/x86_64/initramfs-linux.img "$WORK/initramfs.img" >/dev/null 2>&1
(
  cd "$WORK/initramfs-extract"
  lsinitcpio -x "$WORK/initramfs.img" >/dev/null
)
rm -f "$WORK/initramfs-extract/early_cpio"
install -m 0755 "$ROOT/iso/live-init.sh" "$WORK/initramfs-extract/parametral-installer.sh"

python3 - "$WORK/initramfs-extract/hooks/archiso" <<'PY'
import sys
from pathlib import Path

path = Path(sys.argv[1])
text = path.read_text()
needle = '''    if [ -f "/run/archiso/airootfs/airootfs.img" ]; then
        _mnt_dmsnapshot "/run/archiso/airootfs/airootfs.img" "${newroot}" "/"
    else
        _mnt_overlayfs "/run/archiso/airootfs" "${newroot}" "/"
    fi
'''
addition = '''
    # Parametral OS: put the installer launcher inside the live root and remember where the
    # medium was, so the launcher does not race the /run/archiso/bootmnt mount.
    if [ -f "/parametral-installer.sh" ]; then
        install -Dm755 "/parametral-installer.sh" "${newroot}/root/parametral-installer.sh"
        printf '%s\\n' "${archisodevice:-/dev/sr0}" > "${newroot}/root/parametral-medium"
    fi
'''
if 'Parametral OS: put the installer launcher' not in text:
    if needle not in text:
        raise SystemExit(f"cannot find the archiso overlay block in {path}")
    text = text.replace(needle, needle + addition, 1)
    path.write_text(text)
PY

(
  cd "$WORK/initramfs-extract"
  find . -print0 | cpio --null -o --format=newc -R 0:0 2>/dev/null |
    zstd -19 -T0 -q -o "$WORK/initramfs-parametral.img"
)

# UEFI systemd-boot loads the kernel and initramfs from its own FAT image, not from the
# ISO9660 tree. If only the ISO copy is replaced, UEFI boots the original Arch initramfs and
# the launcher never reaches the live root.
mcopy -o -i "$WORK/efi/efi-parametral.img" "$WORK/initramfs-parametral.img" ::/arch/boot/x86_64/initramfs-linux.img

echo "==> boot config: title, UUID, automatic installer"
python3 - "$WORK/remaster" "$SEARCH_UUID" <<'PY'
import sys
from pathlib import Path

remaster = Path(sys.argv[1])
uuid = sys.argv[2]
script = 'script=/root/parametral-installer.sh'

def edit(rel: str, pairs: list[tuple[str, str]]) -> None:
    path = remaster / rel
    text = path.read_text()
    for old, new in pairs:
        text = text.replace(old, new)
    path.write_text(text)

edit('loader/entries/01-archiso-linux.conf', [
    ('Arch Linux install medium (x86_64, UEFI)', 'Parametral OS installer (x86_64, UEFI)'),
    ('2026-11-01-08-42-25-00', uuid),
    ('options  archisobasedir=arch archisosearchuuid=' + uuid,
     'options  archisobasedir=arch archisosearchuuid=' + uuid + ' ' + script),
])
edit('loader/entries/02-archiso-speech-linux.conf', [
    ('Arch Linux install medium', 'Parametral OS installer'),
    ('2026-11-01-08-42-25-00', uuid),
    ('options  archisobasedir=arch archisosearchuuid=' + uuid,
     'options  archisobasedir=arch archisosearchuuid=' + uuid + ' ' + script),
])
edit('loader/loader.conf', [('timeout 15', 'timeout 10')])
edit('boot/syslinux/archiso_head.cfg', [('MENU TITLE Arch Linux', 'MENU TITLE Parametral OS')])
edit('boot/syslinux/archiso_sys-linux.cfg', [
    ('Arch Linux install medium', 'Parametral OS installer'),
    ('2026-11-01-08-42-25-00', uuid),
    ('APPEND archisobasedir=arch archisosearchuuid=' + uuid,
     'APPEND archisobasedir=arch archisosearchuuid=' + uuid + ' ' + script),
    ('It allows you to install Arch Linux or perform system maintenance.',
     'If the installer did not start, run: mount -o ro /dev/sr0 /mnt && bash /mnt/installer.sh'),
])
edit('boot/grub/loopback.cfg', [
    ('Arch Linux install medium', 'Parametral OS installer'),
    ('archisobasedir=arch img_dev=', 'archisobasedir=arch ' + script + ' img_dev='),
])
PY

echo "==> writing $OUT"
rm -f "$OUT"
xorriso -indev "$BASE_ISO" -outdev "$OUT" \
  -volid PARAMETRAL \
  -map "$WORK/remaster/loader/entries/01-archiso-linux.conf" /loader/entries/01-archiso-linux.conf \
  -map "$WORK/remaster/loader/entries/02-archiso-speech-linux.conf" /loader/entries/02-archiso-speech-linux.conf \
  -map "$WORK/remaster/loader/loader.conf" /loader/loader.conf \
  -map "$WORK/remaster/boot/syslinux/archiso_head.cfg" /boot/syslinux/archiso_head.cfg \
  -map "$WORK/remaster/boot/syslinux/archiso_sys-linux.cfg" /boot/syslinux/archiso_sys-linux.cfg \
  -map "$WORK/remaster/boot/grub/loopback.cfg" /boot/grub/loopback.cfg \
  -map "$WORK/initramfs-parametral.img" /arch/boot/x86_64/initramfs-linux.img \
  -map "$WORK/remaster/installer.sh" /installer.sh \
  -map "$WORK/payload" /parametral \
  -boot_image any replay \
  -append_partition 2 0xef "$WORK/efi/efi-parametral.img" \
  -boot_image any efi_path=--interval:appended_partition_2:all:: \
  -volume_date uuid "$UUID16" \
  -commit >/dev/null

if command -v blkid >/dev/null 2>&1; then
  actual="$(blkid -p "$OUT" | tr ' ' '\n' | sed -n 's/^UUID="\(.*\)"$/\1/p')"
  [ "$actual" = "$SEARCH_UUID" ] || {
    echo "volume UUID mismatch: expected $SEARCH_UUID, got $actual" >&2
    exit 1
  }
fi

sha256sum "$OUT" > "$OUT.sha256"
echo "==> done: $OUT"
cat "$OUT.sha256"
