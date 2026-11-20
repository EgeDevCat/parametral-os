# REVIEW T12 — KDE Plasma birincil hat

Tarih: 2026-11-20 13:05 · Denetleyen: B · Durum: **blocked — VM görüntüsü yok**
Spec: `docs/DESIGN.md` §15.6 · Kod: `scripts/gen_kde_theme.py`, `tests/test_kde_theme.py`

KDE görsel kanıtı olmadan puan yok. Bu dosya, repo tarafında kapananları ve A'nın VM'de
yapması gerekenleri ayırır; "bitti" demek için görüntü şart.

## B tarafında kapananlar (repo)

| dosya | değişiklik | kanıt |
|---|---|---|
| `branding/kde/Parametral.colors` | token'lardan üretildi; Window bg `11,15,20`, text `233,228,216`, amber `224,169,59` | `gen_kde_theme.py --check` |
| `branding/kde/ParametralLight.colors` | iki amber: dolgu `184,134,43`, metin `127,85,16`; selection ink `26,21,10` | aynı + AA testi |
| `branding/kde/kdeglobals-snippet.ini` | `font=Inter`, `fixed=IBM Plex Mono`; Noto Sans yok | `test_first_login_fonts` |
| `branding/kde/konsole/Parametral.colorscheme` | Color1 `214,96,86` (danger), Color2/3 token | `test_ansi_roles_match_tokens` |
| `branding/sddm/parametral/Main.qml` | tüm renkler token kümesinde; `DejaVu Sans` → `Inter` | `Sddm` testleri |
| KDE layout | panel **üst**, **40 px**, `hiding=none`; alt 56 px dock ve autohide kaldırıldı | `test_panel_is_one_40px_top_plate` |
| `contents/defaults` | Plasma teması `Parametral` (breeze-dark değil) | `test_parametral_plasma_theme_is_selected` |
| splash | `#0F141A` → `#0B0F14`; font Inter | `test_splash_uses_tokens_and_inter` |
| panel SVG | yarıçap 14 → 12; `#12171E` + `#E0A93B` | `test_panel_svg_is_token_coloured_and_12px` |

`make test`: KDE tarafı 16/16; toplam sayı aşağıda.

## A'nın VM'de kapatması gerekenler

1. **Duvar kağıdı (bloklayıcı):** `install/75-desktop.sh` hâlâ `parametral-dark.png` /
   `parametral-light.png` dosyalarını `2560x1440.png` adıyla kuruyor. Yeni üretilmiş
   `branding/wallpapers/2560x1440.png` ve `2560x1440-light.png` kurulmalı. Yoksa KDE eski
   duvar kağıdını gösterir, 40 px plaka/ızgara gelmez.
2. **Fontlar:** `install/76-xdg-defaults.sh` kdeglobals'ta `Noto Sans` yazıyor; Inter +
   IBM Plex Mono olmalı. Ayrıca `fc-match Inter` çıktısı aynı VM'den.
3. **Panel:** 40 px üst plaka, `Parametral` Plasma teması, Breeze mavisi yok. 1280×800 ve
   2560×1440, dark + light; panel taşması yok.
4. **Cetvel applet'i (T14):** stok `workspaces` widget'ı bizim imzamız değil. 5 tik,
   pasif 6×2 `faint`, aktif 14×2 amber; panelin alt kenarında 2 px cetvel. Applet gelene
   kadar KDE'de imza yok sayılır.
5. **Kilit:** `contents/defaults` içinde `[kscreenlockerrc] Autolock=false`. Birincil masaüstü
   için bu bir güvenlik sapması; kullanıcı kararı olmadan açılmaz ama BOARD'a yazılmalı.
6. **SDDM:** doğru şifre, yanlış şifre, caps-lock; 1280×800 + 2560×1440. Palet ve Inter.
7. **AI yüzeyi:** approvals + snapshot KDE oturumunda; `pkexec` gerçekten yanıt veriyor mu?
   `check_visual` raporu + `T12-*.png`.
8. **K1–K3:** KDE 2560×1440 ile CachyOS yan yana; etiketsiz.

## Ölçüm beklentisi (A kanıtı geldiğinde)

```
python3 scripts/check_visual.py docs/previews/T12-<...>.png --surface desktop
bar height 40 · top gap 6 · amber <= 2.0% · palette <= 5% · edge >= 8 px
```

## Karar

**blocked.** Repo tarafı hazır; VM görüntüsü, `fc-match`, install düzeltmeleri ve T14 applet'i
olmadan T12 "done" değil. Üç kusur aranmadı; kanıt yok.
