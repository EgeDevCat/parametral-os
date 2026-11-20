# REVIEW T6 — bar: 40 px plaka + cetvel tikleri + saat hiyerarşisi

Tarih: 2026-11-20 12:45 · Denetleyen: B · Görüntüler:
`T6-before-1280x800-dark.png`, `T6-after-1280x800-dark.png`, `T6-after-2560x1440-dark.png`
Spec: `docs/DESIGN.md` §1.1, §1.2, §3.2, §4.3, §10, §15.1
Ölçüm: `python3 scripts/check_visual.py <png> --surface bar`

## Ölçüm — 2560×1440 (native, gerçek 1× kanıt)

```
bar               {'found': True, 'top': 7, 'bottom': 46, 'left': 15, 'right': 2545,
                   'height': 40, 'width': 2531}
amber_piksel_orani 0.018%  (<= 1.2%)
palet_disi_orani   0.052%  (<= 5.0%)
siyah_orani        0.003%  (<= 35.0%)
kenar_boslugu      {'left': 15, 'top': 7, 'right': 14, 'bottom': 1393}
bar_yuksekligi     40  (hedef 40) ✓
bar_ust_boslugu    7   (hedef 6, ±1) ✓
failures           amber-tick
```

Plaka, yükseklik, kenar, palet ve siyah eşikleri **geçti**. Kalan kod kusuru tik ölçüsü.

## Ölçüm — 1280×800

```
bar               {'found': True, 'top': 3, 'bottom': 25, 'left': 0, 'right': 1279,
                   'height': 23, 'width': 1280}
bar_yuksekligi     23  (hedef 40)
bar_ust_boslugu    3   (hedef 6)
failures           edge, bar-height, bar-top-gap, amber-tick
```

Bu görüntü **native 1280 render değil**: 2560×1440 karenin 0,5'e küçültülmüş hâli.
Plaka 40→23 px, tik 7→5 px, pasif tikler ölçekte birleşiyor. Kanıt olarak kullanılamaz;
"küçültmesiz" kuralı ihlal. Native 1280 çekimi gerekir (veya "detay" olarak etiketlenir).

## Bulgular

| bölge | kusur | neden (spec) | puan |
|---|---|---|---|
| bar / 1280 kanıt | 1280×800 görüntüsü 2560 karenin küçültülmüş hâli; plaka 23 px, tik 5 px, 5 tik 3'e düşüyor. | §12/2 "doğal çözünürlük, küçültmesiz"; §10. | 1 |
| bar / aktif tik | 2560'ta aktif tik **7 × 2 px** (x 40–46); spec **14 × 2**. | §1.1 imza; `check_visual` → `amber-tick`. | 1 |
| bar / pasif tik | Pasif tik **4 px**, çekirdek renk `#212830` (≈ `line`); surface üstünde ≈1,4:1. Spec 6 × 2, `faint` #7C8592 (4,82:1). | §1.1; §8/8 non-text ≥3:1. | 1 |
| bar / durum | `55%`, `90%` — yüzde sonda. `%55`, `%90` olmalı. | §3.2. | 1 |
| bar / ikon | Kontrol merkezi glifi 16 px'te okunmuyor (kare + çapraz + nokta); diğerleri ince çizgi. | §8/7 tek stroke seti, 16 px'te okunur. | 2 |
| bar / mark | 2560'ta görünür mark ≈13 px + 12 tikli detay; 1280'de bulanık. 16 px net varyant doğrulanmadı. | §2.3; T8 "mark 16 px denetimi BEKLEMEDE". | 2 |
| bar / amber | Aktif tik + mark üzerinde 2 px amber yay: iki canlı amber. Mark `text`/`muted` olmalı. | §4.3. | 2 |
| kanıt | Light, boş, hata ve AI "yok" ekranı yok; K1–K3 yapılamaz. | §12/2, §15.1, T10. | 1 |
| saat / tarih | 2560'ta `12:30` 17 px medium, tarih 11 px muted; `20 Kasım 2026 Cuma` doğru. | §3.2. | 3 |
| cetvel çizgisi | 2 px, plakanın alt kenarında, içeriden başlıyor; 40 px plaka ile aynı dil. | §1.1. | 3 |
| duvar kağıdı | Izgara + kadran, metin yok, amber yok, kontrast düşük. | §5.7. | 3 |
| plaka rengi | Ölçülen `#12171E` = `surface`. | §4.1. | 3 |

## Çıta

1 Hiyerarşi **3** · 2 Izgara **2** · 3 Tipografi **[KAPI] 2** · 4 Renk **[KAPI] 2** ·
5 Durumlar **1** · 6 Dil **2** · 7 İkon **2** · 8 Erişilebilirlik **2** · 9 Dürüstlük **[KAPI] 2** ·
10 Kimlik **3** → **21/30**

Alt sınır 24. Kapılar 0 değil ama toplam yetmiyor. **done değil.**

## Düzeltme sırası (A)

1. Aktif tik 14 × 2; pasif 6 × 2 ve `faint` #7C8592 (şu an 4 px / `line`).
2. Native 1280×800 çekimi: `monitors.lua` scale 1 + 1280×800 wallpaper; küçültme yok.
3. `%55` / `%90` biçimi.
4. Kontrol merkezi ikonunu 16 px'te okunur tek stroke glifle değiştir.
5. Mark'ı `text`/`muted` yap; amber yalnız aktif tikte kalsın; 16 px varyantı göster.
6. Light + boş + hata + AI "yok" ekranları (T10/T3); sonra `check_visual` tekrar.

## Kör test

K1–K3: **yapılmadı** — light ve AI boş ekranı yok; 2560 CachyOS yan yana değil. Kanıtsız
"geçti" yazılmaz.
