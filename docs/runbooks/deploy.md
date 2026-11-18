# Runbook: yerləşdirmə (Docker, Caddy)

Fayllar: `infra/Dockerfile`, `infra/compose.yml`, `infra/Caddyfile`, `infra/.env.example`. Demo üçün ayrıca
`infra/compose.demo.yml` var: o, parolsuz demo girişi ilə yalnız bu kompüterdə açılır.

## Quruluş

```
internet ──443/80──▶ caddy (TLS, HSTS tətbiqdən, sorğu ≤ 16 MB) ──daxili şəbəkə──▶ app:5070 (ZEKA_MODE=prod)
                                                                              │
                         həcmlər: zeka-data (baza, yükləmələr), zeka-backups, zeka-logs, caddy-data (sertifikatlar), caddy-config
```

- `app` servisinin `ports:` bəndi yoxdur. Onu yalnız Caddy görür.
- `app` konteyneri `zeka` istifadəçisi (uid 10001) ilə işləyir. Kök fayl sistemi yalnız oxunandır (`read_only`), bütün
  Linux imkanları götürülüb (`cap_drop: ALL`), `no-new-privileges` aktivdir. Kod root-a məxsusdur və tətbiq onu dəyişə bilmir.
- Hər servisin Docker jurnalı 50 MB × 5 faylla məhdudlaşır.
- Saat qurşağı: `TZ=Asia/Baku` (Dockerfile) və `ZEKA_TZ` (tətbiq).

## İlk quraşdırma

```bash
git clone <repo> /opt/zeka && cd /opt/zeka
cp infra/.env.example infra/.env && chmod 600 infra/.env        # dəyərləri doldurun (aşağıdakı cədvəl)
mkdir -p infra/secrets/ssh
(umask 077; openssl rand -base64 48 > infra/secrets/backup.key)   # açarın kağız nüsxəsi seyfə: docs/runbooks/backup.md
chown -R 10001:10001 infra/secrets && chmod 700 infra/secrets/ssh
docker compose -f infra/compose.yml up -d --build
docker compose -f infra/compose.yml exec app python backend/manage.py create-admin --username <ad> --name "<Ad Soyad>"
```

Ssh ilə backup üçün `infra/secrets/ssh/`-ə `id_ed25519` (600) və `known_hosts` qoyulur (sahibi 10001). Bu açarlar və backup açarı yalnız `backup` servisinə qoşulur (`docker compose run --rm backup`), veb konteyneri onları görmür.

## `.env` dəyişənləri

| Dəyişən | Nümunə | Mənası |
|---|---|---|
| `SITE_ADDRESS` | `zeka.aztu.edu.az` | Caddy-nin xidmət etdiyi host adı. DNS bu serverə yönəlməlidir, 80 və 443 portları açıq olmalıdır. Caddy sertifikatı özü alır və yeniləyir. Boş olarsa `compose` başlamır |
| `PUBLIC_URL` | `https://zeka.aztu.edu.az` | Portalın ictimai ünvanı: sənədlərin QR kodları bura yönəlir, cookie-lər `Secure` olur, tətbiq HSTS göndərir. `SITE_ADDRESS` ilə eyni host olmalıdır |
| `ZEKA_MODE` | `prod` | Prod rejimi: demo girişi və demo marşrutları yoxdur, insanlar toxum kimi yaradılmır, baza heç vaxt silinmir, `--reset` qadağandır |
| `ZEKA_PROXY_HOPS` | `1` | Tətbiqin qabağındakı etibarlı proksilərin sayı. Caddy birdir. Müştəri ünvanı `X-Forwarded-For`-un sağdan 1-ci elementindən götürülür |
| `ZEKA_TZ` | `Asia/Baku` | Universitetin saat qurşağı: dərs cədvəli, son tarixlər və jurnal vaxtları. Tanınmayan qurşaqla prod başlamır |
| `ZEKA_WORKERS` | `2` | Eyni portu paylaşan proseslər. Nüvə sayından çox olmasın. İndeks bir dəfə qurulur və proseslər onu paylaşır (`docs/perf/baseline.md`) |
| `BACKUP_REMOTE` | `zeka-backup@backup.aztu.edu.az:/srv/zeka-backups` | Ölkə daxilində ikinci host (ssh) və ya qoşulmuş qovluq. Prod-da boş olarsa `infra/backup.sh` 4 kodu ilə bitir |
| `BACKUP_KEY_FILE` | `/run/secrets/backup_key` | Backup açarı. `compose` onu `infra/secrets/backup.key`-dən sirr kimi qoşur. Dəyəri dəyişməyin |
| `AZTU_LLM_PROVIDER` | boş | İstəyə görə xarici LLM: `openai`, `azure` və ya `anthropic`. Boş olarsa oflayn mühərrik cavab verir |
| `AZTU_LLM_BASE_URL` | boş | OpenAI-uyğun və ya Azure son nöqtəsi |
| `AZTU_LLM_API_KEY` | boş | LLM açarı. Yalnız `infra/.env`-də saxlanır, o da git-ə düşmür |
| `AZTU_LLM_MODEL` | boş | Modelin adı |

`ZEKA_ACCESS_CODE` və `ZEKA_ALLOW_OPEN_DEMO` yalnız demo üçündür: prod-da istifadə olunmur.

## TLS

- Susmaya görə Caddy sertifikatı ACME (Let's Encrypt) ilə alır. Bunun üçün 80 və 443 portları internetdən açıq olmalıdır.
- Universitetin öz sertifikatı ilə: `infra/Caddyfile`-da `reverse_proxy` sətrindən əvvəl
  `tls /etc/caddy/certs/fullchain.pem /etc/caddy/certs/privkey.pem` əlavə edin. Fayllar `caddy` servisinə yalnız
  oxunan həcm kimi qoşulur (`./secrets/certs:/etc/caddy/certs:ro`).
- HSTS-i tətbiq göndərir (`PUBLIC_URL` `https://` ilə başlayanda). CSP və `nosniff` də tətbiqdən gəlir.

## Proksi zənciri

Caddy-də `trusted_proxies` təyin olunmayıb. Buna görə müştərinin göndərdiyi `X-Forwarded-For` atılır və yerinə müştərinin
real ünvanı yazılır. Tətbiq `ZEKA_PROXY_HOPS=1` ilə bu ünvanı götürür.

Caddy-nin qabağına ikinci proksi (yük balanslaşdırıcı, WAF) qoyulsa, iki şey **birlikdə** dəyişir:
1. `infra/Caddyfile`-da qlobal blok: `servers { trusted_proxies static <proksinin ünvanı> }`;
2. `infra/.env`-də `ZEKA_PROXY_HOPS=2`.

Yalnız birini dəyişmək ya müştəri ünvanını proksinin ünvanı edir (limitlər hamını birlikdə sayır), ya da saxta
`X-Forwarded-For`-a yol açır.

## Yeniləmə

```bash
cd /opt/zeka && docker compose -f infra/compose.yml run --rm -T backup
git pull && docker compose -f infra/compose.yml up -d --build
```

Yeni miqrasiyalar başlanğıcda tətbiq olunur. Bundan əvvəl bazanın nüsxəsi `zeka-data` həcmindəki `backups/`-a yazılır.
Baza koddan yenidirsə, tətbiq başlamır. Bu halda əvvəlki versiyaya qayıdın (`git checkout <tag>`).

## Yoxlama

```bash
C="docker compose -f infra/compose.yml"
curl -sk -D- https://localhost/healthz                         # 200, strict-transport-security, content-security-policy, nosniff
$C exec app id -u                                              # 10001
docker inspect -f '{{.Name}} {{.HostConfig.LogConfig.Config}}' $($C ps -q)   # max-file:5 max-size:50m
$C exec app python -c "import time; print(time.strftime('%z'))"   # +0400
curl -sk -H 'X-Forwarded-For: 1.2.3.4' https://localhost/healthz; $C logs app | grep -c '1.2.3.4'   # 0
$C exec caddy hostname -i                                      # jurnaldakı "ip" bu ünvan deyil
curl -s -m 3 http://localhost:5070/healthz                     # qoşulmur: tətbiqin portu hostda açıq deyil
$C restart && $C exec app python backend/manage.py status      # məlumat yerindədir
```

Bu yoxlamalar 2026-11-18-də `SITE_ADDRESS=localhost` ilə aparılıb və hamısı keçib. İstisna: sınaq mühitinin şəbəkəsi
Debian paket serverini bağladığı üçün `openssh-client` paketi qurulmayan image ilə işlənib. `tzdata` və `openssl` baza
image-də artıq var. Ssh ilə göndərmə `tests/migration/test_backup_restore.py`-də saxta ssh ilə yoxlanır.
