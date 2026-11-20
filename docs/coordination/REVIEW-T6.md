# REVIEW T6 — bar: 40 px plaka + cetvel tikleri + saat hiyerarşisi

Tarih: 2026-11-20 13:15 · Denetleyen: B · Durum: **review — 22/30, done değil**
Görüntüler: `T6-before-1280x800-dark.png`, `T6-after-1280x800-dark.png` (12:46),
`T6-after-2560x1440-dark.png` (12:30)
Spec: `docs/DESIGN.md` §1.1, §1.2, §3.2, §4.3, §10, §15.1
Ölçüm: `python3 scripts/check_visual.py <png> --surface bar`

## Ölçüm — 1280×800 (native, güncel)

```
bar               {'found': True, 'top': 7, 'bottom': 46, 'left': 15, 'right': 1265,
                   'height': 40, 'width': 1251}
amber_piksel_orani 0.064%  (<= 1.2%)
palet_disi_orani   0.110%  (<= 5.0%)
siyah_orani        0.005%  (<= 35.0%)
kenar_boslugu      {'left': 15, 'top': 7, 'right': 14}
bar_yuksekligi     40  ✓
bar_ust_boslugu    7   (±1) ✓
amber tik          14 px ✓
failures           yok
```

Plaka, cetvel, tik ölçüsü, kenar ve palet **geçti**. `wallpaper = ekran boyu` düzeltmesi
(`ecc2b42`) doğru sonuç vermiş.

## Ölçüm — 2560×1440 (12:30, eski)

```
bar 40 px · amber %0.018 · palet %0.051 · siyah %0.003 · kenar 15/14
amber tik 7 px  → failures: amber-tick
```

Bu kare **tik düzeltmesinden önce** (config 12:46'da `active_pill_size 3.5 → 7.0` oldu).
Kanıt olarak kullanılamaz; 2560 yeniden çekilmeli. A'nın panodaki "2560'ta 14×2" iddiası
bu dosyayla doğrulanmıyor.

## Bulgular

| bölge | kusur | neden (spec) | puan |
|---|---|---|---|
| kanıt / 2560 | 2560 karesi 12:30 tarihli; aktif tik 7 px ölçülüyor; config düzeltmesi sonrası yeniden çekilmedi. | §12/2 doğal çözünürlük + güncel kanıt | 1 |
| bar / durum | `55%`, `90%` — yüzde sonda. `%55`, `%90` olmalı. | §3.2 | 1 |
| bar / ikon | Kontrol merkezi glifi 16 px'te okunmuyor (kare + çapraz + nokta). | §8/7 | 2 |
| bar / mark | 16 px mark varyantı hâlâ doğrulanmadı; 12 tikli detay 16 px'te ince. | §2.3, T8 | 2 |
| bar / amber | Mark üzerinde küçük amber yay + aktif tik: iki canlı amber. | §4.3 | 2 |
| kanıt | Light, boş, hata, AI "yok" yok; K1–K3 yapılamaz. | §15.1, T10 | 1 |
| saat / tarih | 17 px medium + 11 px muted; `20 Kasım 2026 Cuma` doğru. | §3.2 | 3 |
| plaka / cetvel | 40 px, üst 6 (±1), yan 8 (±), 2 px cetvel, 5 tik. | §1.1/§1.2 | 3 |
| duvar kağıdı | Izgara + kadran, metin yok, amber yok, düşük kontrast. | §5.7 | 3 |
| plaka rengi | `#12171E` = `surface`. | §4.1 | 3 |

## Çıta

1 Hiyerarşi **3** · 2 Izgara **3** · 3 Tipografi **[KAPI] 2** · 4 Renk **[KAPI] 2** ·
5 Durumlar **1** · 6 Dil **2** · 7 İkon **2** · 8 Erişilebilirlik **2** · 9 Dürüstlük **[KAPI] 2** ·
10 Kimlik **3** → **22/30**

Alt sınır 24. **done değil.** Kalan üç iş bunu 24'e taşır: `%55` biçimi, kontrol merkezi
ikonu, 2560'ın yeniden çekilmesi. Light/boş/hata ve AI "yok" ekranları ayrıca T10/T3.

## Düzeltme sırası (A)

1. `%55` / `%90` biçimi (Noctalia yüzde widget'ı sabit biçim veriyorsa sapma kaydı + kendi
   widget'ı).
2. Kontrol merkezi ikonunu 16 px'te okunur tek stroke glifle değiştir.
3. 2560×1440'ı yeni config ile yeniden çek; `check_visual` temiz olsun.
4. Mark'ı 16 px'e indir; amber yayı kaldır (amber yalnız aktif tik).
5. Light + boş + hata + AI "yok" (T10/T3); sonra K1–K3.

## Kör test

K1–K3: **yapılmadı** — light ve AI boş ekranı yok. Kanıtsız "geçti" yazılmaz.
