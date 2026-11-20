# Pano — tek gerçek kaynak

Her iş için tek satır. İş almadan önce burayı oku; aldığın işi `doing` yap; bitince `review` +
kanıt yaz. `done`yu yalnız doğrulayan taraf yazar.

| id | başlık | sahip | durum | kabul kriteri | kanıt |
|---|---|---|---|---|---|
| T7 | oturum: start-hyprland / XDG uyarılarını sıfırla | A | todo | Hyprland açılışında siyah toast yok; `journalctl -b --user -u hyprland` içinde uyarı satırı yok | — |
| T8 | font: Inter + IBM Plex Mono + 16 px mark | A/B | todo | `fc-match Inter` → Inter; mark 16 px'te net; 12 px tik kullanılmıyor | `fc-match` çıktısı: Inter.ttc "Inter" ✓ / IBM Plex Mono ✓ (2026-11-20, VM) — **B notu 12:20: bu host'ta `fc-match Inter` → Noto Sans; VM kanıtı ayrı isteniyor** |
| T0 | DESIGN.md + tokens (primaryText, yarıçap ölçeği) + çıta | B | review | DESIGN.md'de her bölüm sayılı spec; tokens.json'da primaryText; gen_theme.py + test güncel; `make test` OK | `docs/DESIGN.md`; `branding/tokens.json`; 18/18 theme testi; `shell/Theme.js` üretildi |
| T6 | bar: 40 px plaka + cetvel tikleri + saat hiyerarşisi + ikonlar | A | review | bar 40 px, workspace mavi yok, saat 17 px / tarih 11 px mono, yüzdeler ikonlu | `docs/previews/T6-before-1280x800-dark.png` / `T6-after-1280x800-dark.png` — yalnız 1280 dark; 2560/L/D/boş/hata yok (T10) |
| T1 | kilit: yanlış şifre + caps-lock durumları | A | todo | ikisi de tasarlanmış, AA, Türkçe, ekran görüntüsü | — |
| T2 | OSD: ses/parlaklık tuş testi | A | todo | OSD görünüyor, paletli, 2 sn içinde kayboluyor | — |
| T10 | önce/sonra önizleme seti (1280×800, 2560×1440, L/D, boş/dolu) | A | todo | her ekran için before/after, doğal çözünürlük | — |
| T3 | light mod doğrulaması + iki çözünürlükte önizleme | A | todo | primaryText ile AA, iki çözünürlük | — |
| T11 | check_visual.py + kör test K1–K3 | B | todo | script eşikleri raporlar; K1–K3 tek satır sonuç | — |
| T4 | docs/DESKTOP-HYPRLAND.md + README düzeltmesi | B | todo | belge gerçek durumu anlatıyor | — |
| T5 | shell/*.qml "deneysel" işaretleme | B | todo | her dosyada başlık notu + README satırı | — |

## Dosya kilidi

| dosya | sahip | iş |
|---|---|---|
| branding/tokens.json, scripts/gen_theme.py, tests/test_theme_tokens.py, docs/DESIGN.md | B | T0 |
| branding/noctalia/config.toml, branding/wallpapers/* | A | T6/T7 |
