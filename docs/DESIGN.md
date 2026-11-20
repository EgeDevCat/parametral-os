# Tasarım Sistemi — ÖLÇÜM PLAKASI

> Tek cümle: **Sıcak grafit üzerine ince çizgili bir ölçüm plakası; makine verisi mono, insan
> cümlesi sakin; tek canlı sinyal amber.**
>
> Hissiyat: sessiz · ölçülü · sıcak · kesin.
> Anti-hissiyat: oyuncu, neon, "rice", kurumsal SaaS, macOS taklidi, cam/gradyan.

Bu dosya sayısız cümle kabul etmez. Her kuralın bir punto, px, ms veya kontrast oranı vardır.
Kaynak: `branding/tokens.json` → `scripts/gen_theme.py` → `shell/Theme.js` + Noctalia paleti.
Elle hex/px yazılmaz; sapma varsa §13'te satırı olur.

Sahip: B (spec) · Uygulayan: A · Denetleyen: B · Son söz: kullanıcı.
Sürüm: T0, 2026-11-20.

---

## 1. Sanat yönü ve tek imza

### 1.1 Tek imza — CETVEL ÇİZGİSİ

Bar **tek bir plakadır**; yüzen üç pill değil. Plakanın alt kenarında **2 px** kalınlığında bir
cetvel çizgisi vardır. Workspace'ler bu çizgi üzerinde **tik işaretleridir**:

| öğe | ölçü | renk |
|---|---|---|
| cetvel çizgisi | 2 px, plakanın alt kenarı, tam genişlik | `hairline` (muted %14) |
| pasif tik | 6 × 2 px, `radiusTick` 1 px | `faint` (#7C8592) |
| dolu/pasif-olmayan tik | 6 × 2 px | `muted` (#9AA4B2) |
| aktif tik | 14 × 2 px | `amber` (#E0A93B) |
| tik arası | 8 px (4 px taban; 8 kullanılır) | — |
| tik → cetvel alt kenarı | 0 px (tik çizginin üstünde oturur) | — |

Kurallar:

- Cetvel ve tik **yalnız barda** kullanılır. Panelde, launcher'da, kilitta, duvar kağıdında
  ikinci bir cetvel/tik motifi yoktur.
- Aktif tik **tek amber dolgudur**. Aynı ekranda amber bir düğme/aktif satır daha varsa biri
  kaldırılır (§4.3).
- Duvar kağıdındaki ızgara aynı dili konuşur: 1 px, düşük kontrast, amber yok.
- Cetvel çizgisi dekor değil, ölçüm vaadidir: workspace sayısı 5'tir, tikler 1–5'tir. Boş
  workspace gizlenmez; pasif tik olarak durur.

### 1.2 Bar yerleşimi

| ölçü | 1280×800 | 2560×1440 |
|---|---|---|
| yükseklik | 40 px | 40 px (**asla ölçeklenmez**) |
| üst boşluk | 6 px | 6 px |
| yan boşluk | 8 px | 12 px |
| iç yastık | 10 px | 10 px |
| küme arası | 6 px | 6 px |
| ikon | 16 px | 16 px |
| panel yarıçapı | 12 px | 12 px |
| küme ayırıcı | 1 px hairline, dolgu değil | aynı |

Bar tek plakadır: kümeler arasında ayrı "island" kutuları, pill'ler, ikinci bir zemin yoktur.
Plaka rengi `surface` (#12171E); üstünde hairline dışında kenarlık yoktur.

> Uygulama notu (A): plaka şu an duvar kağıdına gömülü çiziliyor. Bu, bar şeffaf olduğu için
> çalışıyor ama plaka artık bir UI yüzeyi değil, duvar kağıdı verisidir. Kabul: plaka rengi
> pikselde `#12171E` (±2), yüksekliği 40 px, üst boşluğu 6 px ölçülür. Duvar kağıdı
> değişirse bar da değişir — bu bir sapma, §13'te kayıtlı.

---

## 2. Kahraman ekranlar

Önizleme setinde bu üçü **birinci sırada** yer alır. Ürünün karakteri boş durumda belli olur.

### 2.1 "Ajan yok" (AI tarafı bozukken)

- Display **26/32**, Inter 500: `Ajan yok`
- Gövde **13/20**, Inter: `Bu makinede çalışan bir ajan yok. Durum aşağıda; uydurma bir "bağlı" yok.`
- Üç satır, **40 px** satır yüksekliği, mono **11/16** etiket + değer:
  - `model` — `yok`
  - `gateway` — `yok`
  - `oracle` — `yok`
- Tek öneri (amber **metin**, dolgu değil): `Bağlantıyı kur` + tek satır açıklama.
- Sağ üstte canlı sinyal yok; hata rengi yalnız gerçek hatada.
- Veri kaynağı: gerçek durum dosyası/komutu. Veri yoksa `bilinmiyor` yazılır, `bağlı` yazılmaz.

### 2.2 Boot güven raporu

- Display **26/32**: `Boot güven raporu`
- Dört satır, mono değerler, 40 px:
  - `kurallar imzası` — `doğrulandı` (yeşil nokta 6 px + metin)
  - `oracle` — `yok` (kırmızı nokta + metin)
  - `audit head` — `3f2a…9c1d` (mono, tabular)
  - `gateway` — `kapalı`
- Tarih **11/16** mono: `20 Kasım 2026 Cuma`
- Display yalnız burada ve §2.1 başlığında kullanılır; üçüncü bir yerde yok.

### 2.3 Launcher boş durumu

- Genişlik **520 px**, girdi satırı **48 px**, sonuç satırı **36 px**, max yükseklik **480 px**.
- Mark **16 px** (12 tikli varyant 16 px'te kullanılmaz).
- Başlık **17/24**: `Sonuç yok`
- Tek öneri: `«ara» için uygulama bulunamadı — uygulamaları kur`
- Madde işareti yok, iki dilli uyarı yok, ham hata metni yok.

---

## 3. Tipografi

### 3.1 Aileler

| rol | aile | paket (Arch) | kapı |
|---|---|---|---|
| gövde, başlık | **Inter** | `inter-font` | `fc-match Inter` → `Inter` |
| makine verisi, sayı, kimlik, hash | **IBM Plex Mono** | `ttf-ibm-plex` | `fc-match "IBM Plex Mono"` → `IBM Plex Mono` |

Fallback yakalanırsa iş **blocked**; fallback ile ekran görüntüsü alınmaz ve review'a girmez.
Kapı komutu ve çıktısı review dosyasına yapıştırılır.

### 3.2 Ölçek (1280×800 taban)

| rol | punto / satır | ağırlık | aile | kullanım |
|---|---|---|---|---|
| meta | 11 / 16 | 400 | Inter | etiket, tarih, yardım |
| mono meta | 11 / 16 | 400 | IBM Plex Mono | sayı, yüzde, hash, kimlik |
| gövde | 13 / 20 | 400 | Inter | cümle, açıklama |
| başlık | 17 / 24 | 500 | Inter | panel başlığı, launcher başlığı |
| display | 26 / 32 | 500 | Inter | **yalnız** boot raporu + boş durum başlığı |

- Bir ekranda en fazla **3 punto**.
- Sayılar her yerde tabular: mono veya `font-feature-settings: "tnum"`.
- Saat **17/24** (26 bold yasak); tarih **11/16** muted; ikisi aynı ağırlıkta değil.
- Yüzde işareti önde: `%40`. Binlik `.`, ondalık `,`: `1.280`, `%99,5`.
- Tarih tek biçim: `20 Kasım 2026 Cuma` (`d MMMM yyyy EEEE`, `tr_TR`). Bar, kilit, kontrol
  merkezi aynı.
- `text-transform: uppercase` **yasak** (Türkçe `i` → `İ`; locale'siz büyütme `I` üretir).
  Ay/gün adları yazıldığı gibi: `Kasım`, `Cuma`.
- Kelime markası `PARAMETRAL` bir logodur, metin değildir; yalnız kilit ekranındaki lockup'ta
  yer alır ve havada durmaz.

---

## 4. Renk

### 4.1 Karanlık (ölçülmüş)

| token | hex | üstünde | oran | kullanım |
|---|---|---|---|---|
| `bg` | `#0B0F14` | — | — | sayfa |
| `surface` | `#12171E` | — | — | bar, panel |
| `card` | `#1A2029` | — | — | kart, satır |
| `cardHover` | `#222B36` | — | — | hover |
| `text` | `#E9E4D8` | bg | **15,15:1** | gövde |
| `muted` | `#9AA4B2` | surface | **7,14:1** | ikincil |
| `faint` | `#7C8592` | surface | **4,82:1** | pasif tik, meta |
| `amber` | `#E0A93B` | surface | **8,49:1** | tek canlı sinyal |
| `primaryText` | `#E0A93B` | surface | 8,49:1 | metin amber'i (karanlıkta amber) |
| `onPrimary` | `#1A150A` | amber | **8,57:1** | amber dolgu üstü metin |
| `danger` | `#D66056` | surface | **4,86:1** | red |
| `ok` | `#7EAE68` | surface | **6,98:1** | doğrulandı |
| `line` | `#2A323C` | — | — | hairline/kenar |

**Düzeltme (T0):** eski `faint` `#6B7280` surface üstünde **3,72:1** idi — AA altı. Yeni değer
`#7C8592` = **4,82:1**. Bu bir zevk değişikliği değil, ölçüm.

### 4.2 Açık (iki amberli ayrı tema)

| token | hex | üstünde | oran | kullanım |
|---|---|---|---|---|
| `light.surface` | `#F4EFE6` | — | — | sayfa/panel |
| `light.card` | `#EAE2D5` | — | — | kart |
| `light.text` | `#1E2228` | surface | **13,95:1** | gövde |
| `light.muted` | `#5C5852` | surface | **6,17:1** | ikincil |
| `light.faint` | `#625D55` | surface | **5,70:1** | meta |
| `light.primary` | `#B8862B` | surface | **2,83:1** | **yalnız dolgu** |
| `light.primaryText` | `#8A5F14` | surface | **4,92:1** | amber **metin/ikon/çizgi** |
| `light.onPrimary` | `#1A150A` | primary | **5,61:1** | dolgu üstü metin |
| `light.danger` | `#A2564A` | surface | **4,62:1** | red |
| `light.ok` | `#4F7A3F` | surface | **4,38:1** | **yalnız işaret/nokta** (metin değil) |
| `light.line` | `#CFC3AD` | — | — | hairline |

- Açık mod "karanlığın tersi" değildir; iki amber'i olan ayrı bir temadır.
- `primary` (#B8862B) metin olarak **kullanılamaz**; metin `primaryText` (#8A5F14).
- `onPrimary` açıkta `#1A150A`'dır. `#FFF8EC` primary üstünde **3,07:1** — AA değil.
- `light.ok` metin olarak kullanılmaz (4,38:1). Yeşil yalnız "doğrulandı" işaretidir.

### 4.3 Amber disiplini

- Amber **tek canlı sinyaldir**; dekor değildir.
- Bir ekranda en fazla **bir amber dolgu**: ya bir düğme ya bir aktif satır. İkisi birden olamaz.
- Amber dolgu üstüne `onPrimary` yazılır.
- Duvar kağıdında amber yok.
- Mavi **UI rolü değildir**. Terminal ANSI paletindeki mavi veridir, arayüz değildir.
- Kırmızı yalnız red, yeşil yalnız doğrulama. "Renkli durum" yok.

---

## 5. Izgara ve geometri

### 5.1 Boşluk

4 px taban. İzinli değerler: **4 / 8 / 12 / 16 / 24 / 32 / 48**. Başka değer yok.

Tek istisna barın kendi ölçüsüdür: üst boşluk 6, iç yastık 10, küme arası 6. Bu üç sayı
§1.2'de ölçülmüş ve sabittir; panel/kart/launcher bu istisnayı kullanmaz.

### 5.2 Yarıçap

| öğe | token | px |
|---|---|---|
| tik | `radiusTick` | 1 |
| satır | `radiusRow` | 8 |
| panel / kart / bar / pencere | `radiusPanel` | 12 |
| pill (yalnız gerçek pill) | `radiusPill` | 999 |

Kart 14 ise 12'ye çekilir. Tek dil: 12. Hyprland `rounding` da 12'dir (şu an 14 — borç).

### 5.3 Panel

| ölçü | 1280 | 2560 |
|---|---|---|
| genişlik | 420 | 480 |
| yastık | 16 | 16 |
| satır | 40 | 40 |
| başlık | 32 | 32 |
| yarıçap | 12 | 12 |

### 5.4 Launcher

Genişlik 520 · girdi 48 · sonuç satırı 36 · max yükseklik 480 · boşluk 8 · yarıçap 12.

### 5.5 Gölge

Tek gölge: `0 8px 24px rgba(0,0,0,0.08)`. Başka gölge, glow, kenarlık+glow kombinasyonu yok.
Açık modda gölge aynı geometri, `shadowAlpha` 0,08; renk `#D8CDBB` (Noctalia paleti).

### 5.6 Pencere (Hyprland)

`rounding 12` · `border_size 2` · aktif kenar amber, pasif `line` · `gaps_in 8` · `gaps_out 12`.
Şu anki 14/14/6 değerleri borçtur; 12/12/8'e çekilir. `blur` açık kalabilir ama pencere
arkasında cam efekti taklidi yok.

### 5.7 Duvar kağıdı

- Izgara + kadran. **Metin yok.** Wordmark havada durmaz.
- Kontrast düşük: pencere/bar okunsun. Ölçüm: duvar kağıdı pikselinin `bg`'ye uzaklığı
  ortalama < 12/255; en parlak çizgi `muted`ın %35'ini geçmez.
- Amber yok.
- 1280×800, 1920×1080, 2560×1440; light ve dark varyantı.

---

## 6. Hareket

| olay | süre | eğri |
|---|---|---|
| hover | 120 ms | `cubic-bezier(0.2, 0, 0, 1)` |
| panel aç/kapa | 180 ms | aynı |
| diğer | yok | — |

- Yalnız `opacity` + **4 px** dikey kayma. Genişlik/yükseklik animasyonu yok.
- Yay/bounce/spring yok.
- `reduced-motion` → **0 ms**.
- Hiçbir yerde sonsuz animasyon yok (nabız dahil). Spinner yalnız gerçek bekleyişte.
- Hyprland animasyon eğrisi de aynı aileye çekilir; mevcut `(0.2,0.9)(0.2,1)` borç.

---

## 7. Durumlar

Her yüzey için beş durum tasarlanır; boş beyaz kutu yok.

| yüzey | boş | dolu | hata | çevrimdışı | aşırı yük |
|---|---|---|---|---|---|
| bar | tikler pasif, saat/tarih var | aktif tik amber | tek satır + kırmızı nokta | ağ noktası `faint` | değer `—`, spinner yok |
| panel | başlık + tek öneri | satırlar 40 px | satır + neden + tek eylem | "ağ yok" + son deneme | "çok fazla istek" + bekle |
| launcher | mark 16 + "Sonuç yok" | 36 px satırlar | "Arama başarısız" + tek eylem | "çevrimdışı dizin" | ilk 20 sonuç, "daha fazla" |
| kilit | — | saat + tarih + alan | yanlış şifre: kırmızı cümle | — | — |
| AI | §2.1 | gerçek veri | gerçek hata | gateway yok | kuyruk |
| snapshot | "henüz snapshot yok" | liste | rollback hatası | — | — |

AI tarafı için üç ayrı "yok" ekranı vardır ve üçü de **gerçek veriden** beslenir:

- **model yok** — model listesi boş; `bağlı` yazılmaz.
- **gateway yok** — gateway sağlık kontrolü başarısız; son deneme saati mono.
- **oracle yok** — oracle anahtarı/yanıtı yok; "doğrulanmadı" yazar.

---

## 8. Görsel çıta (30 üzerinden, en az 24; hiçbir maddede 0 yok)

| # | madde | 3 | 2 | 1 | 0 |
|---|---|---|---|---|---|
| 1 | Hiyerarşi | tek bakışta 1 baskın, 1 ikincil, gerisi sessiz; ≤3 punto | ikincil zayıf | iki baskın | hiyerarşi yok |
| 2 | Izgara | 4/8 ritmi; bar/panel/kart aynı dil | bir yerde 2 px kaçak | keyfi boşluk | ızgara yok |
| 3 | Tipografi **[KAPI]** | Inter + IBM Plex Mono gerçekten yüklü; fallback yok | bir yerde yanlış aile | fallback şüphesi | fallback |
| 4 | Renk **[KAPI]** | amber tek sinyal, tek dolgu; mavi yok; oranlar ölçülü | bir fazla amber vurgu | iki dolgu | mavi/neon |
| 5 | Durumlar | 5 durum + 3 "yok" ekranı | biri eksik | iki eksik | boş beyaz kutu |
| 6 | Dil | Türkçe, doğru büyük harf, `%40`, tek tarih, ham stderr yok | bir sapma | iki sapma | üç+ |
| 7 | İkon | tek stroke seti, 16 px'te okunur | bir ikon farklı | karışık set | ikonsuz çıplak yüzde |
| 8 | Erişilebilirlik | AA, görünür odak, tam klavye, reduced-motion | odak zayıf | AA altı bir metin | klavye yok |
| 9 | Dürüstlük **[KAPI]** | olmayan veri yok; "yok" ekranları kahraman | bir yerde tahmin | uydurma değer | sahte "bağlı" |
| 10 | Kimlik | stock Noctalia/CachyOS paleti/logosu/duvar kağıdı kalmaz | bir stock öğe | iki stock öğe | stock tema |

Puanlama: B yazar, A itiraz ederse kanıtla. 2 turdan sonra zevk kararını kullanıcı verir.
24 altı veya herhangi bir 0 → iş "done" olamaz.

---

## 9. Yasak desenler

Biri görülürse iş review'a bile girmez:

ham hata metni · `[!]` kutusu · iki dilli uyarı · ikonsuz çıplak yüzde · 26 px bold saat ·
tarih saatle aynı ağırlıkta · tam amber dolgu seçim satırı · launcher'da madde işareti ·
havada duran wordmark · glassmorphism · neon · gradient mesh · "düşünüyor..." · robot avatar ·
1280×800'de taşma · 3 saniyede okunmayan ekran.

---

## 10. Ölçüm — `scripts/check_visual.py`

B yazar; Python **stdlib + zlib**, bağımlılık yok. PNG'yi kendisi çözer.

```
python3 scripts/check_visual.py <png> [--surface bar|panel|launcher|desktop] [--json]
```

| metrik | eşik | kapsam |
|---|---|---|
| `amber_piksel_orani` | ≤ %1,2 (bar) · ≤ %2,0 (tam masaüstü) | yalnız bar / tüm ekran |
| `palet_disi_orani` | ≤ %5 | token renklerine uzaklık; duvar kağıdı hariç |
| `siyah_orani` | ≤ %35 | ekran "kara delik" olmayacak |
| `kenar_boslugu` | ≥ 8 px | UI yüzeylerinde içerik ekran kenarına yapışmaz |

Algoritma (T11'de uygulanır):

1. PNG'yi RGB'ye çöz; alfa varsa `bg` üstüne bindir.
2. Her pikseli en yakın token rengine ata (RGB Öklid; eşik 24/255). Duvar kağıdı bölgesi
   `--surface desktop` dışında sayılmaz.
3. `amber`: `amber`/`light.primary`/`light.primaryText` kümesine 24/255'ten yakın pikseller.
4. `siyah`: `max(r,g,b) < 24`.
5. `kenar_boslugu`: UI yüzeyinde içerik maskesinin (token rengine yakın olmayan pikseller)
   ekran kenarına uzaklığı; bar için bar plakasının üst/sol/sağ kenarı.
6. Eşik aşılırsa çıkış kodu 1; rapor review dosyasına eklenir.

Eşik aşılırsa "güzel" tartışılmaz; düzeltilir.

Ek ölçümler (aynı script): `bar-yuksekligi` = 40 (±1), `bar-ust-boslugu` = 6 (±1),
`amber-tick` = en geniş amber koşu ≥ 12 px (aktif tik 14). `siyah` = `max(r,g,b) ≤ 8`
(saf siyah); token `bg` #0B0F14 sayılmaz — yoksa karanlık tema yanlışlıkla "kara delik" olur.

---

## 11. Kör test (A yapar, B değerlendirir, kullanıcı hakem)

- **K1** — 2560×1440 Parametral ve CachyOS/Noctalia yan yana, etiketsiz. Projeyi bilmeyen biri
  "hangisi ürün, hangisi dağıtım varsayılanı?" sorusuna CachyOS derse **başarısız**.
- **K2** — Logo kapat. Hâlâ bizim mi? Cetvel çizgisi + mono etiketler + sıcak grafit okunmalı.
- **K3** — 3 saniye göster, kapat. Beklenen tek cümle: **"sakin bir makine paneli"**.
  "Renkli bir bar" cevabı **başarısız**.

Sonuç tek satır yazılır: `K1: geçti · K2: geçti · K3: geçti` + tarih + kişi.

---

## 12. Tasarım kapısı

1. **B spec yazar** — bu dosyada ilgili bölüm + kabul kriterleri; sayılar.
2. **A uygular** — 1280×800 + 2560×1440, light + dark, en az boş/dolu/hata; doğal çözünürlük,
   küçültmesiz; kırpma varsa "detay" etiketi.
3. **B puanlar** — `docs/coordination/REVIEW-<id>.md`: "ekran bölgesi — kusur — neden — puan".
   Üç kusur bulunamazsa gerekçe yazılır.
4. **A düzeltir veya kanıtla itiraz eder** — aynı işte 2 turdan sonra zevk kararını kullanıcı verir.
5. **"done"yu A yazar** — yalnız B'nin review dosyası, `check_visual` raporu ve önce/sonra
   görüntüleri varsa.

Kanıt yolları: `docs/previews/<id>-before.png`, `<id>-after.png`; `docs/coordination/REVIEW-<id>.md`.

---

## 13. Sapma kaydı

Gizli sapma = kanıtsız iddia. Noctalia/Hyprland bir şeyi yapamıyorsa buraya satır eklenir;
denetçi sapmanın dürüstlüğünü kontrol eder, güzelliğini değil.

| yüzey | spec | gerçek | neden | geçici mi |
|---|---|---|---|---|
| açık mod amber metin | `primaryText` #8A5F14 ayrı token | Noctalia v2'de text-only primary rolü yok; `primary` = #8A5F14 | palet şeması | kalıcı; upstream issue |
| açık mod amber dolgu | `primary` #B8862B dolgu | Noctalia'da #B8862B dolgu yok | aynı şema | kalıcı |
| bar plakası | `surface` token, shell çizer | duvar kağıdına gömülü 40 px plaka | Noctalia bar zemini şeffaf | geçici; upstream |
| bar workspace sayısı | 5 tik (boşlar pasif) | 3 tik görünür | Noctalia boş workspace'i gizliyor | geçici; config |
| pencere yarıçapı | 12 | 14 | Hyprland config | geçici (T6/T7) |
| pencere boşluğu | 8/12 | 6/14 | Hyprland config | geçici (T6/T7) |
| animasyon eğrisi | `(0.2,0,0,1)` | `(0.2,0.9)(0.2,1)` | Hyprland curve | geçici (T7) |
| bar iç ölçüsü | 4/8 ölçeği | 6/10 | §1.2'de ölçülmüş bar istisnası | kalıcı (spec) |
| açık mod yeşil | `ok` metin değil | #4F7A3F 4,38:1 | yeşil yalnız işaret | kalıcı (spec) |
| duvar kağıdı bar geometrisi | token'dan okunur | `make_wallpaper.py` sayıları kopyalıyor | betik henüz token okumuyor | geçici (T6) |

**Düzeltilen bulgular (T0):**

| bulgu | önce | sonra | kanıt |
|---|---|---|---|
| karanlık `faint` AA altı | #6B7280 = 3,72:1 | #7C8592 = 4,82:1 | `tests/test_theme_tokens.py` |
| açık `on_primary` AA altı | #FFF8EC = 3,07:1 | #1A150A = 5,61:1 | aynı |
| açık `primary` metin olarak | #B8862B = 2,83:1 | metin `primaryText` #8A5F14 = 4,92:1 | aynı |
| Noctalia `secondary` mavi | #6C9BC4 | #9AA4B2 (muted) | `Parametral.json` + test |
| bar token'ı 56 px | 56 | 40 | `tokens.json` + test |

---

## 14. Token haritası

```
branding/tokens.json
  ├── scripts/gen_theme.py ──► shell/Theme.js ──► shell/*.qml
  ├── branding/noctalia/palettes/Parametral.json  (projeksiyon; test eşitliği zorunlu)
  ├── scripts/make_wallpaper.py                    (bar geometrisi token'dan okunmalı)
  └── docs/DESIGN.md                               (bu dosya; sayılar buradan)
```

- Renk, punto, boşluk, süre: yalnız `tokens.json`. QML'de hex yok (`test_no_hex_literals_in_qml`).
- Noctalia paleti token'ların projeksiyonudur; elle ayrı palet yok (`NoctaliaPalette` testi).
- Yeni token eklemek: `tokens.json` → `gen_theme.py` gerekirse → test → `Theme.js` üret.
- `shell/Theme.js` üretilmiş dosyadır; elle düzenlenmez.

---

## 15. Yüzey kabul kriterleri

### 15.1 Bar (T6)

- [ ] Yükseklik **40 px**, iki çözünürlükte de; üst boşluk 6, yan 8/12, iç yastık 10, küme arası 6.
- [ ] Tek plaka; yüzen island/pill yok. Kümeler arası 1 px hairline.
- [ ] Alt kenarda 2 px cetvel; 5 workspace tiki (6×2), aktif 14×2 amber.
- [ ] Mavi yok; pasif tik `faint`/`muted`, aktif amber.
- [ ] Saat 17/24, tarih 11/16 muted, tarih `20 Kasım 2026 Cuma`.
- [ ] Yüzdeler ikonlu ve önde `%40`; ikon 16 px tek stroke seti.
- [ ] Amber dolgu ekranda tek (aktif tik). Launcher mark'ı 16 px ve net.
- [ ] 1280×800 ve 2560×1440, dark + light; taşma yok.
- [ ] `check_visual` bar: amber ≤ %1,2; palet dışı ≤ %5; siyah ≤ %35; kenar ≥ 8 px.
- [ ] Önce/sonra: `docs/previews/T6-before-*.png` / `T6-after-*.png`.
- [ ] `fc-match` çıktısı Inter + IBM Plex Mono.

### 15.2 Panel (T6/T3)

- [ ] 420/480 px, yastık 16, satır 40, başlık 32, yarıçap 12.
- [ ] Beş durum + AI "model/gateway/oracle yok" ekranları gerçek veriden.
- [ ] Tek gölge; glow yok.
- [ ] Açık modda metin amber'i `primaryText`; `primary` yalnız dolgu.

### 15.3 Launcher

- [ ] 520 px, girdi 48, satır 36, max 480, boşluk 8.
- [ ] Boş durum: mark 16 px + `Sonuç yok` + tek öneri; madde işareti yok.
- [ ] Mark 12 tikli varyant 16 px'te kullanılmaz.

### 15.4 Kilit (T1)

- [ ] Yanlış şifre: kırmızı cümle, alan kenarı `danger`, odak kaybolmaz.
- [ ] Caps-lock: amber uyarı, Türkçe, tek satır; ham stderr yok.
- [ ] Saat **17/24** (26 bold yasak; display yalnız boot raporu + boş durum başlığı).
      Tarih 11/16 mono.
- [ ] Tarih `20 Kasım 2026 Cuma`; `PARAMETRAL` yalnız lockup'ta, havada değil.

### 15.5 AI boş durum (T3/T10)

- [ ] §2.1'deki üç satır gerçek veriden; `bağlı` uydurulmaz.
- [ ] Display yalnız başlıkta; gövde 13/20; mono değerler tabular.
- [ ] Tek amber metin önerisi; amber dolgu yok.

### 15.6 KDE Plasma — birincil hat (T12)

Kullanıcı kararı 2026-11-20: KDE Plasma birincil masaüstü; Hyprland/Noctalia ikincil/deneysel.
KDE "başka bir tema" değil, aynı Ölçüm Plakası'nın Plasma karşılığıdır.

- [ ] `branding/kde/Parametral.colors` ve `ParametralLight.colors` **token'lardan** üretilir;
      elle hex yok. Renk şeması ↔ `tokens.json` eşitliği test edilir.
- [ ] Stock Breeze paleti, mavi vurgu, stock duvar kağıdı, stock logo kalmaz. `Breeze` yalnız
      ikon fallback'i olabilir; palet olamaz.
- [ ] Panel: yükseklik **40 px**, üst boşluk 6, yan 8, iç yastık 10, küme arası 6, ikon 16.
      Panel tek plaka; cetvel çizgisi + 5 tik (6×2 / aktif 14×2) KDE panelinde de aynı.
- [ ] Kickoff/launcher mark **16 px**, amber değil; amber yalnız aktif tik.
- [ ] Saat 17/24, tarih 11/16 mono, `20 Kasım 2026 Cuma`; `%40` biçimi.
- [ ] SDDM: Parametral tema, aynı palet, doğru şifre + yanlış şifre durumu.
- [ ] Konsole `Parametral.colorscheme` token'lardan; ANSI mavi veri, UI mavisi değil.
- [ ] AI approvals + snapshot penceresi KDE oturumunda çalışır; `pkexec` ajanı gerçekten yanıtlar.
- [ ] 1280×800 + 2560×1440, light + dark, boş/dolu/hata; `check_visual` temiz.
- [ ] KDE oturumu ile Hyprland/Noctalia aynı anda çalışmaz (çift bar yok).
- [ ] `make test` OK; `docs/previews/T12-*.png` + `REVIEW-T12.md`.

### 15.7 SFT izleri (T13)

AI yüzeyi aynı zamanda SFT veri kaynağıdır. Ekranda görünen her durum, kayıtta aynı adla ve
gerçek değerle durur; uydurma etiket veri setini zehirler.

- [ ] Kayıt `audit.jsonl` / `v1.audit.query` türevidir; elle yazılmış örnek yok.
- [ ] Alanlar: `ts` (ISO, saniye), `surface`, `state` (`ok|no_model|no_gateway|no_oracle|error|
      offline|overload`), `model`, `gateway`, `oracle`, `audit_head`, `action`, `outcome`,
      `locale` (`tr_TR`), `viewport`.
- [ ] Eksik değer `null`; `bağlı`/`hazır` yalnız gerçek probe başarılıysa.
- [ ] Sır/anahtar/parola yok; kullanıcı metni redakte edilir.
- [ ] Her ekran görüntüsü bir `event_id` ile eşlenir; review'da ikisi birlikte.
- [ ] Şema testi: zorunlu alanlar, enum, `null` disiplini; `tests/test_sft_trace.py`.

---

## 16. Review protokolü

`docs/coordination/REVIEW-<id>.md` şablonu:

```md
# REVIEW <id> — <başlık>
Tarih: YYYY-MM-DD HH:MM · Denetleyen: B · Görüntüler: <yollar>
Spec: docs/DESIGN.md §<bölüm> · check_visual: <rapor>

## Bulgular
| bölge | kusur | neden (spec) | puan |
|---|---|---|---|
| bar / sol küme | ... | §1.2 ... | 1 |

## Çıta
1 Hiyerarşi 3 · 2 Izgara 3 · ... · 10 Kimlik 3 → **27/30**

## Karar
review | blocked | done (done'yu A yazar)
```

Üç kusur bulunamazsa: "üçüncü kusur yok çünkü ..." gerekçesi yazılır; boş bırakılmaz.
