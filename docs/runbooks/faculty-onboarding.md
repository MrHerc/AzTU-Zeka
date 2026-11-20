# Runbook: fakültənin qoşulması

Bir fakültənin köhnə sistemdən Zəka-ya keçməsi: idxal → uzlaşdırma → təlim. Dalğalar, kəsid anları və "Qeydin sahibi"
cədvəli `tasks/plan.md`-dədir. Kəsid günü `docs/runbooks/cutover.md` ilə aparılır. `M` aşağıda
`docker compose -f infra/compose.yml exec app python backend/manage.py` deməkdir.

## 1. Hazırlıq (1–2 həftə əvvəl)

| # | Nə | Kim |
|---|---|---|
| 1 | Fakültənin, kafedraların, qrupların və fənlərin siyahısı köhnə sistemdən ixrac olunur | Köhnə sistemin operatoru |
| 2 | İxracın anı (T0) yazılır: hansı tarix və saatın vəziyyətidir | Operator |
| 3 | Xəritə faylı: `content/mappings/<mənbə>.json` (nümunə: `sample-sis.json`). Hər sütun ya xəritələnir, ya `ignore` ilə səbəbi yazılır | Admin |
| 4 | Dekanlığa və tədris şöbəsinə rol təyinatı (fakültə əhatəsi ilə) | Admin |
| 5 | İşçi hesablarında ikinci faktor (TOTP) qurulur | Hər işçi |

## 2. İdxal

Hər addım əvvəlcə quru sınaqla (`--dry-run`) işlədilir: heç nə yazılmır, hesabat çıxır. Hesabat təmiz olandan sonra
eyni əmr `--dry-run` olmadan işlədilir. İdxal ya tam yazılır, ya heç yazılmır.

```bash
# bir dalğanın bütün faylları, xəritə ilə (bölmə, çevirmə, hesabat)
python tools/etl/run.py --mapping content/mappings/<mənbə>.json --dir <ixrac qovluğu> --wave 0 --as-of <T0 tarixi> --by <admin> --dry-run
python tools/etl/run.py --mapping content/mappings/<mənbə>.json --dir <ixrac qovluğu> --wave 0 --as-of <T0 tarixi> --by <admin>
```

ETL faylları xəritədəki sıra ilə yükləyir. Xəritədə bu sıra saxlanır, çünki hər növ əvvəlkinə istinad edir: struktur (`orgs`) → semestrlər (`terms`) → fənlər (`courses`) → siniflər (`classes`) →
şəxslər (`users`) → qeydiyyat (`enrollments`) → cədvəl və otaqlar → davamiyyət (`attendance`, `attendance-opening`) →
cari ballar (`grades`) → yekun qiymətlər (`results`) → status əmrləri (`status-events`).

Qaydalar:
- Yazan idxal dərs saatlarından kənar işlədilir (axşam və ya həftə sonu).
- Açıq imtahan varsa yazan idxal rədd olunur. `--force` yalnız sahibin icazəsi ilə, auditə yazılır.
- 199 999 sətirdən böyük fayl rədd olunur: ETL onu özü bölür.
- Zəka-da dəyişdirilmiş sətir üstünə yazılmır, konflikt hesabatına düşür. Mənbənin dəyəri lazımdırsa: `--prefer source`
  (auditli).

## 3. Uzlaşdırma

```bash
M reconcile --wave 0 --source <mənbə> --dir <ixrac qovluğu> --out reconcile-wave0.json
```

- Hər fayl yükləndiyi andakı SHA-256 ilə yoxlanır. Dəyişmiş və ya itmiş fayl fərqdir.
- Varlıq üzrə: mənbənin sətir sayı = Zəka-da bağlı sətir sayı.
- Tələbə × fənn üzrə qayıb saatları.
- 50 təsadüfi qeyd: dekanlıq onları köhnə sistemlə əl ilə müqayisə edir və nəticəni imzalayır.
- `RECONCILED` çıxmalıdır. Hər fərq ya düzəldilir, ya sətir-sətir izah yazılır.
- Tarixi qiymətləri uzlaşan tələbənin transkripti bundan sonra verilə bilər.

## 4. Hesabların açılması

```bash
M activation-codes --faculty <kod> --out codes.csv        # tələbələr üçün birdəfəlik kodlar
```

`codes.csv` dekanlığa şifrəli şəkildə verilir və paylanandan sonra silinir. Kodla daxil olan tələbə özü parol qurur.
Müəllim və işçilər: müvəqqəti parol (`must_change`) və ya SSO.

## 5. Təlim

| Kim | Nə | Harada |
|---|---|---|
| Müəllimlər | Jurnal (davamiyyət və bal), fənn səhifəsi, materiallar, Test studiyası, imtahan | Portalda "Bələdçi" (`/guide`), AI Akademiya modulları |
| Dekanlıq | Müraciətlər, sənədlər, imtahan cədvəlləri, istisnalar | `/office`, `/office/exams` |
| Tələbələr | Giriş, cədvəl, AI tutor, e-xidmətlər | Birinci girişdə tur, `/guide` |

Təlim bitəndə sınaq həftəsi: müəllim hər iki sistemə yazır ("Qeydin sahibi", A variantı). Gündəlik uzlaşdırma fərqi 0
və ya izahlı olmalıdır.

## 6. Bitdi meyarı

- Uzlaşdırma `RECONCILED`, 50 qeydin əl yoxlaması imzalı.
- Hər müəllim ən azı bir dərsin davamiyyətini Zəka-da yazıb.
- Dəstək sorğuları sabitləşib.
- Kəsid günü planlaşdırılıb (`docs/runbooks/cutover.md`).

## Sınaq icrası

İdxal, uzlaşdırma və hesab kodları sintetik dalğa 0 faylları ilə sınaqdan keçir: `tests/migration/test_etl.py`
(`tests/fixtures/make_fixtures.py` faylları yaradır). Real fakültənin ixracı ilə ilk icra Task 44-dədir.
