#!/usr/bin/env bash
# 70-verify.sh — the evidence. Run this on the installed system and paste the output.
set -uo pipefail
export PATH="/usr/local/bin:/usr/local/sbin:$PATH"
# 60-boot needs PARAMETRAL_DEV for its boot entries; 70 needs it again to exercise
# snapshot boot-entry. Source it instead of exporting a second copy from the installer.
# shellcheck disable=SC1091
[ -f /etc/parametral/snapshot.env ] && . /etc/parametral/snapshot.env

PASS=0; FAIL=0
ok()   { printf '  [PASS] %s\n' "$*"; PASS=$((PASS+1)); }
bad()  { printf '  [FAIL] %s\n' "$*"; FAIL=$((FAIL+1)); }
# eval in a subshell: a check expression contains `exit 1` and must not end the script
check(){ if ( eval "$2" ) >/dev/null 2>&1; then ok "$1"; else bad "$1"; fi; }

# findmnt reports the modern form `subvol=/@`, not `subvol=@,`; match both without
# pairing the name with the wrong target (a bare grep for "@" also matches @home).
subvol_mounted() {
  local target="$1" name="$2"
  findmnt -no OPTIONS "$target" 2>/dev/null |
    grep -Eq "(^|,)subvol=/@${name#@}(,|$)"
}

echo "Parametral OS install verification — $(date -u +%FT%TZ) on $(uname -r)"
echo

echo "1) snapshot system"
check "btrfs root"                     "findmnt -no FSTYPE / | grep -q btrfs"
if subvol_mounted / @ &&
   subvol_mounted /home @home &&
   subvol_mounted /var @var &&
   subvol_mounted /.snapshots @snapshots; then
  ok "@ / @home / @var / @snapshots mounted"
else
  bad "@ / @home / @var / @snapshots mounted"
fi
check "snapshot tool installed"        "test -x /usr/local/bin/parametral-snapshot"
check "pacman pre-transaction hook"    "grep -q parametral-snapshot /etc/pacman.d/hooks/90-parametral-snapshot.hook"
SNAP_LIST="$(parametral-snapshot list 2>/dev/null || true)"
if printf '%s\n' "$SNAP_LIST" | grep -q 'present'; then
  ok "at least one snapshot exists"
else
  bad "at least one snapshot exists"
fi
if command -v parametral-snapshot >/dev/null; then
  FIRST_ID="$(printf '%s\n' "$SNAP_LIST" | awk 'NR>1 && $NF == "present" {print $1; exit}')"
  if [ -n "${FIRST_ID:-}" ]; then
    check "boot entry can be generated"  "parametral-snapshot boot-entry $FIRST_ID >/dev/null"
    ENTRY="/boot/loader/entries/parametral-snap-$FIRST_ID.conf"
    if [ -f "$ENTRY" ]; then ok "boot entry written ($ENTRY)"; else bad "boot entry missing"; fi
    rm -f "$ENTRY"   # verification artifact, not a permanent menu item
  fi
fi

echo
echo "2) user separation"
check "ai has no supplementary groups" "[ \"\$(id -nG ai | tr ' ' '\\n' | grep -vc '^ai$')\" -eq 0 ]"
# sudo's denial message is localised under the Turkish locale; the exit status is the
# contract, not the English word "not allowed".
if command -v sudo >/dev/null 2>&1 && ! sudo -l -U ai >/dev/null 2>&1; then
  ok "ai cannot sudo"
else
  bad "ai cannot sudo"
fi
check "ai cannot read the approver key dir" "! runuser -u ai -- test -r /var/lib/parametral/keys"
check "ai cannot read /etc/parametral/keys/*.sk" "! runuser -u ai -- sh -c 'cat /etc/parametral/keys/*.sk' 2>/dev/null"
check "ai home is 0700"                "[ \"\$(stat -c %a /home/ai)\" = \"700\" ]"
check "polkit denies ai"               "grep -q 'subject.user === \"ai\"' /etc/polkit-1/rules.d/50-parametral-ai.rules"
check "approver key is 0700 root"      "[ \"\$(stat -c %a /var/lib/parametral/keys)\" = \"700\" ]"
check "parametral has no shell"           "grep -q '/usr/bin/nologin' <(getent passwd parametral)"

echo
echo "3) backup kernel"
check "linux-lts installed"            "pacman -Q linux-lts"
check "lts kernel present in /boot"    "test -f /boot/vmlinuz-linux-lts"
check "lts initramfs present"          "test -f /boot/initramfs-linux-lts.img"
check "fallback initramfs present"     "test -f /boot/initramfs-linux-fallback.img"
check "3 boot entries written"         "[ \"\$(ls /boot/loader/entries/parametral*.conf | wc -l)\" -ge 3 ]"
check "loader timeout set"             "grep -q '^timeout' /boot/loader/loader.conf"

echo
echo "4) nix"
check "nix installed"                  "command -v nix"
check "nix-daemon enabled"             "systemctl is-enabled nix-daemon"
check "require-sigs = true"            "grep -q '^require-sigs = true' /etc/nix/nix.conf"
check "sandbox = true"                 "grep -q '^sandbox = true' /etc/nix/nix.conf"
check "ai is not a trusted user"       "! grep -q 'trusted-users.*ai' /etc/nix/nix.conf"

echo
echo "5) desktop edition"
if [ -f /etc/parametral/desktop.conf ]; then
  # shellcheck disable=SC1091
  . /etc/parametral/desktop.conf
  ok "edition selection recorded (${PARAMETRAL_DESKTOP:-unset})"
  check "greeter service enabled" "systemctl is-enabled sddm.service"
  check "parametral-desktop helper installed" "test -x /usr/local/bin/parametral-desktop"
  case "${PARAMETRAL_DESKTOP:-}" in
    kde|both)
      check "KDE Plasma installed" "pacman -Q plasma-desktop"
      check "Plasma session entry present" "test -f /usr/share/wayland-sessions/plasma.desktop -o -f /usr/share/xsessions/plasma.desktop"
      check "Parametral KDE colour scheme" "test -f /usr/share/color-schemes/Parametral.colors"
      ;;
  esac
  case "${PARAMETRAL_DESKTOP:-}" in
    hyprland|both)
      check "Hyprland stack installed" "pacman -Q hyprland noctalia uwsm"
      check "Parametral session launcher" "test -x /usr/local/bin/parametral-session"
      check "Parametral session entry" "test -f /usr/share/wayland-sessions/parametral.desktop"
      check "Hyprland config installed" "test -f /etc/parametral/hypr/parametral.lua"
      check "generated palette installed" "grep -q 'appearance' /etc/parametral/hypr/theme.lua"
      ;;
  esac
  primary="${PARAMETRAL_PRIMARY_SESSION:-plasma}"
  if [ -f "/usr/share/wayland-sessions/$primary.desktop" ] ||
     [ -f "/usr/share/xsessions/$primary.desktop" ]; then
    ok "primary session entry exists ($primary.desktop)"
  else
    bad "primary session entry missing ($primary.desktop)"
  fi
else
  bad "desktop edition not recorded (/etc/parametral/desktop.conf)"
fi

echo
echo "RESULT: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ] || exit 1
