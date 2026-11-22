# Runbook: V1 buraxılışı (Task 44)

Kim üçün: məhsulun sahibi, növbətçi admin və AzTU İT. Addımlar `tasks/todo.md`-dəki Task 44 və Checkpoint F
meyarlarına uyğundur. `C` aşağıda `docker compose -f infra/compose.yml`, `M` isə
`C exec app python backend/manage.py` deməkdir.

## Sahibin verəcəkləri (boş yerlər)

> **Hələ boşdur.** Sahib 2026-11-21-də qərar verdi: bu dəyərləri sonra verəcək, yerləri saxlanılsın. Hər sətirdə dəyərin
> hara yazılacağı və gələnə qədər nəyin bloklandığı göstərilib. Dəyər gələndə "Dəyər" sütunu doldurulur və eyni sətir
> `tasks/todo.md`-də (Task 44, "Sahibin verəcəkləri") işarələnir. Telefon və şəxsi əlaqə məlumatı git-ə yazılmır:
> onların yeri hədəf serverdir.

| № | Nə | Dəyər | Hara yazılır | Gələnə qədər bloklanır |
|---|---|---|---|---|
| 1 | Hədəf server: host adı, əməliyyat sistemi, disk, backup üçün ikinci host | _boş_ | `infra/.env` (serverdə): `SITE_ADDRESS`, `PUBLIC_URL`, `BACKUP_REMOTE`; aşağıdakı "Hədəf server" cədvəli; `docs/perf/target.md` | Hədəf serverə yerləşdirmə; serverdə `university` yük testi; ikinci maşında bərpa sınağı; backup yaşı, disk və göndərmə xətası xəbərdarlıqları; Checkpoint F-in bərpa və yük testi bəndi |
| 2 | Windows-da SEB 3.x ilə əl sınağı | _boş_ | Aşağıdakı "Əl sınaqları" cədvəli; `tasks/todo.md`, Task 28-in son meyarı | Task 28-in "fayl Windows-da SEB 3.x ilə açılır" meyarı; `seb` rejimli ilk real imtahan (dalğa 2) |
| 3 | İstinad `.seb` faylı və onun açarı | _boş_ | `tests/fixtures/reference.seb` və `tests/fixtures/reference.seb.key` (SEB Config Tool-un göstərdiyi açar) | Task 28-in "Config Key SEB Config Tool-un açarı ilə eynidir" meyarı: `tests/unit/test_seb_config_key.py` fayl qoyulana qədər bu yoxlamanı buraxır |
| 4 | İnsident əlaqələri: adlar və telefonlar | _boş_ | Hədəf serverdəki `docs/runbooks/incident.md` nüsxəsi, "Rollar və əlaqə" cədvəli | İnsident cavabının hazırlığı: 1-ci səviyyəli insidentdə kimə zəng ediləcəyi bilinmir; Checkpoint F-də sahibin buraxılış qərarı |
| 5 | Təhlükəsizlik əlaqəsi və onun yoxlanma tarixi | _boş_ | `infra/.env` (serverdə): `ZEKA_SECURITY_CONTACT` (`mailto:` və ya `https:`), `ZEKA_SECURITY_EXPIRES` (İİİİ-AA-GG, ən çox bir il sonra) | `/.well-known/security.txt`: hər iki dəyər olmadan fayl verilmir (Task 41); kənardan zəiflik bildirişinin ünvanı |
| 6 | T0: dalğa 0-ın idxal olunduğu ixracın anı | _boş_ | Aşağıdakı "Anlar" cədvəli; idxalda `--as-of`, `migration_files.exported_at` | Dalğa 0-ın idxalı və `M reconcile --wave 0` (Task 44-ün "T0 ixracına qarşı uzlaşdırma" meyarı); Checkpoint F-in uzlaşdırma bəndi |

## Hədəf server

| Sahə | Dəyər |
|---|---|
| Host adı (DNS) | _boş (1)_ |
| Əməliyyat sistemi | _boş (1)_ |
| Disk (həcm, növ) | _boş (1)_ |
| Backup üçün ikinci host | _boş (1)_ |

## Anlar

| An | Dəyər | Qeyd |
|---|---|---|
| T0 | _boş (6)_ | Dalğa 0-ın idxal olunduğu ixracın anı (`docs/runbooks/cutover.md`) |
| T1 | _sonra_ | Dalğa 1-in kəsid anı; dalğa 1-dən əvvəl kəsid siyahısı ilə təyin olunur |

## Əl sınaqları

| Sınaq | Kim | Tarix | Nəticə |
|---|---|---|---|
| SEB 3.x, Windows: `config.seb` açılır, yalnız imtahan görünür, çıxış parolu işləyir | _boş (2)_ | _boş_ | _boş_ |

## Buraxılış addımları

Hər addım boş yerlərdən biri gələndən sonra mümkündür (mötərizədə nömrəsi).

1. **Yerləşdirmə (1).** `docs/runbooks/deploy.md`, "İlk quraşdırma". Saat yoxlanır, `infra/.env` doldurulur (5 də
   daxil), `M create-admin` ilk administratoru yaradır.
2. **Yük testi (1).** Canlı məlumatdan əvvəl, ayrıca müvəqqəti bazada:
   `python tools/loadtest.py --scenario mixed --users 1000 --dataset university --seconds 300` və
   `--scenario exam --users 500 --dataset university --seconds 300`. Hədd: p95 < 500 ms, itki 0. Nəticə
   `docs/perf/target.md`-yə yazılır, müvəqqəti baza silinir.
3. **Dalğa 0 (6).** İdxal `docs/runbooks/faculty-onboarding.md` ilə aparılır, sonra
   `M reconcile --wave 0 --source <mənbə> --dir <qovluq>` işlədilir. Fərq 0 olmalıdır, ya da hər fərqin izahı yazılır.
4. **Hər rol üçün tüstü yoxlaması.** Tələbə, müəllim, dekanlıq, rəhbərlik və admin bir dəfə daxil olur, öz əsas
   səhifəsini açır.
5. **Backup və bərpa (1).** Cədvəl üzrə backup ikinci hosta gedir. `infra/restore.sh` ikinci maşında açarın kənar
   nüsxəsi ilə işlədilir (`docs/runbooks/backup.md`).
6. **İzləmə (1, 4).** Bu hallar üçün adı yazılmış alıcıya xəbərdarlıq qurulur və hər biri bir dəfə sınaqdan keçirilir:
   - `/healthz` cavab vermir;
   - boş disk 20%-dən azdır;
   - backup 26 saatdan köhnədir;
   - göndərmə xətası var.
7. **SEB (2, 3).** "Əl sınaqları" cədvəli doldurulur. İstinad fayl qoyulandan sonra
   `python -m pytest tests/unit/test_seb_config_key.py -q` keçir.
8. **Keç və ya keçmə baxışı.** SPEC-in Success Criteria siyahısı üzrə aparılır. Sahib siyahını və buraxılış qərarını
   yazılı təsdiqləyir, sonra `v1.0.0` teqi qoyulur (teq sahibin icazəsi ilə).
