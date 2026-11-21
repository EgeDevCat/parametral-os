# Bootable installer ISO

`iso/build.sh` remasters an official Arch Linux ISO into a bootable Parametral OS installer.
It does not need root and never modifies the Arch ISO.

```fish
bash iso/build.sh ~/Downloads/archlinux-2026.11.01-x86_64.iso \
                  /tmp/parametral-os-v0.1.0-x86_64.iso
```

Output is a hybrid BIOS + UEFI ISO:

- boot menu title **Parametral OS**, installer entry selected after 10 s;
- the installer starts automatically on `tty1`;
- the whole repository is on the ISO at `/parametral`;
- `/installer.sh` at the ISO root is the manual fallback:

```bash
mount -o ro /dev/sr0 /mnt
bash /mnt/installer.sh
```

The installer itself is the same terminal wizard as the payload image: disk, LUKS, hostname,
user, appearance and **KDE Plasma / Hyprland**. It sees the target disks through
`lsblk`, so the VM/disk must actually be attached.

## How the remaster works

1. Reads the Arch ISO's boot entries, syslinux files and `initramfs-linux.img` with `xorriso`.
2. Extracts the initramfs with `lsinitcpio`, adds a launcher, and patches the `archiso` hook to
   copy that launcher into the live root and record `archisodevice`.
3. Repacks the initramfs with `cpio` + `zstd` (as the installing user, with `-R 0:0`).
4. Rewrites the boot entries with a fixed volume UUID and `script=/root/parametral-installer.sh`.
5. Writes the ISO with `xorriso -boot_image any replay`, which preserves and re-patches the
   BIOS and UEFI boot images. `-volume_date uuid` is applied *after* the replay so
   `archisosearchuuid` and the ISO's real UUID agree.

Set `SOURCE_DATE_EPOCH` for a reproducible volume UUID:

```fish
env SOURCE_DATE_EPOCH=1795219200 bash iso/build.sh <arch.iso> <out.iso>
```

The release ISO is built this way; the test is a VirtualBox BIOS boot showing the Parametral
menu, the installer's disk list, and the KDE/Hyprland question.

## Requirements

`xorriso`, `lsinitcpio`, `cpio`, `zstd`, `python3`, and the Arch ISO. No root, no `mkarchiso`,
no `arch-chroot`.
