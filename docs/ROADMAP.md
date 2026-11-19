# Parametral OS — Roadmap v0.3 (birleştirilmiş)

v0.2 (arkadaşının düzenlemesi) + v0.2'deki iki teknik hatanın düzeltmesi + F hattı + kararlar.
Marka adı **Parametral OS**; `parametrald`, `parametral-harddeny`, `hard_deny.v1.json` gibi teknik adlar kod
adı olarak kalıyor (her yerde yeniden adlandırma churn'ü yok, marka sonra oturur).

## v0.3'te değişen (izlenebilirlik)

| # | değişiklik | kaynak |
|---|---|---|
| 1 | **B1 düzeltildi:** nix store sandbox'a `ro` bind edilir, yazmayı sandbox dışındaki `nix-daemon` yapar; sandbox'a yalnız daemon soketi bind edilir (`NIX_REMOTE=daemon`). "ro store içinde `nix profile install`" imkânsızdı. | v0.2 hatası |
| 2 | **B2 düzeltildi:** `--no-build` diye bir nix flag'i yok. Cache-only = `--option builders ''` + `substituters` + `require-sigs true`. | v0.2 hatası |
| 3 | **C1 güvenlik:** iş dosyası **approver** anahtarıyla imzalanır, harddeny anahtarıyla değil. Üç ayrı keypair: harddeny (offline, OS sahibi), approver (onay servisi), job (sysapply doğrular). Yanlış anahtarla imzalı iş reddedilir ve bu bir test kriteridir. | v0.2 düzeltmesi |
| 4 | **F hattı eklendi:** 10 daimi ~100M uzman + deneyim deposu (OS beyni). 80B ayrı ürün, kapsam dışı (E3). | v0.2 eksik |
| 5 | A2 dizin modları: `keys/` **0700**, anahtar dosyaları **0600**. | v0.2 düzeltmesi |
| 6 | A5 kapasite sondajı, B5 home-manager, D5 uygulama bazlı ağ izni, manifest izin alanları, `linux-lts` yedek, AUR yasağı, kısmi pacman yasağı. | v0.2 eklemeleri |
| 7 | Kararlar işlendi: flakes + `flake.lock`, ayrı `ai` ve `approver` uid, off-host audit anchor, prototipte KDE, LUKS varsayılan, Secure Boot sonra. | karar turu |

## Aktörler ve sınırlar

| aktör | sahibi | dokunmaz |
|---|---|---|
| **Sen (OS)** | Arch imajı, btrfs düzeni, systemd unit'leri, `/etc/parametral` sahipliği, kullanıcı ayrımı, KDE prototipi | AI kodu, policy içeriği |
| **Arkadaş (AI)** | model, GC Shield (model içi), araç döngüsü, onay UX'i, deneyim deposuna yazım | kural dosyaları, anahtarlar, politika |
| **Bu katman** | API v1.2, gateway, oracle, sandbox, snapshot, audit, tier-1 doğrulayıcı, F1 runtime | imaj build, model eğitimi |

## Durum (kanıtlı)

- API v1.2 donmuş; **133 test**; izolasyon probu PASS; smoke iki gerçek süreçle OK.
- Oracle: Ed25519 (public-key doğrulama), `SO_PEERCRED`, runtime dosya gözlemi, fail-closed.
- Snapshot: btrfs, root'suz; restore + otomatik `pre-restore` güvenlik snapshot'ı.
- Eksik: `app.install` hattı, host executor'ları, root sahipli anahtarlar, qgroup kota, off-host
  anchor, microVM, F hattı.

## Kritik yol

```
[A*] Arch tabanı ──► [A3] nix-daemon + units ──► [B1] Nix-first install ──► [B2] cache-only
        │                     │                          │
[AI1] API client ─────────────┼──────────► [B3] verify/rollback ──► [B6] manifest izin alanları
                              │
                       [C1] sysapply (approver imzalı iş) ──► [C2] approver uid ──► [C3] restore
                              │
                       [D1] qgroup ─► [D2] audit anchor ─► [D3] CI ─► [D5] app bazlı ağ
                              │
                       [F0] deneyim şeması ─► [F1] 10 uzman runtime ─► [F2] eğitim
                              │
                       [E1] microVM ─► [E2] çok düğüm ─► [E3] 80B = ayrı ürün
```

### A — Arch tabanı (sen; dosyaları ben veriyorum)

| # | iş | "bitti" kanıtı |
|---|---|---|
| A1 | Minimal Arch: btrfs kök, `@`/`@home`/`@var`, systemd-boot, **`linux` + `linux-lts` yedek**, LUKS açık → `install/` kiti hazır | ISO boot; `findmnt /` btrfs; snapshot al→geri dön; LUKS şifreli açılış |
| A2 | Kullanıcılar (kit: `install/40-users.sh`): `operator` (wheel), `parametral` (gateway+oracle), `ai` (hiçbir grupta değil), `approver`. `/etc/parametral` root:root 0755; `keys/` **0700**; `*.pub` 0644, `*.sk` **0600** | `sudo -u ai cat /etc/parametral/keys/hard_deny.ed25519.sk` → **Permission denied**; `.pub` okunur |
| A3 | `parametral-harddeny.service`, `parametrald.service` (`User=parametral`, `ProtectSystem=strict`, `ReadOnlyPaths=/etc/parametral`, `NoNewPrivileges=yes`), **`nix-daemon.service`**; `/etc/nix/nix.conf`: `require-sigs = true`, `sandbox = true`, `trusted-users = root parametral`, `allowed-users = @users` (`ai` trusted değil, kendi substituter'ını ekleyemez) | `parametral status` → `available:true`; `ai` olarak `nix profile list` çalışır; `ai` `nix config` ile substituter değiştiremez |
| A4 | İlk açılışta boş policy + imzalı `hard_deny.v1.json`; public key imajda, private key offline | `parametral harddeny verify` → `verified:true` |
| A5 | İlk açılış **kapasite sondajı** (RAM/CPU/disk/TPM) → kurulum profili: tam / kısmi (F1 uzman sayısı ve sandbox limitleri buna göre) | düşük RAM'li VM'de kısmi profil; rapor `/var/log/parametral/firstboot.json` |
| A6 | AUR yasağı (`makepkg`, AUR yardımcıları tier-2) ve kısmi pacman yasağı (`pacman -U`, `--overwrite` preset dışı) | `paru -S x` ve `pacman -U x.pkg` → `POLICY_DENIED` |

### B — Nix-first kurulum hattı (ben + arkadaş manifest)

| # | iş | "bitti" kanıtı |
|---|---|---|
| B1 | Sandbox'ta `/nix/store` **ro**; `nix-daemon` soketi (`/nix/var/nix/daemon-socket/socket`) sandbox'a bind; `NIX_REMOTE=daemon`. Yazma daemon'da, sandbox ağı kapalı. Profil yazılabilir tek yer: `/work/.nix-profile` | sandbox içinde `nix profile install nixpkgs#ripgrep` başarılı; `curl` hâlâ `ENETUNREACH`; store'a doğrudan yazma `EROFS` |
| B2 | Cache-only: `--option builders '' --option substituters https://cache.nixos.org --option require-sigs true` (`builders` doğru ad; `--no-build` yok). Derleme gerekiyorsa sandbox içinde | ağ kapalıyken cache'ten kurulum; cache'te olmayan paket → dürüst hata, sessiz build yok |
| B3 | Doğrulama + ≤3 deneme: `verify.cmd` exit≠0 ise tekrar; sonunda `state:"failed"` + gerçek stderr | bozuk ref → 3 attempt, `failed`, uydurma yok |
| B4 | Rollback: `nix profile generations` + `--rollback`; snapshot ile çapraz kontrol | kur → boz → rollback → eski `--version` |
| B5 | `host.nix_profile` (tier 0): `home-manager switch`, root'suz, nesil bazlı, onay yok | `home-manager generations` yeni nesil; onay istenmedi |
| B6 | Manifest v1 + **izin alanları**: `network` (host:port), `write_dirs`, `ipc` (izinli sandbox'lar) | doc↔kod kontrat testi geçiyor |

### C — Tier-1 executor (ben; root helper senin imajında)

| # | iş | "bitti" kanıtı |
|---|---|---|
| C1 ✅ | `sysapply` (root): approver imzalı iş dosyası, `hostapply.PRESETS`, önce snapshot. Kod + 10 test (stub pacman). Servis unit'i `install/systemd/` altına eklenecek | `tests/test_sysapply.py`: imzalı iş uygulandı; kurcalanan yük/yanlış anahtar/`sh -c`/snapshot hatası reddedildi |
| C2 | `approver` ayrı uid, Ed25519 anahtar 0600; onay + iş imzalama (`parametral host sign`) | `ai` onay anahtarını okuyamıyor; onaysız tier-1 yok |
| C3 | Geri alma: `snapshot.restore` ile `@` snapshot'ı | paket eski haline döndü |
| C4 | Kısmi pacman yasağı preset'te kilitli: `-U`, `--overwrite` yok | test: `pacman -U` → red |

**Kural:** root helper genel komut çalıştırmaz; preset listesi + imzalı iş dosyası. Onaylı bir
tier-1 işleminin içine root shell saklanamaz.

### D — Sertleştirme ve işletim

| # | iş | "bitti" kanıtı |
|---|---|---|
| D1 ✅ | qgroup komut katmanı + sandbox'a bağlandı (`quota.py`, 7 test); root yetkisi olmayan yerde `quota_note` ile dürüst uyarı | imajda 256 MB kotada 512 MB yazma → `ENOSPC` |
| D2 ✅ | `anchor.py`: imzalı `anchors.jsonl`, `audit anchor` / `audit anchor-verify` (8 test) | yerel log silinse/ kurcalansa bile tespit |
| D3 ✅ | `.github/workflows/ci.yml` (Arch container: guard, test, proof, smoke, bare-except taraması) | kırmızı merge edilemiyor |
| D4 | Yedekleme/restore tatbikatı: snapshot + imaj geri yükleme | tatbikat raporu |
| D5 ✅ | `netproxy.py`: sandbox netns'siz kalır, izin verilen host:port'a yalnız Unix-socket proxy ile çıkılır; grant TTL + audit (10 test) | izinsiz hedef → soket kapanır; izinli hedef → veri akışı; doğrudan `connect` hâlâ `ENETUNREACH` |

### E — Sonra

| # | iş | not |
|---|---|---|
| E1 | microVM profili (Firecracker/KVM) | `profile:"microvm"` alanı hazır |
| E2 | Çok düğüm: `node_id`, `v1.node.peers/dispatch` rezerve | swarm kodu yok |
| E3 | 80B model | **ayrı ürün, bu roadmap dışı** |

### F — OS beyni: 10 daimi uzman (~100M) + deneyim deposu

| # | iş | sahip | "bitti" kanıtı |
|---|---|---|---|
| F0 | **Deneyim deposu şeması** (ORTAK karar, bu hafta): olay = `{ts, node_id, niyet, adımlar, araç çağrıları, sonuç, hata, geri bildirim, kaynak}`; JSONL + indeks; kişisel veri alanları işaretli | ikimiz | şema dosyası + 10 örnek kayıt doğrulayıcıdan geçiyor |
| F1 | Runtime (OS tarafı): 10 × llama.cpp instance, her biri ayrı sandbox + cgroup limiti; router (niyet → uzman); toplam RAM tavanı; `ai` uid'i altında | ben | `systemctl status parametral-mind@1..10`; cgroup tavanı aşılamıyor; router 10 niyet sınıfını doğru yönlendiriyor |
| F2 | Eğitim (senin tarafın, sonra): uzman başına veri F0'dan, LoRA/DPO; GC Shield aynı hatta | sen | eğitim raporu + regresyon seti |

Not: 10 × 100M, 80B'nin yerini tutmaz; amaç yerel, denetlenebilir, düşük gecikmeli uzmanlar.
Kapasite yetmezse A5 profili uzman sayısını düşürür (kısmi kurulum).

## Kararlar (kapandı)

| # | karar | sonuç |
|---|---|---|
| 1 | Paket modeli | **Flakes**; manifest `flake_ref` + `flake.lock` pin; güncelleme döngüsü update-manager'da |
| 2 | Süreç ayrımı | **`ai` ayrı uid + `approver` ayrı uid**; anahtarlar root sahipli |
| 3 | Audit anchor | Günlük imzalı `head_hash` off-host; TPM sonra |
| 4 | Arayüz | Prototipte **KDE**, üründe özel shell |
| 5 | Disk şifreleme | **LUKS varsayılan evet**; Secure Boot sonra |
| 6 | Marka | **Parametral OS**; teknik adlar kod adı |

## Riskler

| risk | azaltma |
|---|---|
| Nix store'a yazma yanlış tasarımı | yazma yalnız `nix-daemon`'da; sandbox'ta ro store + daemon soketi (B1) |
| Cache dışı paket sessizce derlenir | `builders ''` + `require-sigs`; derleme gerekiyorsa sandbox içi, loglu |
| Root helper'ın genişlemesi | preset listesi + **approver imzalı** iş dosyası + reddi test eden vaka |
| Anahtar karışması (harddeny ≈ approver) | üç ayrı keypair, yanlış anahtar testi (C1) |
| 10 uzmanın RAM'i yemesi | F1 cgroup tavanı + A5 kapasite profili |
| Kernel paylaşımı | microVM faz 5; şimdilik seccomp + cap-drop + userns |

## Bu hafta

- Sen: A1 + A2 (+ `linux-lts`, LUKS). Takılırsan subvolume/unit dosyalarını ben veriyorum.
- Arkadaş: AI1 (API client akışı) + **F0 şemasında ortak karar**.
- Ben: B1 (nix-daemon soketli sandbox) + C1 imzalı iş protokolü; ikisi de testli.
