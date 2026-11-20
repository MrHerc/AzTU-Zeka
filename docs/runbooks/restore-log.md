# Bərpa və geri qayıtma jurnalı

Hər sınaq bərpası və geri qayıtma ixracı bura yazılır: tarix, yer, dəst, müddət, sətir sayı, nəticə
(`docs/runbooks/backup.md`, `docs/runbooks/cutover.md`).

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
