# Devir (handoff) kaydı

Şablon:

```
<id> — <başlık>
  Devreden: A|B    Devralan: B|A    Tarih: YYYY-MM-DD HH:MM
  Ne denendi: (madde madde, komutlar dahil)
  Hata/çıktı: (tam son satırlar, dosya:satır)
  Nerede kalındı: (dosya:satır)
  Devralanın ilk adımı: (tek cümle)
```

## Kayıtlar

_(henüz yok)_

```
T11 — check_visual.py + kör test
  Devreden: B (opencode oturumu 1)    Devralan: B (opencode oturumu 2, worktree ../pt-T11)
  Tarih: 2026-11-20 12:24
  Ne denendi: T0+T11 tek oturumda; T0 commit edildi (bdbb5f1); check_visual.py yazıldı;
    oturum 12:24'te durdu.
  Hata/çıktı: bar bölgesi tespiti duvar kağıdı ızgarasını yakaladı:
    bar {'top': 0, 'bottom': 147, 'height': 148} · failures: edge, bar-height, bar-top-gap.
  Nerede kalındı: scripts/check_visual.py (bar bölgesi).
  Devralanın ilk adımı: bar bölgesini surface token rengine göre satır taramasıyla bul.

  ÇÖZÜLDÜ — 2026-11-20 12:50, B oturum 2
  Yapılan: bar bölgesi 3 ardışık surface satırı + bg'ye kadar tarama; 7 test; REVIEW-T6.
  Kanıt: feat/T11 63b0e55 · `make test` 255 OK · `check_visual` 2560 plaka 40 px.
  Kalan: K1–K3 (T10/A görüntüleri); kör test kanıtsız yazılmaz.
```
