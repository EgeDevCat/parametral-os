# Parametral OS — Arch kurulumu (snapshot + kullanıcı ayrımı + yedek çekirdek)

Bu bir *kurulum kiti*: Arch ISO'da çalışır, hedef diski siler. Geliştirme makinesinde
çalıştırılmaz (kit bunu kontrol eder: UEFI + root + `--yes` + boş `/mnt` şartı).

Hedef disk örneği: `/dev/nvme0n1`. Sıra: `10 → 20 → 30 → 40 → 50 → 60 → 70`.

## 1. ISO'da hazırlık (fish)

```fish
loadkeys trq                     # gerekirse
ping -c1 archlinux.org           # ağ var mı
bash install/10-preflight.sh /dev/nvme0n1
bash install/10-preflight.sh /dev/nvme0n1 --yes
```

`10-preflight.sh` şunları doğrular: UEFI modu, root, blok cihazın gerçekten disk olması,
`/mnt` boş, gerekli araçlar (sgdisk, mkfs.fat, mkfs.btrfs, pacstrap, cryptsetup, bootctl),
ve onay (`--yes`).

## 2. Disk + LUKS + btrfs

```fish
bash install/20-disk.sh /dev/nvme0n1 --yes          # LUKS2 varsayılan
# geliştirme için şifresiz:  bash install/20-disk.sh /dev/sda --yes --no-luks
```

Ne yapar: 1 GiB ESP (fat32) + kalan alan LUKS2 → btrfs; subvolume'ler `@`, `@home`, `@var`,
`@snapshots`; mount seçenekleri `compress=zstd:3,noatime,ssd,discard=async`; `fstab` ve
`/etc/parametral/snapshot.env` (root UUID + LUKS UUID) yazılır.

`/var` ayrı subvolume: log/cache gürültüsü snapshot'lara girmez.

## 3. Taban sistem + iki çekirdek

```fish
bash install/30-bootstrap.sh
```

`base base-devel linux linux-lts linux-firmware btrfs-progs cryptsetup sudo networkmanager
nix …` + `genfstab` + `locale` + `mkinitcpio -P` (iki çekirdek için de initramfs) + `nix.conf`
(`sandbox = true`, `require-sigs = true`, `trusted-users = root parametral`) + `nix-daemon` açık.
LUKS varsa HOOKS'a `encrypt`, `/etc/crypttab` yazılır.

## 4. Kullanıcılar (ayrım)

```fish
bash install/40-users.sh
```

| kullanıcı | ne yapar | yetki |
|---|---|---|
| `operator` | sen | wheel + sudo |
| `parametral` | gateway + oracle servisleri | kabuk yok (`nologin`), sudo yok |
| `approver` | onay UI, onay anahtarı | sudo yok, anahtar `0700` |
| `ai` | AI süreci | hiçbir grup yok, sudo yok, ev `0700`, `/etc/parametral/keys` okuyamaz |

`sudoers.d/10-parametral`: `ai`, `parametral`, `approver` için açıkça `!ALL` (sudo denemesi
kayda geçer). Polkit kuralı `ai` için her ayrıcalıklı eylemi reddeder.

## 5. Snapshot sistemi

```fish
bash install/50-snapshots.sh
```

- `/usr/local/bin/parametral-snapshot` kurulur (create / list / boot-entry / promote / prune / delete).
- pacman kancaları: **PreTransaction** → `create pacman`, **PostTransaction** → `prune --keep 10`.
  Yani her `pacman -S/-Syu/-R` öncesi otomatik snapshot; kanca `AbortOnFail` çalışır, snapshot
  alınamazsa paket işlemi de başlamaz.
- `install-baseline` snapshot'ı alınır.

### Geri dönme (tek tuş)

1. `parametral-snapshot list` → id seç.
2. `parametral-snapshot boot-entry <id>` → systemd-boot menüsüne "ParametralOS (snapshot …)" girer.
3. Yeniden başlat, o girdiyi seç: sistem snapshot'ın kopyasından **rw** açılır; bozulan bir şey
   yoksa hiçbir şey değişmez.
4. Sağlam olduğuna karar verirsen `parametral-snapshot promote <id>`: mevcut `@` →
   `@.old-<zaman>` olarak park edilir, snapshot `@` yapılır. Beğenmezsen eskiyi geri alırsın.

Sistem hiç açılmıyorsa: Arch ISO → `mount -o subvol=@snapshots …` → aynı komutlar.

## 6. Önyükleyici (main + yedek çekirdek)

```fish
bash install/60-boot.sh
```

`systemd-boot` kurulur, `loader.conf` (timeout 4, `editor no`), üç girdi:
`parametral.conf` (linux), `parametral-lts.conf` (**linux-lts**), `parametral-fallback.conf`
(fallback initramfs). LUKS varsa `cryptdevice=UUID=…` kernel satırına eklenir.

## 7. Doğrulama (kanıt)

```fish
bash install/70-verify.sh
```

Şunları tek tek PASS/FAIL eder: btrfs subvolume'ler, snapshot aracı + kanca + boot-entry
üretimi, `ai`'nin sudo/grup/anahtar erişimi, polkit, `linux-lts` + initramfs + 3 boot girdisi,
nix ayarları. Hepsi PASS değilse çıkış kodu 1.

## 8. İlk açılış

```fish
# root ile
pacman -S plasma-meta sddm     # prototip arayüzü (KDE)
systemctl enable sddm
systemctl enable --now systemd-timesyncd
# parametral katmanı (repo'dan)
install -Dm0755 bin/parametrald /usr/local/bin/parametrald
install -Dm0755 bin/parametral-harddeny /usr/local/bin/parametral-harddeny
```

Servis dosyaları `install/systemd/` altında: `parametrald.service`, `parametral-harddeny.service`
(`User=parametral`, `ProtectSystem=strict`, `NoNewPrivileges=yes`, `ReadOnlyPaths=/etc/parametral`).

## Bilinen sınırlar

- LUKS açılışta şifre ister; TPM ile otomatik açma sonraki adım (Secure Boot ile birlikte).
- `snapshot promote` çalışırken sistemin o subvolume'dan açık olmaması gerekir (canlı ISO veya
  snapshot oturumu). Araç bunu `refusing` kontrolüyle engeller.
- Snapshot'lar `/` üzerinde; ayrı disk/yedek değil. Diskte yer biterse snapshot da alamazsın —
  `prune` bu yüzden 10 taneyle sınırlı.
- Bu kit `nix` kurar ama AI'ın uygulama kurma hattı `app.install` üzerinden yürür; ayrıntı
  `docs/API-v1.md` §5.9.
