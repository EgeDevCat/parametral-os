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

```
T11 — check_visual.py + kör test
  Devreden: B (opencode oturumu 1)    Devralan: B (opencode oturumu 2, worktree ../pt-T11)
  Tarih: 2026-11-20 12:24
  Ne denendi: `opencode run --auto` ile T0+T11 tek oturumda; T0 commit edildi (bdbb5f1),
    check_visual.py yazıldı, ardından oturum 12:24'te durdu (log 9044 B'de sabit, %0 CPU).
  Hata/çıktı: `python3 scripts/check_visual.py docs/previews/T6-after-1280x800-dark.png --surface bar`
    → bar {'top': 0, 'bottom': 147, 'height': 148} · failures: edge, bar-height, bar-top-gap · rc=1
  Nerede kalındı: scripts/check_visual.py (bar bölgesi tespiti duvar kağıdı ızgarasını yakalıyor),
    tests/test_check_visual.py ve docs/coordination/REVIEW-T6.md yok.
  Devralanın ilk adımı: bar bölgesini `surface` token rengine göre satır taramasıyla bul, sonra test.
```
