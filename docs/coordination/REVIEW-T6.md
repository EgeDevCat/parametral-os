# REVIEW T6 — bar: 40 px plaka + cetvel tikleri + saat hiyerarşisi

Tarih: 2026-11-20 13:25 · Denetleyen: B · Durum: **review — 23/30, done değil**
Görüntü: `T6-after-1280x800-dark.png` (12:53, native)
Spec: `docs/DESIGN.md` §1.1, §1.2, §3.2, §4.3, §8/7, §10, §15.1
Ölçüm: `python3 scripts/check_visual.py <png> --surface bar`

## Ölçüm — 1280×800 (native, güncel)

```
bar               {'found': True, 'top': 7, 'bottom': 46, 'left': 15, 'right': 1265,
                   'height': 40, 'width': 1251}
amber_piksel_orani 0.056%  (<= 1.2%)
palet_disi_orani   0.112%  (<= 5.0%)
siyah_orani        0.005%  (<= 35.0%)
kenar_boslugu      {'left': 15, 'top': 7, 'right': 14}
bar_yuksekligi     40  ✓      bar_ust_boslugu 7 (±1) ✓
amber tik          14 px ✓    failures: yok
```

Plaka, cetvel, aktif tik, kenar ve palet **geçti**. Önceki üç bulgu kapandı:

- aktif tik 7 → **14 px** (`x 40–53`, `#E0A93B`, 8,49:1)
- 1280 kanıtı native; plaka 40 px
- mark amberden çıktı; markta amber piksel yok (yalnız aktif tik)

## Kalan ölçülü kusurlar

| bölge | kusur | neden (spec) | puan |
|---|---|---|---|
| bar / pasif tik | 4 tik, her biri **6 × 2 px** ✓ ama çekirdek renkler `#505861` (2,49:1), `#5F6772` (3,14:1), `#49505A` (2,21:1). 2 px yükseklikte antialias çoğu pikseli 3:1 altına düşürüyor. | §8/8 non-text ≥3:1; §1.1 pasif tik `faint` #7C8592 olmalı | 1 |
| bar / mark | 16 px kutuda **12 tikli** dial varyantı kullanılıyor; görünür çap 14 px, detay kaba. | §8/7 "12 tik mark 16 px'te kullanılmaz"; T8 | 1 |
| bar / durum | `55%`, `90%` — yüzde sonda. | §3.2 `%55` | 1 |
| bar / ikon | Kontrol merkezi glifi 16 px'te okunmuyor (kare + çapraz + nokta). | §8/7 | 2 |
| kanıt / 2560 | 2560 karesi 12:30 tarihli; config düzeltmesinden önce, `amber-tick` 7 px ile düşüyor. | §12/2 güncel kanıt | 1 |
| kanıt / durumlar | Light, boş, hata, AI "yok" yok; K1–K3 yapılamaz. | §15.1, T10/T3 | 1 |

## Çıta

1 Hiyerarşi **3** · 2 Izgara **3** · 3 Tipografi **[KAPI] 3** · 4 Renk **[KAPI] 3** ·
5 Durumlar **1** · 6 Dil **2** · 7 İkon **1** · 8 Erişilebilirlik **2** · 9 Dürüstlük **[KAPI] 2** ·
10 Kimlik **3** → **23/30**

Kapılarda 0 yok; ama toplam 24'ün altında. **done değil.**

## Düzeltme sırası (A)

1. **Pasif tik kontrastı:** `#505861` / `#49505A` yerine en az 3:1 veren tek renk.
   `on_surface_variant` yüzeyde 7,1:1; widget'ın uyguladığı opaklık düşürüyorsa
   `on_surface` (#E9E4D8) veya opaklığı kaldır. Ölçüm: 6×2 tik, en kötü piksel ≥3,0:1.
2. **Mark 16 px:** 12 tikli dial yerine sade 16 px varyant (4 tik veya çember + ibre).
   `T8` mark denetimi buna bağlı.
3. **`%55` / `%90`** biçimi. Noctalia sabit biçim veriyorsa sapma kaydı + kendi widget'ı.
4. **Kontrol merkezi ikonu:** 16 px'te okunur tek stroke glif.
5. **2560×1440'ı yeni config ile yeniden çek**; `check_visual` temiz olsun.
6. Light + boş + hata + AI "yok" (T10/T3); sonra K1–K3.

İlk üç madde + 2560 çekimi 24'ü geçirir; durumlar ayrı iş.

## Kör test

K1–K3: **yapılmadı** — light ve AI boş ekranı yok. Kanıtsız "geçti" yazılmaz.
