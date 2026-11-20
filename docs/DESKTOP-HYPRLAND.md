# The Parametral desktop (Hyprland session)

The Hyprland session is the edition we build ourselves: Hyprland is the compositor, the shell
above it is ours (Quickshell/QML), and every piece of it is a file on disk that a snapshot can
bring back.

The KDE Plasma session stays available in SDDM as the safe option. Both read the same
`/etc/parametral` configuration and the same amber/graphite palette.

## What runs

| Surface   | File                                     | Installed to                              |
|-----------|------------------------------------------|-------------------------------------------|
| Compositor| `branding/hypr/parametral.lua`           | `/etc/parametral/hypr/parametral.lua`     |
| Bar       | `shell/shell.qml`                        | `/usr/share/parametral/shell/shell.qml`   |
| Launcher  | `shell/launcher.qml`                     | `/usr/share/parametral/shell/launcher.qml`|
| Lock      | `branding/hypr/hyprlock.conf`            | `/etc/parametral/hypr/hyprlock.conf`      |
| Session   | `install/79-hypr.sh`                     | `/usr/share/wayland-sessions/parametral.desktop` |

Hyprland 0.57 reads the session from a **Lua** config; the old `hyprland.conf` syntax no longer
parses. The session entry must point at `parametral.lua` — pointing it at the old file starts
Hyprland with defaults and no error anyone sees.

## Keys

| Key | Action |
|-----|--------|
| `SUPER + Space` | Launcher (ours, `shell/launcher.qml`) |
| `SUPER + Return` | Konsole |
| `SUPER + E` | Dolphin |
| `SUPER + Q` | Close window |
| `SUPER + L` | Lock (hyprlock) |
| `SUPER + Escape` | Power menu (bar IPC: `qs ... ipc call powermenu toggle`) |
| `SUPER + 1..5` | Workspace |
| `SUPER + SHIFT + 1..5` | Move window to workspace |
| `SUPER + arrows` | Focus direction |
| `SUPER + M` | Leave the session |

## The bar

Bottom, floating islands: launcher (gauge), workspaces 1–5, status (volume, battery, network),
clock with a Turkish date, power. Islands are separated on purpose — one wide bar reads as a
taskbar from any other distribution.

Status sources are honest rather than clever:

- volume is polled from `wpctl` every 3 s. Quickshell's Pipewire node API reports `0` for a
  suspended sink, and a wrong number is worse than a slightly stale one.
- battery hides itself when UPower has no display device (desktops, VMs without one).
- the network dot is neutral when connectivity is unknown; colour is a claim.

## Design tokens

`#0B0F14` page · `#12171E` island · `#1A2029` card · `#E9E4D8` text · `#9AA4B2` muted ·
`#E0A93B` amber · radius 12–14 px · 1 px amber hairline at 22% opacity.

The same tokens live in `apps/parametral-ui` for the Rust apps, so the shell and the windows do
not drift apart.

## Session selection

SDDM lists both sessions. Autologin, when enabled, is set in `/etc/sddm.conf.d/`:

```ini
[Autologin]
User=operator
Session=parametral      # or: plasma
Relogin=false
```

The session name is the desktop entry's file name, not a path.

## Known gaps

- No polkit agent that actually answers yet. `shell/polkit.qml` is written and its agent
  registers (`isRegistered` is true), but `pkexec` in the VM still answers "No authentication
  agent found", so the end-to-end path is unverified. Until it is fixed, the snapshot app's
  rollback (`pkexec`) has nobody to ask in this session — use the KDE session for that.
- No notification daemon (`Quickshell.Services.Notifications`) yet.
- No settings app: changing the palette or the bar means editing files and reloading
  (`hyprctl reload`, `systemctl --user restart qsbar`).
- The bar's tray island only appears when there are tray items; there is no overflow menu yet.

## Donanım

| | |
|---|---|
| RAM (en az) | 8 GB |
| RAM (önerilen) | 16 GB (32 GB rahat) |
| Disk | 40 GB btrfs (snapshot'lar dahil) |
| GPU | donanım GL; VM'lerde yazılım GL otomatik (`parametral-session`) |

4 GB ile oturum açılıyor ama tarayıcı + derleme aynı anda gelince makine kilitleniyor; 8 GB ve
üstü takılmayı bitiriyor. Takas zorunlu değil ama btrfs swapfile (4 GB) kilitlenmeye karşı sigorta.
