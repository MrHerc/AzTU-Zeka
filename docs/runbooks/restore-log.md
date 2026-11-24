# Bərpa və geri qayıtma jurnalı

Hər sınaq bərpası və geri qayıtma ixracı bura yazılır: tarix, yer, dəst, müddət, sətir sayı, nəticə
(`docs/runbooks/backup.md`, `docs/runbooks/cutover.md`).

## 2026-11-24: canlı yük altında backup, bərpa və bərpa olunan serverin başlanması

Yer: inkişaf konteyneri (4 nüvə, 15,7 GB, Python 3.13.18), Docker-siz. Dəst `university` (10 149 istifadəçi, 60 720
qeydiyyat, 100 094 material parçası, 100 765 test cəhdi); baza ~120 MB, WAL rejimi. Yük `tools/loadtest.py --scenario
mixed --users 300 --seconds 90 --dataset university --workers 2` (80% oxu, 20% yazı, gözləmə vaxtı yoxdur). Yük işləyən
vaxt həmin `ZEKA_DATA`-dan 12 saniyə fasilə ilə 3 backup alınıb. Backup SQLite-ın onlayn backup API-si ilə alınır
(`Connection.backup`, bir addımda): canlı bazanın faylı kopyalanmır. Hər şey müvəqqəti qovluqlarda aparılıb, `data/`-ya toxunulmayıb.

| Addım | Əmr | Müddət | Nəticə |
|---|---|---|---|
| Yük, backup-sız (müqayisə üçün) | `loadtest.py` yuxarıdakı kimi | 90 s | 366 sorğu/s, p50 803 ms, p95 1 731 ms, p99 2 373 ms; 1 dəfə 5xx (`POST /api/news/{news}/save`), 0 bağlantı xətası |
| Yük, 3 backup ilə | eyni, paralel `manage.py backup --dest … --key-file …` | 90 s | 399 sorğu/s, p50 733 ms, p95 1 547 ms, p99 2 132 ms; 0 dəfə 5xx, 0 bağlantı xətası |
| Backup 1–3 | `manage.py backup` | 10,1 s · 9,2 s · 10,3 s | Kod 0. 122 cədvəl; sətirlər 308 062 → 312 602 (backup-lar arasında yazılar davam edib); dəst 37,5 MB (`.enc`), 19 yükləmə |
| Bərpa | `manage.py restore latest.enc --to <yeni qovluq>` | 1,2 s | Kod 0. HMAC, SHA-256, `integrity_check ok`, 122 cədvəlin sətir sayı manifestə uyğundur; qovluq 120 MB |
| Əl ilə yoxlama | `PRAGMA integrity_check`, hər cədvəlin `COUNT(*)` | — | `ok`; manifestdən fərqlənən cədvəl yoxdur (312 602 sətir) |
| Bərpa olunan server | `ZEKA_DATA=<bərpa qovluğu> backend/run.py`, `GET /healthz` | 20,5 s | HTTP 200, `ok: true` (başlanğıcın çoxu 100 000 parçanın axtarış indeksidir) |

Nəticə: canlı yazı yükü altında backup ardıcıl və tamdır, yükə təsiri ölçmə xətası daxilindədir (iki qaçış arasındakı
fərq səs-küydür: 300 müştəri serveri tam doldurur). Saatlıq backup-ın qiyməti: saatda ~10 s bir nüvə, 37,5 MB disk və
ikinci hosta 37,5 MB; 24 saatlıq dəst ~0,9 GB (`backup.md`, «RPO»). Backup-sız qaçışdakı bir 500 xətası
(`news/save`) backup-la bağlı deyil; səbəbi bu sınaqda araşdırılmayıb.

Açıq qalanlar: Docker ilə və hədəf serverdə eyni sınaq (Task 44); bir neçə GB-lıq bazada müddət.

## 2026-11-20: sınaq konteyneri, `university` dəsti (Task 43)

Yer: inkişaf konteyneri (4 nüvə, 15 GB, Python 3.13), Docker-siz, `manage.py` ilə. Dəst `tools/loadtest.py`-nin
`university` dəstidir: 10 147 istifadəçi, 60 720 qeydiyyat, 100 000 material parçası; baza 116 MB. Skript
müvəqqəti qovluqda işləyib və sonda onu silib; `data/`-ya toxunulmayıb.

| Addım | Əmr | Müddət | Nəticə |
|---|---|---|---|
| Host saatı | `timedatectl show -p NTPSynchronized --value` | — | Konteynerdə systemd yoxdur: "System has not been booted with systemd". Hədəf serverdə yoxlanılacaq (Task 44) |
| Backup | `manage.py backup --dest … --key-file …` | 9,0 s | Kod 0. 103 cədvəl, 305 906 sətir, 18 yükləmə; dəst 36 MB. `BACKUP_REMOTE` boşdur (demo rejimi: xəbərdarlıq, prod-da kod 4) |
| Bərpa | `manage.py restore latest.enc --to …` | 1,1 s | Kod 0. HMAC, SHA-256, `integrity_check ok`, sətir sayları manifestə uyğundur |
| Müqayisə | mənbə ilə bərpa olunan baza | — | `users` 10 147 = 10 147, `attendance` 17 280 = 17 280, `grades` 1 440 = 1 440, `lessons` 225 = 225, `enrollments` 60 720 = 60 720 |
| Geri qayıtma: ballar | `manage.py export --kind grades --since 2026-11-01T00:00:00` | 0,2 s | 1 440 sətir |
| Geri qayıtma: davamiyyət | `… --kind attendance --since 2026-11-01T00:00:00` | 0,2 s | 0 sətir: dəstin davamiyyəti bu tarixdən əvvəl yazılıb |
| Geri qayıtma: status | `… --kind status-changes --since 2026-11-01T00:00:00` | 0,2 s | 0 sətir: dəstdə status əmri yoxdur |
| Tam vəziyyət | `… --kind oneroster` | 1,4 s | 2,8 MB zip |

Bərpanın tam müddəti (yoxlama daxil): təxminən 1 saniyə. Bunun üzərinə tətbiqi dayandırmaq, qovluğu dəyişmək və
başlatmaq gəlir (`backup.md`, addım 2–4); Docker ilə bu, sınaqda ölçülməyib.

Açıq qalanlar (Task 44):
- Hədəf serverdə Docker ilə bərpa və `timedatectl`.
- İkinci maşında, açarın kənar nüsxəsi ilə, başqa adamın apardığı bərpa.
- Real ölçülü bazada ölçmə: yükləmələr çox olanda müddət artır.
