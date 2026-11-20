# Parked — 2026-11-20

This repository is **parked**, not deleted. The scope changed: the next product is a Rust
AI/MCP tool platform and its app, not a desktop distribution. The work here stays as a
reference and can be resumed.

## What works

- `make test`: **256 tests OK** (10 conditional skips at the time of parking).
- The AI layer exists and is tested: oracle → policy → token → handler → audit, hash-chained
  `audit.jsonl`, snapshots, sandbox (bwrap + seccomp + cgroup v2), approvals, netproxy.
- The design system is measured: `docs/DESIGN.md`, `branding/tokens.json`,
  `scripts/gen_theme.py`, 18 theme tests; `scripts/check_visual.py` with dark/light modes.
- Hyprland + UWSM + Noctalia session works; KDE Plasma is the safe session.
- Installers for Arch (`install/*.sh`), SDDM/GRUB/plymouth assets, wallpapers, lock.

## Known gaps at parking

- **T6 bar 23/30** (not done): passive tick contrast 2.2–3.1:1, 12-tick mark at 16 px,
  `55%` instead of `%55`, unclear control-centre glyph, stale 2560 preview.
- **T3 light mode**: mark 1.05–1.38:1 on the plate (invisible), passive ticks 2.0–2.5:1,
  plate/page 1.072:1; only 1280 desktop shot, no 2560 light.
- **T12 KDE**: code ready (`gen_kde_theme.py`, SDDM/Konsole/panel, 18 tests) but not merged
  or verified in the VM; `install/76` still sets Noto Sans, not Inter.
- **T14 KDE ruler applet**: code ready, never loaded in Plasma.
- **AI empty states** (`model yok`, `gateway yok`, `oracle yok`) and SFT trace schema (T13)
  are specified, not implemented.
- K1–K3 blind tests never run (no 2560 light + CachyOS side-by-side).

## Branches

| branch | content |
|---|---|
| `master` | merged T0 + T11; latest light-mode work (`5fee021`) |
| `feat/T6-review` | T6 re-score 23/30 + measured findings |
| `feat/T3-review` | `check_visual --mode light` + T3 findings (3 defects) |
| `feat/T12` | KDE palette generator, SDDM/Konsole/panel, ruler applet (18 tests) |
| `feat/T0`, `feat/T11` | merged into master |

## If resumed

1. Merge `feat/T12`, install the plasmoid and Inter/IBM Plex Mono, take KDE
   1280/2560 dark+light screenshots.
2. Fix T6 (tick contrast, 16 px mark, `%55`, control icon, 2560 re-shoot).
3. Fix T3 (mark light variant, tick contrast, plate separation ≥1.15:1, 2560 light).
4. Then T10 (empty/error/AI "yok") and T13 (SFT traces).

Do not delete the repo; the audit/policy/sandbox code and the design system are reusable in
the new product.
