# REVIEW T3 — açık mod

Tarih: 2026-11-20 13:40 · Denetleyen: B · Durum: **review — done değil**
Görüntü: `docs/previews/T3-light-1280x800.png` (12:57, 1280×800)
Spec: `docs/DESIGN.md` §4.2, §4.3, §8/7, §8/8, §15.6, §15.1
Ölçüm: `python3 scripts/check_visual.py <png> --surface bar --mode light` (yeni: `--mode light`)

## Ölçüm — eşikler

```
bar               {'found': True, 'top': 7, 'bottom': 46, 'left': 13, 'right': 1267,
                   'height': 40, 'width': 1255}
amber_piksel_orani 0.056%  (<= 1.2%)
palet_disi_orani   0.223%  (<= 5.0%)   ← koyu modda 0.116%, açıkta iki kat
siyah_orani        0.005%  (<= 35.0%)
kenar_boslugu      {'left': 13, 'top': 7, 'right': 12}
bar_yuksekligi     40 ✓     bar_ust_boslugu 7 (±1) ✓
failures           yok
```

Plaka geometrisi, amber oranı, kenar ve siyah eşikleri geçti. Ancak `check_visual`
eşikleri ikon/plaka kontrastını ölçmüyor; aşağıdaki üç kusur pikselden elle ölçüldü.

## Ölçülen kusurlar

| bölge | ölçüm | spec | puan |
|---|---|---|---|
| launcher mark | Mark çizgileri `#D9D9D6` → **1,24:1**, `#EEEADF` → **1,05:1**, en iyi `#CDCECF` → **1,38:1**. Plaka `#F4EFE6` üstünde mark neredeyse görünmüyor. | §8/7 ikon 16 px'te okunur; T8 | 1 |
| pasif tikler | 6×2 ✓ ama renk `#A09A91` → **2,44:1**, `#AFAAA2` → **2,02:1**. | §8/8 non-text ≥3:1 | 1 |
| bar plakası | `surface #F4EFE6` / `bg #EFE7D9` = **1,072:1**. Plaka sayfadan neredeyse ayrışmıyor; bar ancak 2 px cetvel ve köşe çizgisiyle okunuyor. | §1.2 "bar tek plaka" | 2 |
| aktif tik rengi | `#8A600C` (primaryText) = **4,88:1**. Doğru okunuyor; ama `primary` dolgu `#B8862B` plaka üstünde 2,83:1 olduğu için Noctalia metin amberini kullanıyor. | §4.2 iki amber | 2 |
| kanıt | Yalnız 1280×800 masaüstü var; 2560 açık, panel/launcher/kilit açık yok. | T3 kabul: iki çözünürlük | 1 |
| yüzde | `55%`, `90%` — koyu modla aynı kusur. | §3.2 | 1 |

## İyi olanlar

- Plaka 40 px, üst 7, yan 12–13; cetvel 2 px; 5 tik (1 aktif + 4 pasif).
- Açık modda vinyet yok, ızgara hafif; duvar kağıdı metinsiz, amber yok.
- Saat 17 px / tarih 11 px; `20 Kasım 2026 Cuma` doğru.
- Durum ikonları koyu ve okunur (mark dışında).
- `A'nın notu`: PNG'de blok dokusu yok; llvmpipe çıktısı. Gerçek donanımda K1'de doğrulanacak — kabul.

## Karar

**review, done değil.** Üç gerçek kusur: mark kontrastı (1,05–1,38:1), pasif tik
kontrastı (2,0–2,5:1), plaka sayfa ayrımı (1,07:1). Ayrıca 2560 açık ve diğer yüzeylerin
açık hâli yok.

## Düzeltme sırası (A)

1. **Mark açık modda:** `text` (#1E2228) ile çizilmiş varyant veya
   `custom_image_colorize = true` + tema metin rengi. Hedef: plaka üstünde ≥3:1, 16 px'te
   okunur, 12 tikli detay yok (T8).
2. **Pasif tikler:** açıkta da ≥3:1 verecek tek renk (`muted`/`on_surface` opak).
3. **Plaka ayrımı:** `bg` ile `surface` arasına ölçülebilir bir fark koy (en az 1,15:1) veya
   plakayı 1 px `line` kenarıyla tanımla; 3 saniye testinde "bar" okunmalı.
4. **2560 açık + panel/launcher/kilit açık** çekimleri; `--mode light` ile ölçüm.
5. `%55` biçimi.
6. Aktif tik için sapma kaydı: açıkta `primaryText` (4,88:1), `primary` dolgu (2,83:1)
   kullanılmıyor. `DESIGN.md` §13'e satır.

## Kör test

K1–K3: **yapılmadı** — 2560 açık ve AI boş ekranı yok. Kanıtsız "geçti" yazılmaz.
