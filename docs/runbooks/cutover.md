# Runbook: dalğa üzrə kəsid siyahısı

Kəsid: bir varlığın sahibinin köhnə sistemdən Zəka-ya keçdiyi an. Dalğalar və "Qeydin sahibi" cədvəli `tasks/plan.md`-dədir;
bu siyahı həmin cədvəli addımlara çevirir. `M` aşağıda `docker compose -f infra/compose.yml exec app python backend/manage.py`
deməkdir.

## Anlar

| An | Mənası | Harada yazılır |
|---|---|---|
| T0 | Dalğa 0-ın idxal olunduğu ixracın anı | `docs/runbooks/release-v1.md`, `migration_files.exported_at` |
| T1 | Dalğa 1-in kəsid anı: köhnə sistemin jurnal, cədvəl və tapşırıq modulları yalnız oxunur | `docs/runbooks/release-v1.md` |

## Qeydin sahibi (qısa)

| Varlıq | T1-ə qədər | T1-dən sonra |
|---|---|---|
| Şəxslər, struktur, fənn, cari qeydiyyat, status əmrləri | Köhnə sistem → Zəka (təkrar idxal; status əmrləri `status-events`) | Zəka → ixrac |
| Cədvəl, otaq | Zəka (ilk idxaldan) | Zəka |
| Davamiyyət, cari ballar | A variantı: köhnə sistem əsasdır, pilot müəllim hər ikisinə yazır | Zəka |
| İmtahan nəticələri | Dalğa 2-yə qədər köhnə sistem | Dalğa 2-dən Zəka, ehtiyat nüsxə köhnə sistemə |

## Kəsiddən bir gün əvvəl

- [ ] `timedatectl show -p NTPSynchronized --value` → `yes`.
- [ ] Backup: `docker compose -f infra/compose.yml run --rm -T backup`, kod 0. Bərpa sınağı (`infra/restore.sh`) keçir.
- [ ] Son gündəlik uzlaşdırma: `M reconcile --wave <n> --source <mənbə> --dir <qovluq>` → `RECONCILED` və ya hər fərq izahlı.
- [ ] Kəsid anında açıq imtahan yoxdur (yazan idxal rədd olunur).
- [ ] Dekanlar, tədris şöbəsi və köhnə sistemin operatoru kəsid saatını bilir.
- [ ] Geri qayıtma pəncərəsi təsdiqlənib (susmaya görə 14 gün).

## Kəsid anı

1. Köhnə sistemdə yazma dayandırılır (operator). An yazılır: **T1 = YYYY-MM-DDTHH:MM**.
2. Köhnə sistemdən son ixrac. Fayllar dəyişməz saxlanır (SHA-256 `migration_files`-ə düşür).
3. Köhnə sistemin sahib olduğu qalıq və ballar kəsid tarixi ilə yenidən idxal olunur. Fərqdə köhnə sistemin dəyəri
   qalır:
   ```bash
   python tools/etl/run.py --mapping content/mappings/<mənbə>.json --dir <son ixrac> --wave <n> --as-of <T1 tarixi> --by <admin> --dry-run
   python tools/etl/run.py --mapping content/mappings/<mənbə>.json --dir <son ixrac> --wave <n> --as-of <T1 tarixi> --by <admin>
   ```
   Konflikt hesabatı boş deyilsə və köhnə sistemin dəyəri qalmalıdırsa, həmin növ `M import ... --prefer source` ilə
   təkrar yüklənir (auditli).
4. Uzlaşdırma: `M reconcile --wave <n> --source <mənbə> --dir <son ixrac> --out reconcile-T1.json` → `RECONCILED`.
5. Backup (kod 0).
6. Elan: həmin varlıqlar indi yalnız Zəka-ya yazılır.

## Kəsiddən sonra

- İlk 14 gecə gündəlik uzlaşdırma. Köhnə sistemdə T1-dən sonra yazı 0 olmalıdır.
- Status əmrləri: Zəka-da daxil edilir, "Tələbə-məzun" sisteminə dəyişiklik siyahısı ilə ötürülür
  (`M export --kind status-changes --since <T1>`). 225 nömrəli Fərmana görə dəyişiklik 10 gün ərzində daxil edilir.

## Geri qayıtma (pəncərə ərzində)

Yalnız ciddi problemdə və sahibin qərarı ilə.

1. Zəka-da həmin varlıqlar yalnız oxunur: müəllimlərə və dekanlığa elan edilir, yazan idxallar dayandırılır.
2. Kəsiddən sonra Zəka-da yazılanların ixracı:
   ```bash
   M export --kind grades --since <T1> --out grades-since-T1.csv
   M export --kind attendance --since <T1> --out attendance-since-T1.csv
   M export --kind status-changes --since <T1> --out status-since-T1.csv
   M export --kind oneroster --out oneroster.zip             # tam vəziyyət: OneRoster ixracı --since qəbul etmir
   ```
   Fayllar dekanlığa verilir və ya köhnə sistemə idxal olunur.
3. Köhnə sistem yazma rejiminə qaytarılır (operator). Qayıdış anı yazılır.
4. Pəncərədən sonra geri qayıtma yoxdur: yalnız irəli düzəliş.

## Sınaq icrası

Geri qayıtma ixracı 2026-11-20-də sınaq konteynerində `university` dəstində işlədilib, müddəti
`docs/runbooks/restore-log.md`-dədir. Hədəf serverdə ilk icra Task 44-dədir.
