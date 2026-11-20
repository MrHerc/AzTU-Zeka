# Runbook: backup və bərpa

Əmrlər: `infra/backup.sh` (`backend/manage.py backup`) və `infra/restore.sh` (`backend/manage.py restore`).
Kod: `backend/zeka/core/backup.py`. Testlər: `tests/migration/test_backup_restore.py` (CI-da hər push-da işləyir).

## Bir dəstdə nə var

| Fayl | Məzmun |
|---|---|
| `zeka-YYYYMMDD-HHMMSS.enc` | Baza: bir addımda ardıcıl nüsxə (`Connection.backup`), gzip, AES-256-CBC (`openssl enc -pbkdf2 -iter 10000 -md sha256`) |
| `zeka-YYYYMMDD-HHMMSS.json` | Manifest: `.enc`-in SHA-256-sı, hər cədvəlin sətir sayı, dəstin ehtiyac duyduğu yükləmələr, açarla HMAC |
| `uploads/<sha256>.enc` | Hər yükləmə bir dəfə (məzmun ünvanlıdır, dəyişmir); növbəti dəstlər yalnız yeniləri əlavə edir |
| `uploads/index.tsv` | Yükləmənin və şifrəli faylın SHA-256-sı: ikinci hostda yoxlama üçün |
| `latest.enc` | Ən yeni dəstə keçid |

Saxlama müddəti: son 7 günün hər birinin ən yeni dəsti və son 4 ISO həftənin hər birinin ən yeni dəsti. Heç bir saxlanan
dəstin ehtiyac duymadığı yükləmə silinir. İkinci host qovluğun güzgüsüdür: orada da eyni dəstlər qalır.

## Açar

```bash
umask 077 && openssl rand -base64 48 > /etc/zeka/backup.key      # bir sətir, ≥ 32 simvol
```

- Fayl yalnız sahibi tərəfindən oxunmalıdır (`chmod 600`). Başqalarının oxuya bildiyi və ya qısa açar rədd olunur. Açar
  olmadan backup xəta ilə (kod 2) bitir və heç bir fayl yazmır.
- Açarın iki nüsxəsi serverdən və backup-lardan kənarda saxlanır: biri məhsulun sahibində, biri AzTU İT-də (seyfdə kağız
  nüsxə və ya parol meneceri). Açarı itirmək bütün backup-ları itirmək deməkdir.
- Bərpanı açarın kənar nüsxəsi ilə başqa adam da apara bilməlidir: ildə bir dəfə bu yoxlanır və `restore-log.md`-yə yazılır.
- Açar dəyişəndə köhnə dəstlər köhnə açarla açılır. Köhnə açarı 4 həftə saxlayın.

## Mühit dəyişənləri

| Dəyişən | Mənası |
|---|---|
| `BACKUP_KEY_FILE` | Açar faylının yolu (məcburi) |
| `BACKUP_REMOTE` | İkinci host, ölkə daxilində: `user@host:/yol` (ssh) və ya qoşulmuş qovluq (`/mnt/backup`). Prod-da məcburidir |
| `BACKUP_DIR` | Lokal qovluq, susmaya görə repozitoriyadakı `backups/` (Docker-də ayrıca həcm) |
| `ZEKA_DATA` | Bazanın və yükləmələrin qovluğu, tətbiqlə eyni |

## İkinci host (ssh)

Ayrıca istifadəçi (`zeka-backup`), yalnız açar ilə giriş, qovluq yalnız ona aiddir. Fayl son adını yalnız ikinci hostda
SHA-256-sı uyğun gələndən sonra alır (`.incoming` qovluğunda yoxlanır və yerinə köçürülür). Kəsilən və ya xarab göndəriş
növbəti gecə yenidən göndərilir. Saxlama müddəti hər iki tərəfin dəstləri üzrə hesablanır: lokal qovluq itsə də, ikinci
hostdakı tarixçə silinmir. Qoşulmuş qovluq (`BACKUP_REMOTE=/mnt/...`) üçün `uploads` alt qovluğu o diskdə bir dəfə əl ilə
yaradılır. Disk qoşulmayıbsa backup 3 kodu ilə bitir, eyni diskə sakitcə yazmır. Hostda `tar` və `sha256sum` olmalıdır
(hər Linux-da var). Tətbiq hostunda `ssh` müştərisi və `known_hosts`-da ikinci hostun açarı (`BatchMode=yes`: sual
verilmir, tanınmayan host rədd olunur). Göndərmədən sonra bu dəfə göndərilən hər faylın SHA-256-sı ikinci hostda
`sha256sum -c` ilə yoxlanır. Uyğunsuzluq və ya ssh xətası olarsa çıxış kodu 3 olur.

## Gündəlik iş

Backup ayrıca, qısa ömürlü `backup` konteynerində işləyir (`infra/compose.yml`, `profiles: [backup]`). Backup açarı və ssh açarı yalnız ona qoşulur. Veb prosesi onları görmür.

```cron
17 3 * * *  cd /opt/zeka && docker compose -f infra/compose.yml run --rm -T backup >> /var/log/zeka-backup.log 2>&1 || echo "zeka backup failed: $?" | mail -s "Zəka backup" ops@aztu.edu.az
```

Çıxış kodları:

| Kod | Mənası |
|---|---|
| 0 | Hazırdır |
| 2 | Backup alınmadı (açar, disk, baza); şifrəsiz fayl qalmır |
| 3 | Lokal dəst hazırdır, ikinci host alınmadı |
| 4 | Prod-da `BACKUP_REMOTE` boşdur; lokal dəst hazırdır |
| 5 | Dəst hazırdır, amma məlumat qovluğunda SHA-256-sı uyğun gəlməyən yükləmə var (stderr-də adları); onlar dəstə düşməyib |

## Bərpa

1. Dəsti yoxla və yeni qovluğa bərpa et. İşləyən məlumata toxunulmur:
   ```bash
   infra/restore.sh backups/latest.enc /srv/zeka/restore-$(date +%F)          # konteynersiz quraşdırma
   docker compose -f infra/compose.yml run --rm backup infra/restore.sh \
     /var/lib/zeka/backups/latest.enc /var/lib/zeka/backups/restore-$(date +%F)  # Docker: zeka-backups həcmində
   ```
   Yoxlanır: manifestin HMAC-ı, `.enc`-in SHA-256-sı, `PRAGMA integrity_check`, hər cədvəlin sətir sayı, hər yükləmənin
   SHA-256-sı. Biri uyğun gəlmirsə, kod 2 qaytarılır və qovluqda baza qalmır.
2. Tətbiqi dayandır: `docker compose -f infra/compose.yml stop app`.
3. Köhnə məlumatı kənara qoy, bərpa olunanı yerinə köçür:
   ```bash
   mv /srv/zeka/data /srv/zeka/data.before-restore
   mv /srv/zeka/restore-YYYY-MM-DD /srv/zeka/data
   chown -R 10001:10001 /srv/zeka/data
   ```
4. Tətbiqi başlat. Bərpa olunan baza koddan köhnədirsə, miqrasiyalar başlanğıcda tətbiq olunur. Baza koddan yenidirsə,
   server başlamır: həmin versiyanın kodunu yerləşdirin.
5. `/healthz` və bir neçə əsas səhifəni yoxla, sonra `data.before-restore`-u sil.

Ayda bir dəfə sınaq bərpası ikinci hostdakı nüsxədən aparılır (1-ci addım). Nəticə `docs/runbooks/restore-log.md`-yə
yazılır: tarix, dəst, müddət, sətir sayı.
