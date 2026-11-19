# Anahtar töreni (key ceremony) — Parametral OS

Dört anahtar var, dördü de **asimetrik** (Ed25519). Kural tek cümle: *doğrulayan taraf imza
atamaz.* Gateway, oracle ve sysapply yalnız public key taşır; private key'ler root'a (veya
çevrimdışı bir makineye) aittir.

| anahtar | kim üretir | nerede durur | neyi imzalar | kim doğrular |
|---|---|---|---|---|
| **harddeny** | OS sahibi, çevrimdışı | `/etc/parametral/keys/hard_deny.ed25519.sk` (root 0600) | `policy/hard_deny.v1.json` | `parametral-harddeny` (public key) |
| **approver** | onay servisi (approver uid) | `/var/lib/parametral/keys/approver.ed25519.sk` (0600) | onay kararları **ve** tier-1 iş dosyaları | `parametrald` + `parametral-sysapply` (public key) |
| **anchor** | operatör | `/var/lib/parametral/keys/anchor.ed25519.sk` (0600) | günlük audit head | `audit anchor-verify` (public key) |
| **token** (simetrik değil, HMAC) | daemon, ilk açılışta | `/var/lib/parametral/token.key` (0600) | capability token'ları | aynı daemon |

Token anahtarı bilinçli olarak simetrik: token'ı üreten ve doğrulayan aynı süreç. Kural
dosyalarını imzalayan anahtarlar ise asla daemon'da değil.

## 1. İlk kurulum (kurulum kiti bunu yapar)

```fish
# imajda, root olarak, tek sefer
mkdir -p /etc/parametral/keys && chmod 700 /etc/parametral/keys

# harddeny anahtarı: tercihen çevrimdışı bir makinede üret, sadece public key'i imaja koy
parametral harddeny keygen --key /root/offline/hard_deny.ed25519.sk \
                          --pub /etc/parametral/keys/hard_deny.v1.pub
parametral harddeny sign --rules /etc/parametral/policy/hard_deny.v1.json \
                         --key /root/offline/hard_deny.ed25519.sk
parametral harddeny verify --rules /etc/parametral/policy/hard_deny.v1.json \
                           --pub /etc/parametral/keys/hard_deny.v1.pub

# approver anahtarı: approver uid'inin evinde, 0600
install -d -o approver -g approver -m 700 /var/lib/parametral/keys
runuser -u approver -- parametral approvals keygen --key /var/lib/parametral/keys/approver.ed25519.sk --pub /var/lib/parametral/keys/approver.pub
runuser -u approver -- python3 -c "from parametral import ed25519; ed25519.keygen('/var/lib/parametral/keys/approver.ed25519.sk','/var/lib/parametral/keys/approver.pub')"
```

Sonra `parametrald` ve `parametral-harddeny` servislerini başlat: ikisi de yalnız `*.pub`
okur, eksikse **fail-closed** davranır (oracle açılmaz, gateway her durum değiştiren işlemi
reddeder).

## 2. Günlük akışlar

- **Kural değişikliği**: root, `hard_deny.v1.json`'ı düzenler → `harddeny sign` (offline key) →
  `systemctl restart parametral-harddeny`. Dosya çalışırken değişirse oracle kendini kapatır;
  imza yoksa açılmaz.
- **Tier-1 değişiklik**: AI `host.apply` → iş kuyruğa düşer → **approver** `parametral host sign
  <job_id>` ile o tam argv'yi imzalar → `parametral-sysapply` doğrular ve çalıştırır. Approver
  işi okumadan imzalamamalı; imza, okuduğu yükün hash'ini de taşır.
- **Günlük anchor**: systemd timer → `parametral audit anchor --out /var/backups/parametral-anchors`
  (veya doğrudan off-host hedefe) → haftada bir `audit anchor-verify`.

## 3. Kayıp / ele geçirme

| durum | sonuç | yapılacak |
|---|---|---|
| harddeny **public** key kayıp | oracle açılmaz, her şey fail-closed | imajdaki yedek public key'i geri koy |
| harddeny **private** key kayıp | kural güncellenemez (mevcut imza hâlâ geçerli) | çevrimdışı yedekten al; yoksa yeni keypair + yeni imza + tüm düğümlere dağıtım |
| approver private ele geçti | saldırgan tier-1 iş imzalayabilir | anahtarı iptal et (yeni keypair, public key'i dağıt), audit'te `approved_by` alanından hangi işlerin imzalandığını incele |
| anchor private ele geçti | sahte anchor üretilebilir | anchor'ları yeni anahtarla imzala, eski anchor dosyasını arşivde tut |
| gateway uid ele geçti | hiçbiri: imza üretemez, kural yazamaz | yine de servis kullanıcısının dosyalarını ve audit zincirini incele |

## 4. Rotasyon

1. Yeni keypair üret (aynı prosedür).
2. Yeni public key'i **önce** dağıt (dosya adı `*.v2.pub`), imzayı yeni anahtarla at; eski
   imza dosyasını `*.sig.v1` olarak sakla.
3. Doğrulamanın yeni anahtarla geçtiğini gör (`harddeny verify`, `audit anchor-verify`).
4. Eski private key'i güvenli şekilde imha et; audit'e rotasyon kaydı düş.

## 5. Bilinen sınırlar

- Bu prosedür root erişimi varsayar; root'un ele geçirilmesi her şeyi ele geçirir (audit anchor
  bunu *tespit edilebilir* yapar, engellenemez).
- `harddeny` anahtarını çevrimdışı tutmak manuel bir disiplindir; imaj onu zorlayamaz.
- TPM tabanlı mühürleme (anahtar diskte durmaz) henüz yok — faz 5.
