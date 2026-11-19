# Arkadaşa mesaj (kopyala-yapıştır) — v0.3

> Parametral OS roadmap **v0.3** hazır: senin v0.2 düzenlemen + iki teknik hata düzeltmesi + F hattı.
>
> Düzeltmeler:
> 1. B1 — nix store sandbox'ta `ro`; yazmayı dışarıdaki `nix-daemon` yapıyor, sandbox'a sadece
>    daemon soketi bind ediliyor (`NIX_REMOTE=daemon`). "ro store içinde `nix profile install`"
>    çalışmaz, doğrusu bu.
> 2. B2 — `--no-build` diye bir flag yok; cache-only `--option builders '' --option substituters
>    https://cache.nixos.org --option require-sigs true`.
> 3. C1 — iş dosyası artık **approver** anahtarıyla imzalanıyor (harddeny anahtarı ayrı kaldı).
>    Yanlış anahtarla imzalı iş reddediliyor ve bu bir test kriteri.
>
> Yeni: F hattı (10 × ~100M uzman + deneyim deposu şeması F0), A5 kapasite sondajı, B5
> home-manager, D5 uygulama bazlı ağ izni, manifest izin alanları (`network`/`write_dirs`/`ipc`),
> `linux-lts` yedek, AUR + kısmi pacman yasağı.
>
> Kararlar kapandı: flakes + `flake.lock`, ayrı `ai` ve `approver` uid, off-host imzalı audit
> anchor, prototipte KDE, LUKS varsayılan, Secure Boot sonra. Marka: **Parametral OS**.
>
> Senden bu hafta: (1) API v1.2 client akışı (`docs/API-v1.md`), (2) **F0 deneyim deposu şeması**
> üzerinde ortak karar — alanlar: `{ts, node_id, niyet, adımlar, araç çağrıları, sonuç, hata,
> geri bildirim, kaynak}`.
>
> Repo: https://github.com/EgeDevCat/parametral-os (private — collaborator olarak eklenmen lazım)
> Roadmap: `docs/ROADMAP.md` · Sözleşme: `docs/API-v1.md`

## Bizim tarafta durum (arkadaşa özet)

- Phase 1 bitti: gateway (JSON-RPC v1.2), policy (default deny), token, onay kapısı, audit zinciri,
  bwrap sandbox + kendi seccomp guard'ı + cgroup v2, exec/fs API, tier-2 oracle (Ed25519,
  SO_PEERCRED, runtime watch, fail-closed), btrfs snapshot/restore.
- 133 test geçiyor; izolasyon probu PASS; iki gerçek süreçle smoke OK.
- Sıradaki: B1 (nix-daemon soketli sandbox) + C1 (approver imzalı iş dosyası, sysapply).
