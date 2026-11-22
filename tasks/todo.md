# Tapşırıqlar: Zəka V1

Mənbə: `SPEC.md`, `tasks/plan.md` · Vəziyyət: **təsdiq gözləyir**
Ölçü: S = 1–2 fayl, M = 3–7 fayl, L = 8 və daha çox fayl və ya bir neçə dilim (hər dilim ayrıca commit). Yollar Task 3-dən sonrakı quruluşa görədir.
Hər tapşırıq üçün ümumi şərt: `python -m pytest -q`, `ruff check .`, `mypy` yaşıl; yeni sətirlər üç dildə.

---

## Faza 1 — Birləşdirmə və bünövrə

## Task 1: Beş PR-ı birləşdir — TAMAMLANDI (commit `9d23e99`)

> Nəticə: 698 test keçdi (639 + 30 təhlükəsizlik + 26 Radar + 3 yeni); ruff və mypy təmiz; i18n en/ru 100%.
> Köçürülən 43 təhlükəsizlik və 26 Radar yoxlamasının hamısı pytest-dədir. Heç bir test silinməyib və ya keçilməyib.
> Qalan qeydlər: `docs/ARCHITECTURE.md` və `docs/API.md` köhnə `main`-i təsvir edir (Task 3-də yenilənir);
> `/api/demo/storyline` giriş kodu olmadan cavab verir (Task 5-də prod rejimində bağlanır); Docker obrazı qurulub sınanmayıb (Task 9).

**Description:** `trial/integration` sınaq budağının nəticəsi iş budağına gətirilir. Sıra: #3, #5, #4, #2, #1; hər biri `-Xignore-cr-at-eol` ilə. HTTP qatında #5-in `web.Body` oxuyucusu və #3-ün bütün qoruyucuları qalır. #3 və #4-ün `tests/selftest.py`-a yazdığı yoxlamalar pytest-ə köçürülür.

**Acceptance criteria:**
- [x] Test sayı ən azı 639 + köçürülən təhlükəsizlik və Radar yoxlamalarıdır; heç bir test zəiflədilməyib, keçilməyib, silinməyib
- [x] #3-ün qoruyucuları yerindədir: CSRF, sorğu ölçüsü və `Transfer-Encoding` yoxlaması, başlıq doğrulaması, limitlər, giriş kodu, sessiya müddəti
- [x] `python tools/i18n.py stats` en və ru üçün 100% göstərir

**Verification:**
- [x] `python -m pytest -q`
- [x] `ruff check . && mypy && for f in static/js/*.js; do node --check "$f"; done`
- [x] `python run.py --reset --port 5123` açılır, `/api/bootstrap` 200 qaytarır

**Dependencies:** None
**Files likely touched:** `app/web.py`, `app/r_core.py`, `app/r_academy.py`, `app/r_learning.py`, `tests/integration/test_security_review.py`, `tests/integration/test_radar.py`, `README.md`, tərcümə kataloqları
**Estimated scope:** L (birləşdirmə; yeni funksiya yazılmır)

## Task 2: Sətir sonlarını sabitlə

**Description:** `.gitattributes` əlavə olunur (`* text=auto eol=lf`, `*.bat text eol=crlf`, ikili fayllar `binary`). Bütün repo bir ayrıca commit-də normallaşdırılır. Həmin commit-də başqa dəyişiklik olmur.

**Acceptance criteria:**
- [x] `git ls-files --eol | grep -c "i/crlf"` 0 qaytarır
- [x] Normallaşdırma commit-i `git diff -w` ilə boşdur
- [x] `start_demo.bat` Windows-da işləyir (CRLF qalır)

**Verification:**
- [x] `git ls-files --eol | awk '{print $1}' | sort | uniq -c`
- [x] `python -m pytest -q`

**Dependencies:** Task 1
**Files likely touched:** `.gitattributes`, bütün CRLF faylları (yalnız sətir sonu)
**Estimated scope:** S

## Task 3: Repo-nu dilə və qata görə böl

**Description:** `git mv` ilə köçürmə, iki commit: (1) `app/` → `backend/zeka/core/` və `backend/zeka/legacy/`, `run.py` → `backend/run.py`; (2) `static/` → `frontend/`, Docker və yerləşdirmə faylları → `infra/`. İdxal yolları, statik qovluq yolu, CI, `pyproject.toml`, README və `CLAUDE.md` yenilənir. Qat qaydasını yoxlayan test əlavə olunur.

**Acceptance criteria:**
- [x] Davranış dəyişmir: bütün testlər dəyişdirilmədən (yalnız idxal yolu) yaşıldır
- [x] `git log --follow` köçürülən fayllar üçün tarixçəni göstərir (təmiz adlandırma)
- [x] `tests/unit/test_layers.py`: heç bir `domain.py` `core.web`, `core.db` və ya `sqlite3` idxal etmir
- [x] `docs/ARCHITECTURE.md` və `docs/API.md` birləşdirilmiş vəziyyəti təsvir edir: sessiya müddəti, giriş kodu, Radar marşrutları, pytest

**Verification:**
- [x] `python -m pytest -q`
- [x] `python backend/run.py --port 5123` açılır; əsas səhifə və `/static/` yolları işləyir
- [x] `docker build -f infra/Dockerfile .`

**Dependencies:** Task 2
**Files likely touched:** bütün `app/`, `static/` (köçürmə), `backend/run.py`, `pyproject.toml`, `.github/workflows/*.yml`, `CLAUDE.md`, `README.md`
**Estimated scope:** L (mexaniki köçürmə, iki commit)

## Task 4: Miqrasiya mühərriki

**Description:** `core/migrate.py`: `schema_migrations(version, name, checksum, applied_at)` cədvəli, `backend/migrations/NNNN_ad.sql` faylları, hər miqrasiya ayrıca tranzaksiyada. `0001_baseline.sql` indiki sxemdir. Prod rejimində `store.init()` bazanı heç vaxt silmir. `manage.py migrate | status`.

Fayl adı `NNNN_ad.sql`, NNNN = tapşırıq nömrəsi × 10 (Task 12 → `0120_totp.sql`); eyni tapşırığın sonrakı düzəlişi və ya ikinci dilimi `0121_…`. Birləşdirilmiş (commit olunmuş) miqrasiya faylı redaktə edilmir, hər tapşırıq öz faylını əlavə edir. Mühərrik `schema_migrations`-da olmayan hər faylı nömrə sırası ilə tətbiq edir; nömrələrdə boşluq və kiçik nömrənin gec gəlməsi xəta deyil. Miqrasiya yalnız öz tapşırığının `Dependencies` zəncirindəki cədvəllərə söykənir. Tapşırıq daha böyük nömrəli tapşırığın cədvəlinə söykənirsə, onun miqrasiyası həmin fayldan böyük nömrə alır (Task 35 → `0365_community.sql`, `0360`-dan sonra).

**Acceptance criteria:**
- [x] `PRAGMA user_version = 4` olan (indiki `SCHEMA_VERSION`) demo bazası miqrasiyadan sonra hər cədvəldə eyni sətir sayına malikdir
- [x] Tətbiq olunmuş miqrasiya faylı dəyişdirilibsə (checksum), bazada faylı olmayan versiya qeydi varsa (baza daha yeni koddandır) və ya eyni NNNN ilə iki fayl varsa, server açılmır və səbəbi yazır
- [x] `0001` və `0030` tətbiq olunmuş bazaya sonradan əlavə olunan `0020` tətbiq olunur (test)
- [x] Hər miqrasiyadan əvvəl bazanın nüsxəsi yaradılır; son 5 nüsxə saxlanır

**Verification:**
- [x] `python -m pytest tests/migration/test_schema_migrations.py -q`
- [x] `python backend/manage.py status`

**Dependencies:** Task 3
**Files likely touched:** `backend/zeka/core/migrate.py`, `backend/zeka/core/db.py`, `backend/migrations/0001_baseline.sql`, `backend/manage.py`, `tests/migration/test_schema_migrations.py`
**Estimated scope:** M

## Task 5: İş rejimləri: demo və prod

**Description:** `core/config.py` bütün ayarları mühit dəyişənlərindən oxuyur. `ZEKA_MODE=prod`: demo giriş marşrutları, seed və reset qeydiyyatdan keçmir. Loopback olmayan ünvanda prod rejimi məcburidir. `manage.py create-admin` ilk administratoru yaradır. Prod rejimində `PUBLIC_URL` `https://` ilə başlayırsa və `ZEKA_PROXY_HOPS=0`-dırsa server açılmır və səbəbi yazır (tətbiq TLS danışmır, deməli qabaqda proksi var).

Saat (plan A19). `core/clock.py`: `now()` (UTC, ofsetli) və `local()` (`ZEKA_TZ`, susmaya görə `Asia/Baku`). `store.now()` `clock.local()`-dan oxuyur; legacy davranışı dəyişmir. Prod rejimində qurşaq tapılmasa server açılmır və səbəbi yazır. Demo rejimində tz bazası yoxdursa (Windows) OS vaxtı işlənir. `ruff` `DTZ005` və `DTZ011` açılır: `clock.py`-dən kənarda `datetime.now()` və `date.today()` lint xətasıdır. CI-da bir ubuntu matris sətri `TZ: America/Los_Angeles` ilə işləyir.

**Acceptance criteria:**
- [x] Prod rejimində `/api/auth/demo`, `/demo/login`, `/api/demo/storyline`, `/api/admin/reset` 404 qaytarır
- [x] `--host 0.0.0.0` demo rejimində açılmır
- [x] Prod rejimində `PUBLIC_URL=https://…` və `ZEKA_PROXY_HOPS=0` ilə server açılmır
- [x] Boş prod bazası yalnız `create-admin` ilə yaradılan hesabla açılır; heç bir sintetik istifadəçi yoxdur
- [x] Proses `TZ=America/Los_Angeles`, `ZEKA_TZ=Asia/Baku`, saat 06:00Z-yə sabitlənib: `/api/student/home` 10:00–11:30 dərsini `now` göstərir (Linux; tz bazası olmayan Windows-da keçilir)
- [x] Prod rejimində mövcud olmayan `ZEKA_TZ` dəyəri ilə server açılmır; `ruff check .` `clock.py`-dən kənarda `datetime.now()` və `date.today()` çağırışı tapmır

**Verification:**
- [x] `python -m pytest tests/integration/test_modes.py tests/integration/test_clock.py -q`
- [x] `ZEKA_MODE=prod python backend/run.py` və `curl -s -o /dev/null -w "%{http_code}" -X POST localhost:5070/api/auth/demo`

**Dependencies:** Task 4
**Files likely touched:** `backend/zeka/core/config.py`, `backend/zeka/core/clock.py`, `backend/run.py`, `backend/manage.py`, `backend/zeka/legacy/r_core.py`, `backend/zeka/legacy/r_admin.py`, `backend/zeka/legacy/store.py`, `tests/integration/test_clock.py`, `pyproject.toml`, `.github/workflows/ci.yml`
**Estimated scope:** L (iki dilim: iş rejimləri; saat)

## Task 6: Handler qapısı və çox proses

**Description:** Handler icrası sayı məhdud semaforla əhatələnir (`ZEKA_HANDLERS`, susmaya görə 2). Xaricə şəbəkə çağırışı edən marşrut (`slow=True`: LLM, OIDC) əsas 2 slotu tutmur, ayrıca hədli semaforda gedir (`ZEKA_SLOW`, susmaya görə 4); hər xarici çağırışın açıq vaxt aşımı var (≤ 15 s). Növbə vaxtı bitəndə 503 və `Retry-After`. `run.py --workers N`: `SO_REUSEPORT` ilə eyni portu paylaşan N proses, düşəni yenidən başladan nəzarətçi, səliqəli dayanma. `/healthz` əlavə olunur; `server_time` (UTC, ofsetli) və `tz` qaytarır. `tools/loadtest.py` yazılır. `--dataset demo|faculty|university` müvəqqəti bazada sintetik dəst yaradır (faculty: 2 000 tələbə, 12 000 qeydiyyat, 1 200 cədvəl sətri, 20 000 cəhd, 20 000 hissə; university: 10 000 / 60 000 / 6 000 / 100 000 / 100 000); hər ssenarinin marşrut qarışığı və düşünmə fasiləsi faylın başında yazılır.

**Acceptance criteria:**
- [x] 300 paralel müştəri, oxu ssenarisi: 0 xəta, tək prosesdə ≥ 200 sorğu/san (ölçülmüş baza: 221; demo baza, qapının reqressiya yoxlaması)
- [x] 4 proses tək prosesin ən azı 2,5 mislini verir
- [x] Semafor sızmır: 1 000 xətalı sorğudan sonra normal sorğu cavab alır; öldürülən proses demo bazada 2 saniyəyə bərpa olunur; işçi dinləmə yuvasını yalnız indeksi qurandan sonra açır və bu müddətdə qalan proseslər xətasız cavab verir
- [x] 4 paralel 10 saniyəlik `slow` handler gedərkən oxu və yazma sorğuları: 5xx = 0, p95 ≤ 500 ms

**Verification:**
- [x] `python tools/loadtest.py --scenario read --users 300 --seconds 30 --dataset demo`
- [x] `python -m pytest tests/integration/test_concurrency.py -q`

**Dependencies:** Task 3
**Files likely touched:** `backend/zeka/core/web.py`, `backend/run.py`, `tools/loadtest.py`, `tests/integration/test_concurrency.py`
**Estimated scope:** M

## Task 7: Proses-lokal vəziyyəti bazaya köçür

**Description:** Birdəfəlik sənəd açarları (`common._DOC_KEYS`) və limit sayğacları (`security.py`) cədvələ keçir. Axtarış indeksləri hər prosesdə qurulur; `index_version` dəyişəndə proses yalnız dəyişən sənədləri (əlavə, yenilənmə, silinmə) tətbiq edir; tam qurma yalnız proses başlayanda olur. `0071_hot_path_indexes.sql`-də isti yol indeksləri (0070 artıq tətbiq olunmuşdu): `attempts(user_id, quiz_id)`, `timetable(course_id)`, `enrollments(course_id)`, `quizzes(course_id)`, `materials(course_id)`, `lessons(course_id)`; `student_home` və `/api/schedule` cədvəli yalnız istifadəçinin fənləri üzrə, hər fənnə bir indeksli sorğu ilə oxuyur (`week_timetable`).

**Acceptance criteria:**
- [x] A prosesinin verdiyi açarı B prosesi bir dəfə qəbul edir, ikinci istifadə rədd olunur
- [x] Limit proses sayına vurulmur: N proseslə də eyni hədd tətbiq olunur
- [x] Limit sayğacı öz qısa tranzaksiyasında yazılır və dərhal commit olunur; test rejimində ilk yazmadan commit-ə qədər 200 ms-dən uzun sorğu tranzaksiyası testi yıxır (idxal istisna)
- [x] A prosesindən yüklənən material B prosesində növbəti sorğuda axtarışda çıxır
- [x] `university` dəstində (100 000 hissə) material yükləndikdən sonra digər prosesin növbəti axtarışı ≤ 200 ms gecikir (tam yenidənqurma yoxdur); işçinin başlanğıc müddəti və proses başına indeks yaddaşı ölçülüb və `docs/perf/baseline.md`-də yazılıb
- [x] `university` dəstində oxu ssenarisinin marşrutlarının icra etdiyi heç bir sorğunun `EXPLAIN QUERY PLAN`-ında 1 000 sətirdən böyük cədvəl üzrə `SCAN` yoxdur (`tests/load/test_query_plans.py`; Task 42 qarışıq və imtahan ssenarilərini əlavə edir)
- [x] `faculty` dəstində tək prosesin oxu ssenarisi demo nəticəsinin ≥ 60%-ni verir (hədd: SPEC Open Questions 23) və 300 paralel müştəridə 0 xəta; `university` nəticəsi `docs/perf/baseline.md`-də yazılıb

**Verification:**
- [x] `python -m pytest tests/integration/test_multiworker_state.py -q` (iki prosesli server ilə)
- [x] `python -m pytest tests/load/test_query_plans.py -q`
- [x] `python tools/loadtest.py --scenario read --users 300 --seconds 30 --dataset faculty` və eyni əmr `--dataset university` ilə

**Dependencies:** Task 4, Task 6
**Files likely touched:** `backend/zeka/core/security.py`, `backend/zeka/legacy/common.py`, `backend/zeka/legacy/engine.py`, `backend/zeka/legacy/r_learning.py`, `backend/migrations/0070_shared_state.sql`, `tools/loadtest.py`, `tests/load/test_query_plans.py`, `docs/perf/baseline.md`
**Estimated scope:** L (iki commit: paylaşılan vəziyyət; indekslər və ölçmə)

## Task 8: Backup və bərpa

**Description:** `infra/backup.sh` `backend/manage.py backup` əmrini çağırır: `sqlite3.Connection.backup()` tək addımda (və ya `VACUUM INTO`) ardıcıl nüsxə; `sqlite3` CLI istifadə olunmur (100 səhifəlik addımlar başqa bağlantının hər commit-ində nüsxəni yenidən başladır). Yükləmələrdən yalnız əvvəlki dəstlərdə olmayan fayllar (məzmun ünvanlıdır), sıxılma, `openssl enc -aes-256-cbc -pbkdf2` ilə şifrələmə, SHA-256 manifest. Sonra dəst `BACKUP_REMOTE`-a (ölkə daxilində ikinci host) göndərilir və manifest orada yoxlanır; prod rejimində `BACKUP_REMOTE` boşdursa və ya göndərmə alınmırsa skript xəta ilə bitir. Saxlama: 7 gündəlik, 4 həftəlik. `infra/restore.sh` manifesti yoxlayır, yeni qovluğa bərpa edir, `PRAGMA integrity_check` işlədir.

**Acceptance criteria:**
- [x] Təmiz qovluğa bərpa hər cədvəldə eyni sətir sayını və hər yükləmə üçün eyni SHA-256-nı verir
- [x] Açar faylı olmadan backup uğursuz bitir, şifrəsiz fayl yaratmır
- [x] Başqa proses hər 20 ms-dən bir commit edərkən backup yazı getməyən bazadakı müddətin 3 mislindən tez bitir; bərpada `integrity_check` keçir
- [x] Göndərmə uğursuz olanda skript sıfırdan fərqli kodla bitir; uzaq tərəfdə manifest yoxlanır
- [x] CI-da backup → bərpa sınağı işləyir

**Verification:**
- [x] `infra/backup.sh && infra/restore.sh backups/latest.enc /tmp/restore-test`
- [x] `python -m pytest tests/migration/test_backup_restore.py -q`

**Dependencies:** Task 4
**Files likely touched:** `infra/backup.sh`, `infra/restore.sh`, `backend/manage.py`, `tests/migration/test_backup_restore.py`, `.github/workflows/ci.yml`
**Estimated scope:** M

## Task 9: Yerləşdirmə: Docker, Caddy, sağlamlıq yoxlaması

**Description:** `infra/Dockerfile` (root olmayan istifadəçi, sağlamlıq yoxlaması), `infra/compose.yml` (tətbiq + Caddy; həcmlər: məlumat, backup, sertifikat), `infra/Caddyfile` (TLS, HSTS, sorğu ölçüsü həddi 16 MB), `infra/.env.example`. Giriş jurnalı JSON formatında stdout-a. `compose.yml`-də tətbiq servisinin `ports:` bəndi yoxdur (yalnız daxili şəbəkə); `ZEKA_MODE=prod`, `PUBLIC_URL` və `ZEKA_PROXY_HOPS=1` `.env.example`-dədir. Caddyfile-da `trusted_proxies` təyin olunmur. Qabaqda ikinci proksi olarsa hop sayı və `trusted_proxies` birlikdə dəyişir (runbook). `compose.yml`-də hər servis üçün log həddi var (`logging: max-size 50m, max-file 5`). `infra/Dockerfile`-də `ENV TZ=Asia/Baku` (log vaxtı və kənar `datetime.now()` üçün ehtiyat); `.env.example`-də `ZEKA_TZ` və `BACKUP_REMOTE`.

**Acceptance criteria:**
- [x] `docker compose up -d` sonra `https://localhost/healthz` 200 qaytarır; HSTS, CSP, `nosniff` başlıqları var
- [x] `docker inspect` hər konteyner üçün log həddini göstərir
- [x] `docker compose -f infra/compose.yml exec app python -c "import time; print(time.strftime('%z'))"` `+0400` çap edir; `/healthz`-dəki `server_time` hostun `date -u` çıxışından 2 saniyədən çox fərqlənmir
- [x] Konteyner root kimi işləmir; `docker compose restart` məlumatı saxlayır
- [x] `.env.example`-dəki hər dəyişən `docs/runbooks/deploy.md`-də izah olunub
- [x] Caddy arxasında giriş jurnalındakı müştəri ünvanı Caddy konteynerinin ünvanı deyil; müştərinin özü göndərdiyi `X-Forwarded-For: 1.2.3.4` jurnalda ünvan kimi görünmür; tətbiqin portu hostdan açılmır

**Verification:**
- [x] `docker compose -f infra/compose.yml up -d && curl -sk -D- https://localhost/healthz`
- [x] `docker compose -f infra/compose.yml exec app id -u` (0 deyil)
- [x] `docker inspect -f '{{.Name}} {{.HostConfig.LogConfig.Config}}' $(docker compose -f infra/compose.yml ps -q)`: hər sətirdə `max-size:50m` və `max-file:5`
- [x] `curl -sk -H 'X-Forwarded-For: 1.2.3.4' https://localhost/healthz`, sonra `docker compose -f infra/compose.yml logs app | grep -c '1.2.3.4'` 0 qaytarır və jurnaldakı ünvan `docker compose -f infra/compose.yml exec caddy hostname -i` çıxışından fərqlidir; `curl -s -m 3 http://localhost:5070/healthz` qoşula bilmir

Qeyd (2026-11-18): yoxlamalar `SITE_ADDRESS=localhost` ilə keçdi. Sınaq mühiti Debian paket serverini bağladığı üçün image `openssh-client` qurulmadan yoxlanıb; ssh göndərişi testdə saxta ssh ilə yoxlanır. Demo `infra/compose.demo.yml`-ə köçdü.

**Dependencies:** Task 5, Task 6
**Files likely touched:** `infra/Dockerfile`, `infra/compose.yml`, `infra/Caddyfile`, `infra/.env.example`, `docs/runbooks/deploy.md`
**Estimated scope:** M

## Checkpoint A: Task 1–9 sonra

- [x] Bütün testlər yaşıl; rəy axını (tap → təkzib et → düzəlt) keçib — `docs/review/checkpoint-a-2026-11-18.md`
- [x] `docker compose up` ilə HTTPS açılır; yenidən başlatma məlumatı saxlayır
- [x] 300 paralel müştəridə 0 xəta (`demo` və `faculty` dəstləri); bərpa sınağı keçir
- [ ] Sahiblə baxış; commit və push icazəsi

---

## Faza 2 — Kimlik və reyestr

## Task 10: Hesablar və parol

**Description:** `users` cədvəlinə `email`, `password_hash`, `must_change`, `status`, `failed_count`, `locked_until` əlavə olunur. `POST /api/auth/login`, parol dəyişmə, adminin birdəfəlik müvəqqəti parol verməsi. Hash: `hashlib.scrypt`, parametrlər sabitdir və sətirdə saxlanır: n=2^15, r=8, p=1, `maxmem` açıq verilir (stdlib-in susmaya görə həddi bu parametri rədd edir); n=2^17 sahibin qərarı ilə (ölçülüb: 323 ms və 128 MiB hər hash; SPEC Open Questions 21). Hash açıq yazma tranzaksiyası olmadan hesablanır. Siyasət NIST SP 800-63B-4 üzrə: tək amildə ≥ 15 simvol, MFA ilə ≥ 8, ən azı 64-ə icazə, tərkib qaydası və dövri dəyişmə yoxdur, zəif parol siyahısı. Prod rejimində rol seçimi ekranı giriş forması ilə əvəz olunur.

**Acceptance criteria:**
- [x] Yanlış parol və mövcud olmayan istifadəçi eyni cavabı verir; müqayisə sabit vaxtlıdır
- [x] Uğursuz cəhdlər (hesab, müştəri ünvanı; IPv6-da /64) üzrə sayılır: 15 dəqiqədə 10 uğursuz cəhd həmin ünvanı həmin hesab üçün 15 dəqiqə bloklayır (429 və `Retry-After`; handler yatmır; blok scrypt-dən əvvəl yoxlanır; blok zamanı rədd edilən cəhd sayılmır). Hesab üzrə ardıcıl 100 uğursuz cəhd hesabı 15 dəqiqə kilidləyir. Hər blok və kilid audit hadisəsi yazır; admin kilidi səbəblə aça bilir. Test: A ünvanından 50 yanlış parol B ünvanından düzgün girişi gecikdirmir.
- [x] Qısa və siyahıdakı parollar tərcümə olunmuş səbəblə rədd olunur; hash parametri dəyişəndə növbəti girişdə yenidən hesablanır

**Verification:**
- [x] `python -m pytest tests/unit/test_passwords.py tests/integration/test_auth_login.py -q`

Qeyd (2026-11-18): `content/password-blocklist.txt` qısa siyahıdır (≈100); yerləşdirmədə böyük sızmış-parol siyahısı ilə əvəz oluna bilər. Prod giriş forması, məcburi parol dəyişmə pəncərəsi və profil menyusunda "Parolu dəyiş" brauzerdə (Chromium) yoxlanıb. `manage.py create-admin` müvəqqəti parol çap edir.

**Dependencies:** Task 5, Task 7
**Files likely touched:** `backend/zeka/modules/identity/{domain,service,repo,routes}.py`, `backend/migrations/0100_identity.sql`, `frontend/js/main.js`, `content/password-blocklist.txt`
**Estimated scope:** M

## Task 11: Sessiya sərtləşdirməsi

**Description:** Sessiya id-sinin SHA-256-sı saxlanır. `last_seen`, `scope`, `mfa_at` sütunları. Boş və mütləq müddət rola görə: işçi 1 saat və 24 saat, tələbə 8 saat və 30 gün (tenant ayarı). `X-Session` başlığı və JSON-dakı token silinir, yalnız kuki qalır. Giriş və hüquq dəyişikliyində id yenilənir. "Sessiyalarım" siyahısı və ləğv.

**Acceptance criteria:**
- [x] Baza nüsxəsində istifadə edilə bilən sessiya tokeni yoxdur
- [x] Boş və mütləq müddət serverdə tətbiq olunur (saat irəli çəkilən test)
- [x] `X-Session` başlığı nəzərə alınmır; girişdən və MFA-dan sonra sessiya id-si dəyişir

**Verification:**
- [x] `python -m pytest tests/integration/test_sessions.py -q`

**Dependencies:** Task 10
**Files likely touched:** `backend/zeka/modules/identity/{service,repo}.py`, `backend/migrations/0110_sessions.sql`, `backend/zeka/legacy/common.py`, `frontend/js/core.js`, `frontend/js/main.js`
**Estimated scope:** M

## Task 12: İşçi rolları üçün TOTP

**Description:** RFC 6238 (HMAC-SHA1, 30 saniyə, 6 rəqəm, ±1 pəncərə), təkrar istifadəyə qarşı son sayğac saxlanır. Qoşulma mövcud `qr.py` ilə `otpauth://` QR-i göstərir. 10 bərpa kodu, hash ilə. Qiymət yazan və ya idarə edən hər rol üçün məcburi; tələbə üçün könüllü. Yanlış TOTP və bərpa kodu Task 10-dakı (hesab, ünvan) sayğacına düşür. TOTP toxumu bazada açıq saxlanır (stdlib-də simmetrik şifr yoxdur); bu Task 41 təhdid modelində qəbul edilmiş risk kimi yazılır; sahib `cryptography` icazəsi versə mühit açarı ilə şifrələnir.

**Acceptance criteria:**
- [x] RFC 6238 test vektorları keçir
- [x] İkinci amili olmayan işçi yalnız qoşulma marşrutlarına çata bilən sessiya alır
- [x] Eyni kod öz pəncərəsində iki dəfə qəbul olunmur; bərpa kodu bir dəfə işləyir
- [x] 5 ardıcıl yanlış TOTP və ya bərpa kodu gözləyən girişi ləğv edir (parol addımı təkrarlanır); bundan sonra düzgün kod da rədd olunur

**Verification:**
- [x] `python -m pytest tests/unit/test_totp.py tests/integration/test_mfa.py -q`

Qeyd (2026-11-18): bərpa kodu ilə də giriş və 5 yanlış koddan sonra ləğv brauzerdə yoxlanıb. Parolu düz yazmaq gözləyən ikinci addımda sayğacı sıfırlamır (əks halda hər düz parol 5 yeni kod təxmini verərdi); sayğac yalnız ikinci addım keçəndə sıfırlanır.

**Dependencies:** Task 11
**Files likely touched:** `backend/zeka/modules/identity/{domain,service,routes}.py`, `frontend/js/main.js`, `backend/migrations/0120_totp.sql`
**Estimated scope:** M

## Task 13: Rol və icazə modeli

**Description:** Rol id-ləri:

| İstifadəçi növü (SPEC Objective) | Rol id-si | Qeyd |
|---|---|---|
| tələbə | `student` | kodda var |
| müəllim | `teacher` | kodda var |
| kafedra müdiri | `dept_head` | yeni |
| dekanlıq | `office` | kodda var; id dəyişmir (A3) |
| tədris şöbəsi | `academic_office` | yeni |
| imtahan nəzarətçisi | `proctor` | yeni |
| rəhbərlik (rektorluq) | `leader` | kodda var; klub rəhbəri deyil |
| İT admin | `admin` | kodda var |
| klub rəhbəri | rol deyil | Task 35: klubun `rəhbər` sahəsi, obyekt səviyyəli yoxlama |
| moderator | rol deyil | icazələr: `qa.moderate`, `community.moderate` (`core/perms.py`) |

Susmaya görə `qa.moderate`: `office`, `admin`. `community.moderate`: klubun rəhbəri (öz klubunda), `office`, `admin`; klub rəhbərinə qarşı şikayət `office` növbəsinə düşür. Bu bölgünü sahib Checkpoint B-də təsdiqləyir (SPEC Open Questions 24).

`role_grants(user_id, role, scope_type, scope_id)`: bir istifadəçi bir neçə rolu əhatə ilə daşıya bilir. Marşrut dekoratoru `perm="journal.write"` qəbul edir; icazə xəritəsi `core/perms.py`-dədir. Təhlükəsizlik testi marşrut cədvəlindən rol × marşrut matrisi qurur və `tests/security/matrix.json` ilə müqayisə edir. İki dilim: (1) rol modeli və matris; (2) dekanlıq əhatəsi və oxu auditi.

Dekanlıq əhatəsi (dilim 2). Bu gün hər `office`, `leader` və `admin` istifadəçisi bütün universitetin müraciətlərini, tibbi arayış əlavələri daxil, görür (`docs/CODEMAP.md` L5). `office` rolu `role_grants`-də fakültə əhatəsi daşıyır (`scope_type='faculty'`). Müraciət, sənəd və əlavə fayl yalnız tələbəsi həmin fakültədə olan `office` istifadəçisinə açılır; müraciət siyahısı, saylar və yeni müraciət bildirişi eyni əhatə ilə süzülür. Fakültə əhatəsi olmayan `office` hesabı heç bir müraciət görmür. Yoxlama obyekt səviyyəsindədir: `r_services.py`-dəki müraciət və sənəd girişi, `r_core.py`-dəki `file_access`. Rol × marşrut matrisi bununla dəyişmir. Demo seed `office` istifadəçisinə öz fakültəsinin əhatəsini verir.

Oxu auditi (dilim 2). Bu gün başqasının müraciətini və sənədini açmaq audit yazmır (`docs/CODEMAP.md` L7). Başqasının sənədini, əlavə faylını, qiymət siyahısını və ya risk profilini (Radar) qaytaran marşrut `@R(..., audit_read="<növ>")` ilə işarələnir; nüvə hər uğurlu cavabda audit hadisəsi yazır: oxuyan, məlumatın sahibi, obyekt, vaxt. Hadisə öz qısa tranzaksiyasında yazılır (Task 7). İstifadəçinin öz məlumatını oxuması yazılmır. Sonrakı tapşırıqların eyni növ marşrutları (Task 21-in qiymət siyahısı, Task 22-nin göndərişi) eyni işarəni daşıyır.

**Acceptance criteria:**
- [x] Matrisdə olmayan yeni marşrut test dəstini yıxır
- [x] Legacy marşrutlarda mövcud beş rolun (`student`, `teacher`, `office`, `leader`, `admin`) matrisi Task 13-dən əvvəlki ilə eynidir
- [ ] `dept_head` yalnız öz kafedrasının məlumatını görür və dəyişir. `teacher`-in əhatəsi rəhbəri olduğu (`courses.teacher_id`) və ya tədris vahidi (`teaching_units`, Task 15) daşıdığı fənndir; jurnala yalnız öz vahidlərinin və ona keçirilmiş dərslərin (`lessons.teacher_id`) siyahısı üzrə yazır
- [x] Çox rollu istifadəçi aktiv rolu dəyişəndə sessiya id-si yenilənir və audit yazılır
- [x] A fakültəsinin `office` istifadəçisi B fakültəsinin tələbəsinin müraciətinə (`GET /api/requests/{id}`), sənədinə (`/doc/{id}`) və əlavə faylına (`GET /api/files/{id}`) 404 alır, öz fakültəsində 200; `GET /api/requests` siyahısında B fakültəsinin sətri yoxdur; əhatəsiz `office` hesabının siyahısı boşdur
- [x] Başqasının sənədinin, əlavə faylının, qiymət siyahısının və Radar risk profilinin oxunması audit jurnalına oxuyan, sahib və obyekt id-si ilə yazılır; öz məlumatının oxunması yazılmır
- [x] `tests/security/matrix.json` hər marşrutun `audit_read` dəyərini saxlayır; marşrut cədvəli ilə fərq test dəstini yıxır

**Verification:**
- [ ] `python -m pytest tests/security/test_authz_matrix.py tests/security/test_staff_scope.py -q`

Qeyd (2026-11-18): dilim 1 hazırdır (`core/perms.py`, `0130_role_grants.sql`, matris 128 marşrutla Task 13-dən əvvəl qeydə alınıb, yalnız 5 yeni marşrut əlavə olunub, `tests/security/test_roles.py`). Dilim 2: dekanlıq fakültə əhatəsi və oxu auditi hazırdır (`tests/security/test_staff_scope.py`); qiymət siyahısının `audit_read` işarəsi Task 21-də marşrutla birlikdə gəlir. `dept_head` və `teacher` əhatəsi tədris vahidinə (Task 15 dilim 2) və jurnala (Task 20) bağlıdır, ona görə açıq qalır.

**Dependencies:** Task 11; dilim 2 Task 15 (dilim 1: fakültə cədvəli) birləşdiriləndən sonra
**Files likely touched:** `backend/zeka/core/perms.py`, `backend/zeka/core/web.py`, `backend/zeka/core/audit.py`, `backend/zeka/modules/identity/repo.py`, `backend/migrations/0130_role_grants.sql`, `backend/zeka/legacy/{common,r_services,r_core,r_radar}.py`, `tests/security/matrix.json`, `tests/security/test_authz_matrix.py`, `tests/security/test_staff_scope.py`
**Estimated scope:** L (iki dilim, iki commit: rol modeli və matris; dekanlıq əhatəsi və oxu auditi)

## Task 14: SSO: ümumi OIDC müştərisi

**Description:** Authorization Code + PKCE, `state`, `nonce`. Kəşf ünvanı ayardan. Token və `userinfo` birbaşa TLS ilə alınır. Hesab (`iss`, `sub`) cütünə bağlanır; bağlantı `sso_identities(user_id, iss, sub)` cədvəlində saxlanır və sonrakı girişlər yalnız onunla tapılır. İlk bağlantı ayarda adı verilən tələbə nömrəsi iddiası ilə, və ya `email` ilə yalnız `email_verified=true` olanda və yerli hesabın işçi rolu olmayanda qurulur. İşçi rolu olan hesabı yalnız sahibi yerli parol + TOTP sessiyasından, və ya admin bağlayır. ID token OIDC Core 3.1.3.7 üzrə yoxlanır (`iss`, `aud`, `exp`, `nonce`); `userinfo`-nun `sub`-u ID token-in `sub`-u ilə eyni olmalıdır (5.3.2). Issuer və kəşf sənədindəki bütün son nöqtələr `https` olmalıdır; `http` yalnız demo rejimində loopback üçün; sertifikat yoxlamasını söndürən ayar yoxdur. Avtomatik hesab yaradılması susmaya görə bağlıdır. Testlər stdlib ilə yazılmış saxta IdP-yə qarşıdır.

**Acceptance criteria:**
- [x] Saxta IdP ilə tam axın keçir; `state` və ya `nonce` uyğunsuzluğu rədd olunur
- [x] Tanınmayan istifadəçi hesab yaradılmadan "hesab tapılmadı" alır
- [x] IdP MFA təsdiqləmirsə, işçi üçün yerli TOTP tələbi qalır
- [x] Yanlış `iss`, yanlış `aud`, vaxtı keçmiş `exp`, və ya `userinfo` `sub`-u ID token `sub`-undan fərqli olan cavab rədd olunur
- [x] IdP-də `email` dəyişdirilməsi girişi başqa yerli hesaba keçirmir; `email_verified` doğru deyilsə `email` ilə ilk bağlantı qurulmur; işçi hesabı `email` ilə avtomatik bağlanmır
- [x] Prod rejimində `http://` issuer və ya kəşf sənədindəki `https` olmayan son nöqtə ilə SSO açılmır

**Verification:**
- [x] `python -m pytest tests/integration/test_oidc.py -q` (35 test; qaydalar ayrıca `tests/unit/test_sso_rules.py`-də)

Qeyd (2026-11-18): ayarlar `settings.sso`-dadır (T17 ekranı onu idarə edəcək), müştəri sirri yalnız `ZEKA_OIDC_CLIENT_SECRET`.
Başlanmış giriş `zeka_sso` cookie-si ilə brauzerə bağlanır (giriş CSRF-i). Avtomatik hesab yaradılması ümumiyyətlə yazılmayıb.
Real TLS sertifikatlı IdP ilə yoxlanmayıb: testlər demo rejimində loopback `http` istifadə edir.

**Dependencies:** Task 12
**Files likely touched:** `backend/zeka/modules/identity/sso.py`, `backend/zeka/modules/identity/routes.py`, `backend/migrations/0140_sso_identities.sql` (`sso_identities` cədvəli, (`iss`, `sub`) üzrə unikal), `tests/integration/test_oidc.py`, `frontend/js/main.js`
**Estimated scope:** M

## Task 15: Struktur və reyestr idarəsi

**Description:** Cədvəllər: `faculties`, `departments`, `specialties`, `academic_terms`; `study_groups` və `courses` bunlara bağlanır. `academic_terms` tədris dövrünü və imtahan sessiyasını ayrı saxlayır: `teaching_start`, `teaching_end`, `exam_start`, `exam_end`. Admin və tədris şöbəsi üçün siyahı, axtarış, yaratma, dəyişmə, deaktiv etmə ekranları. İki dilim: (1) struktur və semestr, (2) istifadəçi, fənn, qeydiyyat.

Tədris vahidi (dilim 2, `0151_directory_units.sql`): `teaching_units(id, course_id, kind: mühazirə|məşğələ|laboratoriya, teacher_id, subgroup NULL)` və `teaching_unit_groups(unit_id, group_id)`. `enrollments`-ə boş ola bilən `group_id` və `subgroup` əlavə olunur. Susmaya görə tələbənin öz qrupu götürülür; fərqli dəyər fənni başqa qrupla təkrar keçən tələbə üçündür. Ayrıca təklif (offering) cədvəli yoxdur: `academic_terms`-ə bağlı `courses` sətri özü təklifdir, ona görə sonrakı semestrdə təkrar keçilən fənn yeni sətirdir. `courses.teacher_id` fənnin rəhbər müəllimi kimi qalır; legacy handler-lər onu oxuyur.

Status əmrləri (dilim 2, `0151_directory_units.sql`): `student_status_events(id, student_id, kind, order_no, order_date, effective_date, from_group_id, to_group_id, note, entered_by, created_at, reported_at)`. `kind`: `admission | group_change | transfer_in | transfer_out | academic_leave | expulsion | reinstatement | graduation`. Cədvələ yalnız əlavə olunur; düzəliş səbəbi yazılan yeni hadisədir. `enrollments`-ə `begin_date` və `end_date` əlavə olunur (OneRoster `beginDate`/`endDate`); Task 16 idxalı və Task 37 dövrə testi onları daşıyır. Akademik status son hadisədən çıxarılır və Task 10-dakı hesab statusundan (`users.status`) ayrıdır. Legacy `r_services` və `docs.leave_body`: `academic_leave` müraciətinin `issue` addımı `order_no` və `order_date` tələb edir və hadisəni yazır; arayışda verilmə tarixi yox, həmin əmrin nömrəsi və tarixi çap olunur. Hadisəni ekrandan kimin daxil etdiyi sahibin qərarıdır (SPEC Open Questions 17); qərara qədər yalnız `academic_office`. `issue` addımının icazəsi bu tapşırıqda dəyişmir; addımların rollarını Task 46 təyin edir.

**Acceptance criteria:**
- [x] Hər varlıq üçün yaratma, dəyişmə, deaktiv etmə doğrulama və audit ilə işləyir; silmə yoxdur
- [x] `teaching_end < exam_start` şərtini pozan semestr tərcümə olunmuş səbəblə rədd olunur
- [x] Deaktiv istifadəçi girə bilmir, tarixçəsi qalır
- [x] Əmr nömrəsi, əmr tarixi və qüvvəyə minmə tarixi olmadan status dəyişmir; akademik məzuniyyət və xaric qüvvəyə minmə tarixindən sonrakı dərs siyahılarından tələbəni çıxarır, əvvəlki davamiyyət və ballar qalır; məzuniyyətdəki tələbə hesabına girir və öz sənədlərini görür
- [x] Siyahılar serverdə səhifələnir (səhifədə ≤ 50) və serverdə axtarılır

**Verification:**
- [x] `python -m pytest tests/integration/test_directory_admin.py tests/integration/test_student_status.py -q` (16 + 11 test)
- [ ] Əl yoxlaması: admin kimi fakültə → kafedra → qrup → tələbə yarat, tələbə kimi gir (API ilə testdə keçir: yaratma, müvəqqəti parol, giriş, deaktiv; brauzerdə yalnız siyahılar, qeydiyyat, status və vahid pəncərələri açılıb)

Qeyd (2026-11-18, dilim 2): `0151_directory_units.sql`; `users`, `courses`, `units` generik direktoriyaya qoşuldu; hesabları yalnız
admin idarə edir (`users.manage`), tədris şöbəsi reyestri oxuyur və fənn/qeydiyyat/vahid idarə edir. Dərs siyahısı:
`GET /api/courses/{id}/roster?day=` (`begin_date <= gün < end_date`). Status əmrləri yalnız əlavə olunur (trigger). Qrup
dəyişikliyi əmr yazılanda tətbiq olunur (gələcək tarixli köçürmə Task 37-nin planlayıcısını gözləyir). Arayış siyahıları
(müəllim seçimi, fənn seçimi) ilk 50 sətri göstərir; axtarışlı seçim T16-dan sonra. Legacy oxucular (Radar, test
bildirişləri, fənnin tələbə sayı) hələ `end_date`-ə baxmır.

Qeyd (2026-11-18): dilim 1 hazırdır — `modules/directory`, `0150_directory.sql`, `frontend/js/admin-directory.js`, `tests/integration/test_directory_admin.py`; fakültə, kafedra, ixtisas, qrup və semestr yaradılır, dəyişir, deaktiv edilir (silmə yoxdur, audit var). İstifadəçi, fənn, qeydiyyat, tədris vahidi və status əmrləri dilim 2-dədir.

**Dependencies:** Task 13 (dilim 1: rol modeli və matris)
**Files likely touched:** `backend/zeka/modules/directory/{domain,service,repo,routes}.py`, `backend/migrations/0150_directory.sql` (dilim 1: struktur və semestr), `backend/migrations/0151_directory_units.sql` (dilim 2: tədris vahidi, qeydiyyat sütunları, status əmrləri), `backend/zeka/legacy/{r_services,docs}.py`, `frontend/js/admin-directory.js`, `frontend/js/shell.js`, `frontend/css/m-admin.css`, `tests/integration/test_student_status.py`
**Estimated scope:** L (iki dilim, iki commit)

## Task 16: Kütləvi idxal

**Description:** `manage.py import --kind orgs|terms|users|courses|classes|enrollments|timetable --source <ad> --file F [--dry-run] [--prefer source]`. `--source` məcburidir: mənbə sistemin adıdır. Task 16 ümumi mexanizmi verir: növ reyestri, quru sınaq və "ya tam, ya heç" tranzaksiyası. Sonrakı tapşırıqlar reyestrə növ əlavə edir: `rooms` Task 18-də; jurnal növləri (`attendance`, `attendance-opening`, `grades`) Task 38-də `manage.py import`-a qoşulur, `attendance-opening` və `grades` yükləyiciləri Task 20 və Task 21-də `journal/service.py`-nin açıq funksiyaları kimi yazılır; `results` və `status-events` növləri də Task 38-dədir. Task 16-ya jurnal kodu və jurnal faylı düşmür; əhatəsi və ölçüsü dəyişmir.

Mənbə bağlantısı: `import_links(kind, source_system, source_id, row_id, source_hash, imported_at)`, (`kind`, `source_system`, `source_id`) üzrə unikal. Bağlantı yalnız bu cədvəldədir; idxal olunan cədvəllərə mənbə sütunu əlavə olunmur. Konflikt qaydası: mənbədən gələn sahələri `imported_at`-dan sonra Zəka-da dəyişdirilmiş və fayldakı dəyərdən fərqlənən sətir üstünə yazılmır və konflikt hesabatına düşür; faylın qalan sətirləri yazılır. `--prefer source` belə sətrin üstünə yazır və audit hadisəsi yazır. Mənbədən gələn sətir Zəka-da adi qaydada dəyişdirilir: Task 15 ekranları onun üçün bağlanmır.

OneRoster 1.2 CSV sütun adları və Azərbaycanca başlıq qarşılıqları qəbul olunur. Xəritə: OneRoster `classes` → `teaching_units`; `enrollments`-də `role=teacher` vahidin müəllimini təyin edir, `role=student` fənnə qeydiyyatı, qrupu və yarımqrupu yazır; `beginDate`/`endDate` `enrollments.begin_date`/`end_date`-ə düşür. `sourcedId` üzrə idempotent yeniləmə: `sourcedId` `import_links.source_id`-də saxlanır. Fayl ya tam idxal olunur, ya heç; konfliktli sətir xəta deyil. Admin ekranında yükləmə və quru sınaq önizləməsi. Aktivləşdirmə kodları yalnız `student` rolu üçündür; işçi hesabı Task 10-dakı admin müvəqqəti parolu ilə açılır. Kod: `secrets` ilə 60 bit (12 base32 simvol), yalnız verildiyi tələbə nömrəsi ilə birlikdə qəbul olunur, bazada yalnız SHA-256-sı saxlanır, birdəfəlikdir, müddəti tenant ayarıdır (susmaya görə 14 gün). Dekanlıq CSV-si fakültə üzrə yaradılanda bir dəfə verilir; yenidən yaratma köhnə kodları ləğv edir. Yanlış kod cəhdləri Task 10-dakı (hesab, ünvan) məhdudiyyətindən keçir; yanlış cəhd kodu ləğv etmir.

**Forma №3 (2026-11-18, sahibin qərarı):** `--kind teaching-load` kafedranın akademik yük faylını (`.xlsx`) oxuyur və tədris vahidlərini yaradır. Format və oxuma qaydaları `docs/forms/forma-3.md`-dədir: iki tərtibat (bir vərəqdə müəllim blokları; hər müəllimə bir vərəq), başlıq mətnlə tapılır, boş fənn adlı sətir əvvəlki fənnin davamıdır, birləşmiş mühazirə axını bütün qrupları əhatə edən bir vahiddir, `Digər dərs yüklərini aparan müəllimlər` ikinci müəllimdir. Oxuyucu standart kitabxana ilə yazılır (`zipfile`, `xml.etree`), Office faylları üçün mövcud ölçü və DTD qoruyucuları ilə; yeni asılılıq yoxdur. Müəllim adı reyestrdəki istifadəçiyə uyğunlaşdırılır; tapılmayan ad konflikt hesabatına düşür, hesab yaradılmır.

**Acceptance criteria:**
- [x] Hər iki tərtibatda uydurma Forma №3 nümunəsi (`tests/fixtures/forma3_blocks.xlsx`, `tests/fixtures/forma3_sheets.xlsx`) gözlənilən tədris vahidlərini verir: axın, yarımqrup, ikinci müəllim, `Cəmi` və `SAAT HESABI` sətirlərinin keçilməsi daxil; real fayllar repoya düşmür
- [x] 10 000 sətirlik istifadəçi faylı 60 saniyədən tez idxal olunur; təkrar işlətmə 0 dəyişiklik bildirir
- [x] 3 səhv sətri olan fayl heç nə yazmır və 3 sətri nömrə və səbəblə göstərir
- [x] Zəka-da dəyişdirilmiş sətir təkrar idxalda üstünə yazılmır, konflikt hesabatında sətir nömrəsi ilə görünür; `--prefer source` üstünə yazır və audit hadisəsi yazır
- [x] Doğrulama yazma tranzaksiyasından əvvəl bitir; yazma tək `BEGIN IMMEDIATE` tranzaksiyasıdır və kilid müddəti idxal hesabatında çıxır: 10 000 sətirdə ≤ 1 s. Admin ekranı ≤ 20 000 sətir qəbul edir; böyük fayl yalnız `manage.py` ilə
- [x] Aktivləşdirmə kodu bir dəfə işləyir və müddəti bitəndə rədd olunur; düzgün kod başqa tələbə nömrəsi ilə rədd olunur; bazada açıq kod yoxdur (yalnız hash); bir ünvandan 10 yanlış koddan sonra 429, başqa ünvandan düzgün kod işləyir

**Verification:**
- [x] `python -m pytest tests/integration/test_import.py -q` (13 test)
- [x] `python backend/manage.py import --kind users --source test --file tests/fixtures/users_10k.csv --dry-run` (təmiz demo bazasında: 10 000 yeni, 0,12 s; real idxal 0,33 s, kilid 208 ms; təkrar 0 dəyişiklik; 10 120 aktivləşdirmə kodu)

Qeyd (2026-11-18): `modules/integration/` (`tables.py` CSV/XLSX oxuyucusu, `forma3.py`, `domain.py`, `importer.py`, `repo.py`,
`routes.py`), `0160_import.sql`, `frontend/js/admin-import.js`, giriş səhifəsində "Tələbə hesabını aktivləşdir". Konflikt
idxal anındakı sahələrin hash-i (`import_links.source_hash`) ilə tapılır; heç vaxt idxal olunmamış sətrin yalnız boş
sahələri doldurulursa konflikt sayılmır. Forma №3-də fənn adla (bir neçə semestrdə eyni ad varsa semestrin adı ilə),
müəllim "Soyad Ad Ata adı" sözləri ilə, qrup adla tapılır; tapılmayan konflikt hesabatına düşür. Real AzTU fayllarının
hər iki tərtibatı bu oxuyucu ilə yoxlanmayıb (fayllar repoda yoxdur): sahib ilk real idxalı quru sınaqla etməlidir.

**Dependencies:** Task 15 (dilim 1: struktur və semestr); `classes` və `enrollments` növləri dilim 2-nin miqrasiyasından (`teaching_units`, `enrollments.begin_date`) sonra
**Files likely touched:** `backend/zeka/modules/integration/importer.py`, `backend/migrations/0160_import.sql` (`import_links` cədvəli, (`kind`, `source_system`, `source_id`) üzrə unikal; aktivləşdirmə kodları), `backend/manage.py`, `frontend/js/admin-import.js`, `tests/fixtures/*.csv`
**Estimated scope:** M

## Task 17: Tenant ayarları

**Description:** Universitet profili, loqo, qiymət sxemi (komponentlər, çəkilər, imtahan minimumu, keçid balı, hərf şkalası), davamiyyət həddi, `attendance.excused_counts_toward_limit` (üzrlü qayıb həddə sayılırmı; susmaya görə sayılır, SPEC Assumptions 11), `attendance.points_rule` (buraxılmış saat faizi → davamiyyət balı cədvəli), `journal.cutover_date` (kəsid tarixi: cari semestrdə jurnalın Zəka-da başladığı gün; boşdursa və ya cari tədris dövründən kənardırsa kəsid yoxdur; SPEC Open Questions 9), dərs saatları, reyestr prefiksi, bayram günləri ayarlara keçir. Semestr tarixləri ayar deyil: `academic_terms`-dədir (Task 15). `semester_start` ayarından istifadə edən kod (`r_learning.py:188`, `radar.py:82`, `store.py:397-398`) cari `academic_terms` sətrinə keçir. `SEM_WEEKS` (`r_learning.py:40`) ayara çevrilmir, silinir. Admin ekranı. Kodda sabit yazılmış AzTU dəyərləri çıxarılır: `r_academy.py` (`PREREQ` fənnin sahəsinə keçir, Task 23-də sillabusun prerekvizit sahəsi olur), `docs.py`, `r_learning.py`, `store.py`, `student.js`.

**Acceptance criteria:**
- [x] Sxemi 30/10/10/50 və imtahan minimumu 17-yə dəyişmək kodu dəyişmədən hesablanan nəticəni dəyişir
- [x] Sadalanan fayllarda köhnə sabitlər qalmır
- [x] İkinci, uydurma universitet konfiqurasiyası ilə inteqrasiya testləri keçir

**Verification:**
- [x] `python -m pytest tests/integration/test_tenant_settings.py -q` (10 test)

Qeyd (2026-11-18): `core/tenant.py` (susmaya görə neytral; AzTU dəyərləri `content/seed.json` → `tenant`), `modules/tenant`
(admin marşrutları), `frontend/js/admin-settings.js`, `0170_course_prereq.sql`. `semester_start` ayarı yoxdur: demo cari
semestri `academic_terms` sətri kimi yaradır, kod `directory.service.current_term()` oxuyur; `SEM_WEEKS` silindi (həftələr
semestrin tədris dövründən). Radarın qayıb siqnalı da universitetin həddinə bağlandı. Sillabusun qiymətləndirmə cədvəli və
davamiyyət qaydası sxemdən gəlir. Edilməyib: loqonun yüklənməsi (hələ `/static/img/brand`), `journal.cutover_date`,
`lesson_times` və `holidays` yalnız saxlanır və yoxlanır, onları Task 19–20 oxuyacaq.

**Dependencies:** Task 15 (dilim 1: struktur və semestr)
**Files likely touched:** `backend/zeka/core/tenant.py`, `backend/zeka/legacy/{r_academy,docs,r_learning,store,radar}.py`, `backend/migrations/0170_course_prereq.sql` (`courses.prereq`), `frontend/js/admin-settings.js`, `frontend/js/student.js`
**Estimated scope:** L (iki dilim: ayarlar və admin ekranı; koddakı sabitlərin çıxarılması)

## Checkpoint B: Task 10–17 sonra

- [x] Prod rejimində parolsuz yol yoxdur; rol × marşrut matrisi yaşıl (`test_modes.py`, `test_authz_matrix.py`, 158 marşrut)
- [x] 10 000 tələbə idxal olunur və aktivləşdirmə kodu ilə öz hesabına girir (`test_import.py`: 10k 0,33 s, kilid ~200 ms)
- [x] Yeddi rəyçinin baxışı, hər tapıntının ayrıca təkzibi, yalnız təsdiqlənənlərin düzəlişi: `docs/review/checkpoint-b-2026-11-18.md`, reqressiya testləri `tests/integration/test_checkpoint_b.py`
- [ ] Sınaq nüsxəsi sabit adla açılır: `curl https://<ad>/healthz` (`-k` olmadan) sahibin SEB kompüterindən 200 qaytarır; sintetik məlumatla işləyir; hər yoxlama nöqtəsində push-dan sonra `docs/runbooks/deploy.md` ilə yenilənir. Ad saat 22-yə hazır deyilsə: Task 18, 19, 28-in əl yoxlamaları LAN-da http ilə (`seb://`) aparılır, `sebs://` sınağı və Google Calendar abunəliyi Task 44-ün meyarına yazılır
- [ ] Sahib rol cədvəlini və `qa.moderate`, `community.moderate` bölgüsünü təsdiqləyib (Task 13; SPEC Open Questions 24)
- [ ] Rəy axını keçib; sahiblə baxış

---

## Faza 3 — Akademik nüvə

## Task 18: Korpus, otaq və otaq QR-i

**Description:** Cədvəllər: `buildings`, `floors`, `rooms` (kod, növ, tutum, əlçatanlıq). CSV idxalı: Task 16-dakı idxal servisinə `--kind rooms` əlavə olunur. Otaq səhifəsi `/r/{kod}`: otağın adı, indiki və növbəti dərs. Hər korpus üçün çap olunan QR vərəqi (mövcud `qr.py`). `timetable.room` mətn sahəsi otağa bağlanır; uyğunlaşmayan sətirlər hesabatda.

**Acceptance criteria:**
- [x] Hər otağın sabit QR ünvanı var; səhifə indiki və növbəti dərsi cədvəldən göstərir
- [x] Girişsiz baxışda tələbə adı və ya şəxsi məlumat görünmür (müəllimin adı da göstərilmir)
- [x] Mövcud cədvəl sətirləri otağa bağlanır və ya hesabatda sadalanır

Qeyd: mərtəbə ayrıca `floors` cədvəli deyil, otağın `floor` sütunudur (heç bir meyar mərtəbə cədvəli tələb etmir).
Korpus və otaq ekranı ayrıca `facilities.js` deyil, "Struktur və reyestr" səhifəsinin iki bölməsidir.

**Verification:**
- [x] `python -m pytest tests/integration/test_facilities.py -q`
- [ ] Əl yoxlaması: çap olunan QR telefonla oxunur və otaq səhifəsini açır (sahib; brauzerdə vərəq və səhifə yoxlanıb)

**Dependencies:** Task 16; `timetable.room` bağlama dilimi Task 19 birləşdiriləndən sonra
**Files likely touched:** `backend/zeka/modules/facilities/{domain,service,repo,routes}.py`, `backend/migrations/0180_facilities.sql`, `frontend/js/facilities.js`
**Estimated scope:** M

## Task 19: Cədvəl idarəsi və iCal

**Description:** Tədris şöbəsi cədvəl sətirlərini yaradır və dəyişir: tədris vahidi, gün, saat, otaq, həftə nümunəsi, akademik saat sayı (növ və müəllim vahiddən gəlir). Saxlananda toqquşma yoxlanır: otaq, vahidin müəllimi və vahidin hər (qrup, yarımqrup) cütü üzrə. Bütöv qrup öz yarımqrupları ilə toqquşur; 1-ci yarımqrup 2-ci yarımqrupla toqquşmur. Otaq `timetable.room` kodu kimi saxlanır, toqquşma normallaşdırılmış kodla yoxlanır; `rooms` cədvəlinə bağlama Task 18-dədir. Dərslər yalnız `teaching_start` ilə `teaching_end` arasında yaradılır, bayram günləri buraxılır; dərs yaradılanda akademik saat cədvəl sətrindən, `lessons.teacher_id` vahiddən köçürülür. Yaradılma (tədris vahidi, tarix, başlama saatı) açarı üzrə idempotentdir. Davam edən semestrdə kəsid tarixi (`journal.cutover_date`, Task 17; idxaldan sonra `as_of`, Task 20) və ondan əvvəlki dərslər plan saatı üçün yaradılır, amma qeyd üçün açılmır; onların davamiyyəti Task 38 idxalından gəlir. Dərsin ləğvi və ya köçürülməsi qeydiyyatdakılara bildiriş göndərir. İstifadəçi üzrə ləğv edilə bilən tokenli iCal lenti.

**Acceptance criteria:**
- [x] Toqquşan sətir rədd olunur və toqquşmanın nə ilə olduğu yazılır
- [x] 3 qrupluq mühazirə axını, ikinci müəllimin üç məşğələsi və iki yarımqrupda laboratoriya olan fənn toqquşmasız saxlanır; eyni qrupun eyni saatdakı ikinci dərsi rədd olunur
- [x] Yaradılan dərslər həftə nümunəsinə uyğundur və bayramları buraxır
- [x] Dərs yaradılmasının təkrarı dublikat yaratmır: (tədris vahidi, tarix, başlama saatı) üzrə bir dərs var (köçürülmüş dərs öz plan slotunu saxlayır)
- [x] `teaching_end`-dən sonrakı tarixə dərs yaradılmır
- [x] iCal lenti RFC 5545 sahələrini və `TZID=Asia/Baku` daşıyır; dəyişiklikdən sonra yenilənir

Qeyd: kəsid tarixindən əvvəlki dərslərin "qeyd üçün açılmaması" Task 20-də yoxlanır (dərs yaradılır, qeyd qaydası jurnaldadır).
Demo: hər fənnin hər dərs növü bütün demo qrupları üçün bir tədris vahididir; semestrin bütün dərsləri yaradılır.

**Verification:**
- [x] `python -m pytest tests/unit/test_timetable_conflicts.py tests/integration/test_timetable.py -q`
- [ ] Əl yoxlaması: lent Google Calendar və Outlook-a əlavə olunur (sahib; xarici xidmət, buradan yoxlanmadı)

**Dependencies:** Task 15 (dilim 2: tədris vahidi), Task 17
**Files likely touched:** `backend/zeka/modules/timetable/{domain,service,repo,routes}.py`, `backend/migrations/0190_timetable.sql` (`timetable.unit_id`, `timetable.academic_hours`, həftə nümunəsi, `lessons.unit_id`, `lessons.teacher_id`, `lessons.academic_hours`, iCal tokeni), `frontend/js/timetable-admin.js`
**Estimated scope:** L (iki dilim: vahidli cədvəl və toqquşma; dərs yaradılması və iCal)

## Task 20: Davamiyyət jurnalı

**Description:** Müəllim bugünkü dərsi açır, siyahı susmaya görə "iştirak edir", istisnaları işarələyir. Siyahı: fənnə qeydiyyatı dərsin tarixində qüvvədə olan (`begin_date`–`end_date`) və qrupu (vahidin yarımqrupu varsa, yarımqrupu da) dərsin tədris vahidinə daxil olan tələbələr. Saxlama idempotentdir. Düzəliş pəncərəsi (ayar, 48 saat) bitəndən sonra dəyişiklik kafedra müdirindən və səbəbdən keçir. Üzrlü qayıb axını qalır. Əvəzetmə: `dept_head` dərsin müəllimini (`lessons.teacher_id`) məcburi səbəblə dəyişir, dəyişiklik auditdədir; başqa əvəzetmə mexanizmi yoxdur.

Faiz və status (tələbə × fənn). Faiz = buraxılmış akademik saat / plan akademik saatı. Plan saatı: tələbənin siyahısında olduğu vahidlərin tədris dövründəki (`teaching_start`–`teaching_end`) ləğv olunmamış dərslərinin akademik saatı. Kəsid tarixi tələbə × fənn üçün idxal sətrinin `as_of` dəyəridir; idxal yoxdursa `journal.cutover_date` ayarıdır (Task 17; boşdursa kəsid yoxdur və bütün dərslər Zəka-da qeyd olunur). Buraxılmış saat: kəsid tarixinə qədərki idxal olunmuş qayıb saatı (açılış qalığı və ya dərs səviyyəli `source='legacy'` sətirlər; bir tələbə × fənn üçün yalnız biri, Task 38) + kəsid tarixindən sonrakı Zəka dərslərindəki qayıb saatı. Üzrsüz qayıb həmişə sayılır. Üzrlü qayıb (qalıqdakı üzrlü saat daxil) `attendance.excused_counts_toward_limit` ayarı açıq olanda sayılır. Effektiv hədd = min(tenant həddi, dərc olunmuş sillabusun həddi). Sillabusun həddi `courses.attendance_limit`-də saxlanır (Task 25 dərcdə yazır); boşdursa tenant həddi tətbiq olunur. Status: normal, xəbərdarlıq, imtahana buraxılmır, məlumat natamam. "Məlumat natamam": kəsid tarixində və ya ondan əvvəl dərsi olan, amma həmin dövr üçün idxal olunmuş qayıb məlumatı (açılış qalığı və ya dərs səviyyəli sətir) olmayan tələbə × fənn. Bu hesab `r_learning.py:63-71`-dəki "həftəlik sətir sayı × `SEM_WEEKS` × 0,25" düsturunu və `student.js:333`-dəki dərs sayı ilə limiti əvəz edir.

Açılış qalığı (semestr ortasında kəsid üçün): `attendance_opening(student_id, course_id, held_hours, unexcused_hours, excused_hours, as_of)`: tələbə × fənn × semestr üzrə kəsid tarixinə qədər keçilmiş, üzrsüz buraxılmış və üzrlü buraxılmış saat. Mənbə bağlantısı `import_links`-dədir (Task 16); mənbə açarı (semestr `sourcedId`, fənn `sourcedId`, tələbə `sourcedId`) üçlüyüdür. `held_hours` faizə girmir: idxal hesabatı onu Zəka-nın `as_of`-a qədərki plan saatı ilə tutuşdurur və fərqli sətirləri göstərir. `attendance-opening` növünün yükləyicisi `journal/service.py`-nin açıq funksiyasıdır (Task 16 reyestri; `manage.py import`-a Task 38-də qoşulur). Köhnə sistem dərs səviyyəli qeyd verirsə, Task 38-in `attendance` növü `as_of`-a qədərki dərslərə `source='legacy'` və `as_of` daşıyan davamiyyət sətri yazır; belə sətir 48 saatlıq pəncərəyə düşmür və onu yalnız kafedra müdiri səbəblə dəyişir. Kəsid tarixi və ondan əvvəlki tarixli dərslər qeyd üçün açılmır və Task 39-dakı doldurulma faizinə düşmür. Qalığı olan fəndə status `as_of` tarixi ilə birlikdə göstərilir. Qalıq sətri dərs qeydi deyil: 48 saatlıq pəncərə ona aid deyil. Sətir yalnız iki yolla dəyişir: mənbə açarı (`import_links`) üzrə təkrar idxalla (idxal edən hesab və faylın SHA-256-sı auditdədir; Zəka-da düzəldilmiş sətir Task 16-dakı konflikt qaydasına düşür) və ya kafedra müdirinin səbəbli düzəlişi ilə. `as_of` və ondan əvvəlki tarixə təsdiqlənən üzrlü qayıb müraciəti qalıq sətrində saatı üzrsüzdən üzrlüyə keçirir; səbəb müraciətin id-sidir.

**Acceptance criteria:**
- [x] 30 nəfərlik dərs bir sorğu ilə qeyd olunur; eyni sorğunun təkrarı nəticəni dəyişmir
- [x] 1-ci yarımqrupun tələbəsinin 2-ci yarımqrupun laboratoriya dərslərində davamiyyət sətri yoxdur və həmin dərslər onun plan saatına düşmür
- [x] Kafedra müdiri dərsin müəllimini səbəbsiz dəyişə bilmir; dəyişiklik auditdədir və yeni müəllim həmin dərsin davamiyyətini yazır
- [x] Pəncərədən sonra müəllimin düzəlişi rədd olunur; kafedra müdirinin düzəlişi səbəblə yazılır
- [x] Vahid test (hədd 25%): 45 plan akademik saatında 11 buraxılmış saat "imtahana buraxılmır" vermir, 12 saat verir; ləğv olunmuş dərs və `teaching_end`-dən sonrakı gün məxrəcə düşmür
- [x] Buraxılmış saat faizi yalnız qeydiyyatın `begin_date`–`end_date` aralığındakı dərslərdən hesablanır
- [x] Üzrlü qayıb `attendance.excused_counts_toward_limit` ayarına görə sayılır; vahid testlər ayarın hər iki dəyəri üçündür
- [x] Effektiv hədd = min(tenant həddi, dərc olunmuş sillabusun həddi); status tələbəyə, müəllimə və dekanlığa görünür
- [x] Açılış qalığında plan saatının 20%-i qədər, Zəka-da 6%-i qədər üzrsüz qayıbı olan tələbə "imtahana buraxılmır" statusu alır
- [x] Eyni qalıq faylının təkrar idxalı 0 dəyişiklik bildirir; daha gec `as_of` ilə təkrar idxal həmin tarixdən əvvəlki Zəka qeydlərini ikinci dəfə saymır
- [x] Faizə kəsid tarixinə qədərki idxal olunmuş qayıblar daxildir: eyni qayıblar dərs səviyyəli sətir kimi və açılış qalığı kimi idxal olunanda faiz və status eynidir
- [x] Müəllim açılış qalığını və idxal olunmuş (`source='legacy'`) davamiyyət sətrini dəyişə bilmir (403); kafedra müdirinin düzəlişi səbəblə yazılır
- [x] `journal.cutover_date` təyin olunub: həmin tarixdə və ya ondan əvvəl dərsi olan, amma nə açılış qalığı, nə də idxal olunmuş dərs səviyyəli sətri olan tələbə × fənn "normal" yox, "məlumat natamam" göstərir; ona "imtahana buraxılmır" statusu avtomatik verilmir
- [x] `held_hours` Zəka-nın `as_of`-a qədərki plan saatından fərqlənən sətir idxal hesabatında sətir nömrəsi ilə görünür

Qeyd: açılış qalığının yükləyicisi `journal/service.py`-də deyil, Task 16-nın idxal reyestrindədir (`attendance-opening` növü, `manage.py import` və ekran onu artıq tanıyır); qalıq Zəka-nın planı ilə `journal.service.planned_until` vasitəsilə tutuşdurulur. `as_of` tarixinə qədərki dərsə təsdiqlənən üzrlü qayıb müraciətinin qalıqda saatı üzrlüyə keçirməsi edilmədi: belə dərsin Zəka-da qayıb sətri yoxdur, müraciət formu onu seçə bilmir (Task 38-də, köhnə sətirlərlə birlikdə). Fikstur faylı əvəzinə test öz CSV-sini qurur (tarixlər bu günə görədir).

**Verification:**
- [x] `python -m pytest tests/unit/test_attendance_rules.py tests/integration/test_attendance_journal.py tests/integration/test_attendance_opening.py -q`

**Dependencies:** Task 19, Task 17
**Files likely touched:** `backend/zeka/modules/journal/{domain,service,repo,routes}.py`, `backend/migrations/0200_attendance_opening.sql` (`attendance_opening` cədvəli; `attendance.source` və `attendance.as_of` sütunları; `courses.attendance_limit`: boşdursa tenant həddi, Task 25 dərcdə yazır), `frontend/js/journal.js`, `frontend/css/m-journal.css`, `tests/fixtures/attendance_opening.csv`
**Estimated scope:** L (iki dilim: dərs qeydi, faiz və status; açılış qalığı və idxal olunmuş sətirlər)

## Task 21: Qiymət jurnalı

**Description:** Komponentlər dərc olunmuş sillabusdan və ya tenant sxemindən gəlir. Cədvəl şəklində daxiletmə, Excel-dən yapışdırma. Davamiyyət komponenti jurnaldan `attendance.points_rule` ilə hesablanır (`r_learning.py:215`-dəki sabit düsturun yerinə) və cədvələ əl ilə yazılmır; düzəliş yalnız mövcud səbəbli, auditli dəyişiklik yolu ilədir. Qaralama → dərc. Dərcdən sonrakı dəyişiklik səbəb tələb edir və jurnala düşür. Yekun bal, imtahan minimumu, hərf qiyməti. İmtahan komponentinin balı `exam_id` və `attempt_no` daşıyır (`0210_journal.sql`; Task 30 bu sütunlarla yazır).

`grades` idxal növü (tələbə, fənn, komponent, bal, maksimum) cədvəl daxiletməsi ilə eyni servis yolundan yazır: sətir `source='legacy'` və kəsid tarixini (`as_of`) daşıyır, müəllif idxal edən hesabdır, səbəb `import:<faylın adı>:<sha256-sı>`. Mənbə açarı: (fənn `sourcedId`, tələbə `sourcedId`, komponent açarı). Fənnin sxemində olmayan komponent səhv sətirdir. Yükləyici `journal/service.py`-nin açıq funksiyasıdır (Task 16 reyestri; `manage.py import`-a Task 38-də qoşulur). Davamiyyət komponenti idxal olunmur: kəsid tarixinə qədərki idxal olunmuş qayıblardan (açılış qalığı və ya `source='legacy'` sətirlər, Task 20) və jurnaldan hesablanır. Ballar KOICA-da yoxdursa (SPEC, Əvəzləmə matrisi: "E-jurnal (TKTA: sistemdə yoxdur)"), eyni CSV şablonunu dekanlıq doldurur; müəllimin öz yolu Excel-dən yapışdırmadır.

Tələbənin qiymət səhifəsi real məlumatdan oxuyur. Transkript yalnız dərc olunmuş yekun qiymətlərdən qurulur: orta bal = Σ(yekun bal × kredit) / Σ kredit; "Cəmi kredit" yalnız keçid balını və imtahan minimumunu keçən fənləri sayır; bir tələbə × fənn × semestr üçün bir sətir. `transcript` müraciət növü tələbənin tarixçəsi uzlaşdırılana qədər (`history_reconciled_at`; qəbul semestri Zəka-dakı ilk semestrdən əvvəl olmayan tələbələr üçün avtomatik) bağlıdır və səbəbi göstərir. Şablondan "Ballar sintetikdir (demo)" sətri çıxarılır.

**Acceptance criteria:**
- [x] Həddən kənar və rəqəm olmayan dəyər xana səviyyəsində tərcümə olunmuş mesajla rədd olunur
- [x] Müəllim komponent balını yalnız öz tədris vahidlərinin siyahısındakı tələbələrə yazır; başqa vahidin tələbəsinə yazı 403 alır
- [x] Davamiyyət komponentinə cədvəldən yazılan dəyər rədd olunur; `attendance.points_rule` dəyişəndə həmin bal kod dəyişmədən dəyişir
- [x] Davamiyyət komponentinin balına kəsid tarixinə qədərki idxal olunmuş qayıblar daxildir: yalnız açılış qalığında qayıbı olan tələbənin balı `attendance.points_rule`-a görə azalır
- [x] Dərcdən sonrakı hər dəyişikliyin müəllifi, köhnə və yeni dəyəri, səbəbi qiymət jurnalındadır
- [x] İdxal olunan bal qiymət jurnalında `source='legacy'`, idxal edən hesab və fayl adı ilə görünür; eyni faylın təkrar idxalı 0 dəyişiklik bildirir; sxemdə olmayan komponentli sətir sətir nömrəsi ilə rədd olunur
- [x] Yekun və hərf tenant sxeminə, imtahan minimumu daxil, uyğundur; tələbə yalnız dərc olunmuş balı görür
- [x] Dekanlıq nəticəsi "keçdi" olmayan tələbə × fənn siyahısını (akademik borclar) görür və CSV ixrac edir
- [x] Tarixçəsi uzlaşdırılmamış tələbənin transkript müraciəti tərcümə olunmuş səbəblə rədd olunur; uzlaşdırılmış tələbədə kəsilən fənn "Cəmi kredit"ə düşmür və orta bal əl hesabı ilə üst-üstə düşür
- [x] Sintetik `transcript_rows` silinib və heç bir marşrut onu çağırmır; onun vahid testi dərc olunmuş qiymətlərdən qurulan transkriptin testi ilə əvəz olunub

Qeyd: `grades` yükləyicisi Task 16 reyestrindədir (`grades` idxal növü); yekun qiymətlər `final_grades`-də fənnin adı, krediti və semestri ilə saxlanır, Zəka-dan əvvəlki semestrlər `course_id`-siz sətirlərdir (demo onları köhnə sistemin idxalı kimi yazır). Davamiyyət balı bu günə qədər keçilmiş saatın buraxılan payından hesablanır. Tarixçənin uzlaşdırılması kataloqdakı "Status" pəncərəsindədir.

**Verification:**
- [x] `python -m pytest tests/unit/test_grading_rules.py tests/integration/test_grade_journal.py -q`
- [x] `python -m pytest tests/integration/test_transcript_gate.py -q`
- [x] `grep -rn "transcript_rows" backend/` boş çıxış verir

**Dependencies:** Task 20
**Files likely touched:** `backend/zeka/modules/journal/{domain,service,repo,routes}.py`, `backend/migrations/0210_journal.sql` (imtahan balında `exam_id` və `attempt_no`; balda `source` və `as_of`; tələbədə `history_reconciled_at`), `frontend/js/journal.js`, `backend/zeka/legacy/r_learning.py`, `backend/zeka/legacy/docs.py`, `backend/zeka/legacy/r_services.py`, `backend/zeka/legacy/store.py`, `tests/unit/test_store.py`
**Estimated scope:** L (iki dilim: qiymət jurnalı və `grades` yükləyicisi; transkript)

## Task 22: Tapşırıqlar və material faylı

**Description:** Müəllim tapşırıq yaradır: mətn, son tarix, maksimum bal, komponent, gecikmə qaydası. Tələbə fayl və ya mətn göndərir (mövcud fayl API-si). Müəllim rəy və bal yazır; bal jurnal komponentinə düşür. İki dilim: (1) tapşırıq axını; (2) mühazirə materialının orijinal faylı.

Mühazirə materialının orijinal faylı (dilim 2). Bu gün yüklənən fayldan yalnız çıxarılan mətn saxlanır, orijinal atılır və tələbə onu endirə bilmir (`docs/CODEMAP.md` L53). Yükləmədə orijinal fayl mövcud məzmun ünvanlı fayl anbarına yazılır (`store.save_file`: `data/uploads/<sha256>.bin`, `files` cədvəli) və `materials.file_id` ilə bağlanır; `save_file` `.docx`, `.pptx`, `.md` və `.txt` növlərini qəbul edir. Çıxarılan mətn və hissələr əvvəlki kimi saxlanır. Orijinalı fənnə yazılmış tələbə və fənnin müəllimi endirir: `GET /api/materials/{id}/file`; `file_access` bu oxucunu tanıyır. Materialın əvəzlənməsi yeni versiya yaradır (`materials.replaces_id`): əvvəlki versiyanın faylı və mətni silinmir və müəllimə görünür; tələbə və axtarış indeksi yalnız cari versiyanı görür.

**Acceptance criteria:**
- [x] Son tarixdən sonrakı göndəriş qaydaya görə "gecikib" işarələnir və ya rədd olunur
- [x] Yalnız fənnə yazılan tələbə göndərə bilir; göndərişi yalnız sahibi və fənnin müəllimi oxuyur
- [x] Qiymətləndirilən bal jurnalda uyğun komponentdə görünür
- [x] Müəllimin yüklədiyi `.docx` faylını fənnə yazılmış tələbə endirir və SHA-256-sı yüklənən faylla eynidir; fənnə yazılmayan tələbə 404 alır
- [x] Material əvəzlənəndən sonra tələbə yeni faylı alır; əvvəlki versiyanın faylı müəllim üçün endirilir; tutor axtarışı yalnız cari versiyanın hissələrini qaytarır

Qeyd: modul `backend/zeka/modules/learning/{domain,repo,service,routes}.py`-dir (bir `assignments.py` deyil); bir komponentə bir neçə tapşırıq düşə bilər, onların cəmi komponentin maksimumunu keçmir.

**Verification:**
- [x] `python -m pytest tests/integration/test_assignments.py tests/integration/test_material_files.py -q`

**Dependencies:** dilim 1: Task 21; dilim 2: yalnız Task 13
**Files likely touched:** `backend/zeka/modules/learning/assignments.py`, `backend/zeka/modules/learning/routes.py`, `backend/migrations/0220_assignments.sql`, `backend/migrations/0221_material_files.sql` (`materials.file_id`, `materials.replaces_id`), `backend/zeka/legacy/{r_learning,r_core,store}.py`, `frontend/js/assignments.js`, `frontend/js/student.js`, `frontend/js/teacher.js`, `tests/integration/test_material_files.py`
**Estimated scope:** L (iki dilim, iki commit: tapşırıq axını; material faylı)

## Task 45: Sənədin bütövlüyü

**Description:** Bu gün verilmiş sənəd hər baxışda canlı sətirlərdən yenidən qurulur, `/verify` hash-i yenidən hesablamadan "SHA-256 ✓" çap edir, reyestr nömrəsi `COUNT(*)+1`-dir (`docs/CODEMAP.md` L30, L31, L33). Üç dəyişiklik.

Saxlanmış yük. Verilmə anında sənədin göstərilməsi üçün lazım olan bütün sahələr (sahibin adı, qrupu, kursu, universitet, fakültə, ixtisas, mətn və ya transkript sətirləri, verən şəxs, tarix) bir dəfə yığılır və kanonik JSON kimi `documents.payload`-da saxlanır; `documents.hash` bu yükün SHA-256-sıdır. Yük sahələrdir, HTML deyil: üç dildə görünüş eyni yükdən qurulur. `/doc/{id}` və `/verify/{code}` yalnız bu yükdən oxuyur; `users`, `study_groups`, ayarlar və qiymət cədvəllərinə baxmır. Yük veriləndən sonra dəyişmir; düzəliş ləğv və yeni sənəddir. Yükü olmayan (bu miqrasiyadan əvvəlki) sənəd canlı sətirlərdən qurulmur və "doğrulanmır" göstərir. Demo seed sənədləri eyni verilmə funksiyası ilə yaradır.

Doğrulama. `/verify/{code}` hash-i saxlanmış yükdən yenidən hesablayır və `documents.hash` ilə sabit vaxtlı müqayisə edir. Uyğun gəlməsə "sənəd dəyişdirilib" göstərir; "SHA-256 ✓" yalnız müqayisə keçəndə çap olunur. Hədd: hash açarsızdır və yüklə eyni bazadadır, bazaya yaza bilən şəxs ikisini birlikdə dəyişə bilər. Bu, Task 41 təhdid modelində yazılır; imza Out of Scope-dadır (SİMA, ASAN İmza).

Reyestr nömrəsi. `doc_sequences(prefix, year, last_no)` cədvəli; nömrə verilmə tranzaksiyasında (`BEGIN IMMEDIATE`) artırılır. `store.py`-dəki `COUNT(*)+1` hesabı silinir. Sənədin silinməsi və ya ləğvi nömrəni geri qaytarmır. Miqrasiya hər prefiks və il üçün `last_no`-nu mövcud ən böyük nömrədən doldurur.

Task 30-un protokolu və imtahan-qiymət cədvəli bu verilmə yolundan keçir.

**Acceptance criteria:**
- [x] Sənəd veriləndən sonra sahibin adı və qrupu dəyişdirilir: `/doc/{id}` verilmə anındakı mətni göstərir, `/verify` "etibarlıdır" qaytarır. Transkriptdə dərc olunmuş balın dəyişdirilməsi eyni nəticəni verir (`test_a_transcript_is_shown_as_issued_after_a_published_grade_changes`)
- [x] Saxtalaşdırma testi: bazada `documents.payload` birbaşa dəyişdirilir; `/verify` "sənəd dəyişdirilib" qaytarır və "SHA-256 ✓" çap etmir. Yalnız `documents.hash` dəyişdiriləndə nəticə eynidir
- [x] Paralel verilmə testi: iki prosesdən eyni prefikslə 50 paralel verilmə 50 fərqli, boşluqsuz ardıcıl nömrə verir; 5xx 0
- [x] Sənəd bazadan silinəndən sonra növbəti verilmə uğurludur və nömrə təkrarlanmır
- [x] Yükü olmayan sənəd `/verify`-da "doğrulanmır" göstərir; `/doc/{id}` onu canlı sətirlərdən qurmur

**Verification:**
- [x] `python -m pytest tests/integration/test_document_integrity.py -q`
- [x] `grep -n "COUNT(\*)" backend/zeka/legacy/store.py` reyestr nömrəsi hesabını göstərmir

**Dependencies:** Task 7, Task 17; transkriptin bal halı Task 21 birləşdiriləndən sonra
**Files likely touched:** `backend/zeka/legacy/{store,docs,r_services}.py`, `backend/migrations/0450_document_integrity.sql` (`documents.payload`, `doc_sequences` cədvəli), `tests/integration/test_document_integrity.py`
**Estimated scope:** M

## Checkpoint C: Task 18–22 və Task 45 sonra

- [x] Müəllim dərsdə davamiyyət və bal yazır; tələbə dərhal görür (`test_attendance_journal`, `test_grade_journal`, `test_checkpoint_c::test_t6_…`)
- [x] 25% həddi və imtahana buraxılış avtomatik hesablanır (`test_attendance_rules`, `test_grading_rules`)
- [x] Verilmiş sənəd saxlanmış yükdən göstərilir; bazada dəyişdirilən yük `/verify`-da "sənəd dəyişdirilib" verir (`test_document_integrity`)
- [x] Rəy axını keçib: `docs/review/checkpoint-c-2026-11-19.md`
- [ ] Sahiblə baxış (J2-nin siyasəti və J11 sahibin qərarıdır)

---

## Faza 4 — Sillabus və imtahan

## Task 23: Struktur sillabus

**Description:** `syllabus_versions` cədvəli: versiya, status, doğrulanmış JSON. Sahələr: nəticələr (id, mətn, Bloom səviyyəsi), həftəlik plan (mövzu, nəticələr, fəaliyyət), qiymətləndirmə (komponent, çəki), qaydalar (davamiyyət, gecikmə, AI siyasəti), prerekvizitlər (ilkin dəyər fənnin prerekvizit sahəsindən, Task 17), ədəbiyyat. Mövcud səhifə redaktora çevrilir; mövcud generator ilkin doldurma kimi qalır.

**Forma №3-dən ilkin doldurma:** yeni sillabus fənnin dərc olunmuş tədris vahidlərindən (Task 16, `teaching-load` idxalı) iş yükünü götürür: semestr üzrə mühazirə, məşğələ, laboratoriya kontakt saatları, qruplar, tələbə sayı, müəllimlər. Müəllim dəyərləri dəyişə bilər; Forma №3-dən fərqlənən saat təsdiq zəncirində fərq kimi göstərilir.

**Acceptance criteria:**
- [x] Forma №3-dən idxal olunmuş fənn üçün yeni sillabusun saatları idxal olunmuş kontakt saatlarına bərabərdir; dəyişdirilmiş saat kafedra müdirinin ekranında fərq kimi görünür
- [x] Çəkilərin cəmi 100 deyilsə və ya imtahan çəkisi tenant qaydasına uyğun deyilsə saxlanmır
- [x] Davamiyyət həddi tenant həddindən yuxarı olan sillabus saxlanmır: sillabus həddi yalnız aşağı sala bilər
- [x] Hər saxlama yeni qaralama versiyası yaradır; dərc olunmuş versiya dəyişdirilə bilmir
- [x] Çap görünüşündə bütün dəyərlər escape olunur

**Verification:**
- [x] `python -m pytest tests/unit/test_syllabus_validation.py tests/integration/test_syllabus.py -q`

**Dependencies:** Task 17
**Files likely touched:** `backend/zeka/modules/syllabus/{domain,service,repo,routes}.py`, `backend/migrations/0230_syllabus.sql`, `frontend/js/academy.js`
**Estimated scope:** M

## Task 24: Çərçivə xəritəsi və NICE idxalı

**Description:** `frameworks(key, version, title, source_url)` və `framework_items(framework_id, code, kind, parent, title)`. `manage.py import-framework --file`: NIST-in dərc etdiyi NICE Framework Components v2.2.0 JSON faylını oxuyur. Test nümunəsi real fayldan kəsilir. Fayl əlçatan deyilsə tapşırıq bloklanmış qalır; nümunə və ya fayl əl ilə yazılmır. Bloom və EQF daxili gəlir. Nəticə ↔ bənd xəritəsi üçün axtarışlı seçim. Əhatə hesabatı: iş rolu üzrə hansı bilik, bacarıq və tapşırıq bəyanatı hansı fənnin nəticəsi ilə örtülür; CSV ixracı.

**Acceptance criteria:**
- [ ] NICE idxalı idempotentdir və versiyanı saxlayır; yeni versiya idxal olunanda köhnə xəritələr oxunaqlı qalır
- [ ] İdxal NIST-in dərc etdiyi dəyişdirilməmiş fayldan aparılır; idxaldan sonra hər növ üzrə (iş rolu, bilik, bacarıq, tapşırıq bəyanatı) sətir sayı fayldakı element sayına bərabərdir
- [ ] Bir nəticə bir neçə çərçivənin bəndləri ilə işarələnə bilir
- [ ] Proqram üzrə əhatə hesabatı örtülməyən bəyanatları sadalayır

**Verification:**
- [ ] `python -m pytest tests/integration/test_frameworks.py -q`
- [ ] `python backend/manage.py import-framework --file content/frameworks/nice-components-2.2.0.json`

**Dependencies:** Task 23; sahibin NICE addımı (`tasks/plan.md`, Sahibin addımları)
**Files likely touched:** `backend/zeka/modules/syllabus/frameworks.py`, `backend/migrations/0240_frameworks.sql`, `content/frameworks/`, `frontend/js/academy.js`
**Estimated scope:** M

## Task 25: Təsdiq axını və fənnin konfiqurasiyası

**Description:** Statuslar: qaralama → təqdim olunub → kafedra təsdiqləyib → dərc olunub; hər addımda şərhlə geri qaytarma. Versiyalar arası fərq görünüşü. Dərc olunanda: jurnal komponentləri, fənnin davamiyyət həddi (`courses.attendance_limit`, Task 20-nin miqrasiyası), AI siyasətinə görə tutor rejimi, imtahan planının ilkin dəyərləri təyin olunur. Tələbə fənn səhifəsində dərc olunmuş sillabusu görür.

**Acceptance criteria:**
- [x] Zəncirdə yalnız növbəti rol statusu irəli apara bilir
- [x] Dərc fənnin qiymət komponentlərini və tutor rejimini sillabusdakı kimi dəyişir
- [x] Dərc fənnin davamiyyət həddini təyin edir; jurnal bundan sonra min(tenant həddi, sillabus həddi) tətbiq edir (test: tenant 25%, sillabus 20%, 21% qayıb "imtahana buraxılmır" verir)
- [x] Bal artıq yazılıbsa, dərc tədris şöbəsinin açıq, auditli icazəsi olmadan bloklanır; tələbə yalnız dərc olunmuş versiyanı görür

**Verification:**
- [x] `python -m pytest tests/integration/test_syllabus_workflow.py -q`

**Dependencies:** Task 23, Task 21
**Files likely touched:** `backend/zeka/modules/syllabus/{service,routes}.py`, `backend/zeka/modules/journal/service.py`, `frontend/js/academy.js`, `frontend/js/student.js`
**Estimated scope:** M

## Task 26: İmtahan nüvəsi

**Description:** Cədvəllər: `exams` (növ `kind`: əsas | təkrar | fərdi vaxt; pəncərə, müddət, plan, qoruma rejimi, şəbəkə siyahısı, status), `exam_roster(exam_id, student_id, status, səbəb)`, `exam_forms` (tələbə üzrə sual və variant sırası, toxum), `exam_attempts`, `exam_answers`, `exam_events` (yalnız əlavə olunan imtahan jurnalı; `seq`, `prev_hash`, `hash` sütunları və `UNIQUE(exam_id, seq)` bu miqrasiyadadır, zənciri Task 30 hesablayır). İmtahan siyahısı (`exam_roster`) imtahan açılanda bir dəfə çəkilir: fənnə qeydiyyatdan və `journal/service.py`-dəki buraxılış statusundan. `domain.py`: plana görə hovuzlardan variant qurulması (nəticə və çətinlik üzrə say), toxumla təkrarlanan qarışdırma, son vaxt, avtomatik təslim. Son vaxtı keçmiş, təslim olunmamış cəhdləri `exam.autosubmit` dövri işi bağlayır; iş Task 36-nın icraçısında bu tapşırıqda qeydiyyatdan keçir. Qiymətləndirmə imtahan bağlananda mövcud `engine.grade` ilə. Sual hovuzu: bu tapşırığın miqrasiyası `questions.purpose` sütununu əlavə edir (`practice` | `exam`, susmaya görə `practice`). Dəyər sual ilk dəfə təsdiqlənəndə seçilir və sonra dəyişmir. İmtahan planı yalnız `purpose='exam'` suallardan qurulur və onları `learning` servisinin funksiyası ilə oxuyur. `purpose='exam'` sual tələbəyə yalnız `scope="exam"` marşrutları ilə, öz cəhdi daxilində gedir: `practice_turn`, `INDEX["questions"]`, Radar-ın məşq addımı onu istisna edir, `quiz_create` 400 qaytarır.

**Acceptance criteria:**
- [x] İki tələbə fərqli sual və variant sırası alır; eyni tələbə həmişə eyni variantı alır
- [x] `deadline_at`-dan sonrakı cavab server saatı ilə rədd olunur; iki dəfə başlatma eyni cəhdi qaytarır
- [x] Tələbə sorğu göndərmədən: `deadline_at` keçəndən sonra növbəti `exam.autosubmit` dövrəsi cəhdi təslim olunmuş edir (saat irəli çəkilən test); `tests/integration/test_periodic_jobs.py`-nin gözlənilən iş siyahısına `exam.autosubmit` əlavə olunub
- [x] Siyahıda olmayan tələbə (fənnə yazılmayıb və ya jurnalda "imtahana buraxılmır") cəhd başlada bilmir: 403, tərcümə olunmuş səbəb, hadisə imtahan jurnalında. `office` səbəb yazmaqla istisna əlavə edir; istisna auditdədir.
- [x] Tələbəyə açıq hər imtahan marşrutunun cavabı icazə siyahılı sxemlə yoxlanır (sual üçün yalnız `id`, `qtype`, `text`, `options`, `unit`); siyahıda olmayan hər açar (`answer`, `explanation`, `correct`, `score` daxil) testi yıxır. Açıqlamadan sonra tələbə yalnız yekun balı və nəticə üzrə bölgünü görür; sualın açarı və izahı V1-də heç bir tələbə marşrutunda qayıtmır.
- [x] Sızma testi: mətnində, variantlarında və izahında nişan sətri olan `purpose='exam'` suallardan imtahan qurulur; fənnə yazılmış tələbə adi sessiya ilə marşrut cədvəlindəki bütün GET marşrutlarını çağırır, Məşq rejimində hovuz tükənənə qədər tutorla danışır və Radar planını açır; heç bir cavabda nişan yoxdur. `purpose='exam'` sualın testə əlavə edilməsi və təsdiqlənmiş sualın `purpose`-unun dəyişdirilməsi 400 qaytarır.
- [x] Proses UTC-də, `ZEKA_TZ=Asia/Baku`: 10:00–12:00 kimi daxil edilən pəncərə `06:00:00+00:00`-da açılır, `08:00:00+00:00`-da bağlanır

**Verification:**
- [x] `python -m pytest tests/unit/test_exam_rules.py tests/integration/test_exam_core.py tests/security/test_exam_item_leak.py -q`

**Dependencies:** Task 13, Task 21, Task 36 (dilim 1: iş icraçısı və dövri işlər)
**Files likely touched:** `backend/zeka/modules/exam/{domain,service,repo,routes}.py`, `backend/migrations/0260_exam.sql`, `backend/zeka/legacy/{r_learning,store,radar}.py`, `tests/security/test_exam_item_leak.py`, `tests/integration/test_periodic_jobs.py`
**Estimated scope:** L (üç dilim: sual hovuzu, variant, cəhd dövrü)

## Task 27: İmtahan əhatəli sessiya və imtahan səhifəsi

**Description:** Tələbə imtahana girəndə sessiya `exam:{id}` əhatəsi alır. Əhatə iki istiqamətlidir: `exam:{id}` əhatəli sessiya yalnız `scope="exam"` marşrutlarına çatır; `scope="exam"` marşrutu yalnız əhatəsi həmin marşrutun imtahanına bərabər olan sessiyaya açılır (adi sessiya və başqa imtahanın sessiyası 403 alır). `frontend/exam.html` və `js/exam.js`: naviqasiyasız səhifə; vəziyyətlər: yoxlanır, hazırdır, gedir, təslim olunub. Hər dəyişiklikdə və 20 saniyədən bir avtomatik saxlama; oflayn növbə və təkrar cəhd; yenidən yükləmədən sonra davam. Tək sessiya: imtahana giriş tələbənin bütün başqa sessiyalarını bağlayır. Cəhd gedərkən adi giriş imtahan sessiyasını bağlamır və imtahan marşrutlarına çatmır; cəhdi yalnız Task 28 və Task 29 yoxlamalarından keçən yeni imtahana giriş öz üzərinə götürür və əvvəlki imtahan sessiyasını bağlayır. Hər iki hal imtahan hadisəsi kimi yazılır.

**Acceptance criteria:**
- [x] Marşrut cədvəlindən qurulan avtomatik test: imtahan əhatəli sessiya ilə imtahandan kənar hər marşrut 403; adi tələbə sessiyası ilə hər `scope="exam"` marşrutu 403; `exam:1` sessiyası ilə 2-ci imtahanın cəhd marşrutları 403
- [x] Oflayn yazılan cavablar bağlantı qayıdanda çatdırılır (şəbəkə söndürülən e2e test)
- [x] İmtahana giriş tələbənin başqa sessiyalarını bir sorğu ərzində bağlayır; cəhd gedərkən adi giriş imtahan sessiyasını bağlamır
- [x] Taymer serverin verdiyi qalan saniyədən sayılır; müştəri saatı 4 saat səhv olanda da server son vaxtı ilə 2 saniyə dəqiqliklə üst-üstə düşür
- [x] 300 simulyasiya olunmuş tələbə imtahanı başladır, cavab yazır və təslim edir: itən cavab 0 (server sayı = müştəri sayı), p95 < 500 ms (`faculty` dəsti). Ölçmə 2026-11-19: 300 saniyəyə yayılmış rejimdə 3 000 / 3 000 cavab, p95 8 ms; hamısı birdən (`--burst`) p95 871 ms (1 işçi), 621 ms (4 işçi), itki 0: `docs/perf/baseline.md`

**Verification:**
- [x] `python -m pytest tests/security/test_exam_scope.py -q`
- [x] `python -m pytest tests/integration/test_exam_page.py -q` (Playwright skripti `tests/e2e/exam_offline.js`; node + Playwright olmayanda keçirilir)
- [x] `python tools/loadtest.py --scenario exam --users 300 --seconds 300 --dataset faculty`

**Dependencies:** Task 26
**Files likely touched:** `backend/zeka/core/web.py`, `backend/zeka/modules/exam/routes.py`, `frontend/exam.html`, `frontend/js/exam.js`, `frontend/css/m-exam.css`, `tests/security/test_exam_scope.py`, `tools/loadtest.py`
**Estimated scope:** L (7 fayl; iki dilim: əhatəli sessiya və imtahan səhifəsi; imtahan yük ssenarisi)

## Task 28: SEB inteqrasiyası

**Description:** `modules/exam/seb.py`: `plistlib` ilə konfiqurasiya (`startURL`, `quitURL`, `hashedQuitPassword`, URL filtri, `sendBrowserExamKey`, `browserWindowWebView=3`, `allowVirtualMachine=false`, mübadilə buferi və ekran şəkli bağlı). Config Key: `originatorVersion` çıxarılır, boş lüğətlər silinir, açarlar böyük-kiçik hərfə baxmadan sıralanır, sıx JSON, SHA-256. `GET /exam/{id}/config.seb?k=`, `sebs://` keçidi. Yoxlama: başlıq (`X-SafeExamBrowser-ConfigKeyHash`) və JS API (`SafeExamBrowser.security.updateKeys`); server `sha256(URL + açar)` ilə sabit vaxtlı müqayisə edir; başlıq yolunda URL = `PUBLIC_URL` + sorğunun xam hədəfi (`handler.path`: dekodlanmamış yol və sorğu sətri), JS API yolunda müştərinin göndərdiyi `location.href`-in sxemi və hostu `PUBLIC_URL` ilə eyni olmalıdır; yoxlanan URL-də sessiya üzrə birdəfəlik dəyər var. İstinad faylının oxuyucusu xam XML plist və gzip + `plnd` bükümünü qəbul edir; `pswd`, `pwcc` və ya `pkhs` gələrsə səbəbi deyən xəta verir.

**Acceptance criteria:**
- [ ] Sahibin verdiyi nümunə `.seb` faylı üçün hesablanan Config Key SEB Config Tool-un göstərdiyi açarla eynidir
  (2026-11-19: alqoritm iki real SEB faylında yoxlanıb: SEB 2.1.4 macOS və 2.2.3 Windows, açarlar Moodle-un testindən; fayllar lisenziyaya görə repoya qoyulmayıb, `SEB_TEST_VECTORS` ilə işləyir. Sahibin faylı `tests/fixtures/reference.seb` + `reference.seb.key` kimi qoyulanda test özü işə düşür)
- [x] `seb` rejimində səhv və ya olmayan hash ilə cəhd başlamır və yoxlanmamış sessiya mövcud cəhdin sual və cavab marşrutlarında 403 alır; bir sessiyada tutulan hash başqasında rədd olunur
- [ ] Yaradılan fayl Windows-da SEB 3.x ilə açılır və yalnız imtahanı göstərir (əl sınağı)
- [x] `PUBLIC_URL` dinləmə ünvanından fərqli olanda (`https://zeka.test`) və URL-də `%2F` və iki parametr olanda düzgün hash qəbul olunur; `http://127.0.0.1:port` üzərində hesablanan hash rədd olunur

**Verification:**
- [x] `python -m pytest tests/unit/test_seb_config_key.py tests/integration/test_seb_verify.py -q`
- [ ] Əl sınağı: SEB qurulmuş kompüterdə sınaq nüsxəsində `sebs://` keçidi; nüsxə yoxdursa LAN-da `seb://`

**Dependencies:** Task 27
**Files likely touched:** `backend/zeka/modules/exam/seb.py`, `backend/zeka/modules/exam/routes.py`, `exam/template.plist`, `frontend/js/exam.js`, `frontend/js/teacher.js`, `tests/fixtures/reference.seb`
**Estimated scope:** M

## Task 29: Nəzarətçi paneli

**Description:** İmtahan üzrə `proctor` təyinatı. 5 saniyəlik sorğu ilə canlı lövhə: siyahı statusu (`exam_roster`-dən, Task 26), irəliləyiş, son görünmə, hadisələr (fokus itkisi, tam ekrandan çıxış, yenidən qoşulma, ünvan dəyişməsi). Səbəbi məcburi əməliyyatlar: vaxt əlavə et, dayandır, davam etdir, cəhdi bitir, yenidən aç, giriş kilidini aç (yalnız öz imtahan siyahısındakı tələbə üçün). Şəbəkə siyahısı girişdə və hər `scope="exam"` sorğusunda yoxlanır: siyahıdan kənar ünvan 403 alır və jurnala yazılır; siyahı daxilində ünvan dəyişməsi lövhə hadisəsidir.

**Acceptance criteria:**
- [x] `allowed_cidrs`-dən kənar ünvandan giriş və cəhd ortasında gələn sorğu rədd olunur və jurnala yazılır. Ünvan `client_ip()`-dən gəlir; `ZEKA_PROXY_HOPS=1` ilə üç hal yoxlanır: `X-Forwarded-For` siyahıdadır (buraxılır), kənardadır (rədd), `içəri-saxta, kənar-real` (rədd: sağdan birinci ünvan götürülür). `ZEKA_PROXY_HOPS=0` ilə başlıq nəzərə alınmır.
- [x] Hər nəzarətçi əməliyyatı səbəb tələb edir və imtahan jurnalında görünür
- [x] Tələbənin vəziyyət dəyişməsi lövhədə 10 saniyə ərzində əks olunur

**Verification:**
- [x] `python -m pytest tests/integration/test_proctor.py -q`

**Dependencies:** Task 27
**Files likely touched:** `backend/zeka/modules/exam/{service,repo,routes}.py`, `backend/migrations/0290_proctor.sql` (nəzarətçi təyinatı; `exam_events` Task 26-nın miqrasiyasındadır), `frontend/js/proctor.js`, `frontend/css/m-exam.css`
**Estimated scope:** M

## Task 30: Hash zəncirli protokol və nəticənin jurnala keçməsi

**Description:** `exam_events` (Task 26-da yaradılıb; Task 26, 27 və 29 ona hadisə yazır) yalnız əlavə olunur: `hash = sha256(prev_hash + kanonik hadisə)`. Bu tapşırığa miqrasiya düşmür (qeyd 2026-11-19: zəncir sütunları 0260-dadır; protokolun bağlantısı və bağlanmış cədvəllər üçün `0300_exam_release.sql` əlavə olundu). Zəncir imtahan üzrə təkdir və `seq` ilə sıralanır: `UNIQUE(exam_id, seq)`; əlavə `BEGIN IMMEDIATE` içində gedir (başı oxu → hesabla → yaz). Task 29 hadisələrindən əlavə: təslimdə və avtomatik təslimdə `attempt.submitted {attempt_id, form_seed, answers_sha256}` (`answers_sha256` = `qid` üzrə sıralanmış `(qid, value)` siyahısının kanonik JSON-unun SHA-256-sı); bağlananda qiymətləndirmədən sonra `attempt.graded {attempt_id, score}`, sonra `exam.closed`. `manage.py exam-verify <id> [--root <hex>]` halqaları yoxlayır, hər cəhdin son `attempt.submitted` dəyərini `exam_answers`-dən, `attempt.graded` dəyərini `exam_attempts`-dən yenidən hesablayır, başı protokoldakı köklə və verilibsə `--root` ilə tutuşdurur. Kök bazadan kənara çıxır: protokolda tam 64 simvol çap olunur və bağlananda outbox (Task 36) ilə imtahan müəlliminə və dekanlığa göndərilir. İmtahan bağlanandan sonrakı bal dəyişikliyi (apellyasiya) yalnız jurnalda, səbəb və müəlliflə aparılır (Task 21); `exam_attempts` dəyişmir. Bağlananda mövcud sənəd infrastrukturu ilə protokol: faktlar, saylar, insidentlər, zəncirin kökü, QR. Xam bal imtahan komponentinin maksimumuna `exam/domain.py`-də çevrilir; yuvarlaqlaşdırma qaydası yalnız oradadır. Müəllim nəticəni açıqlayır; bal jurnalın imtahan komponentinə `journal/service.py` ilə, `exam_id` və `attempt_no` ilə yazılır (sütunlar Task 21-in `0210_journal.sql` miqrasiyasındadır). Əvvəlki imtahanın açıqlanmış nəticəsi saxlanır, üstünə yazılmır. Nəticə statusu: keçdi | imtahan < minimum | cəm < keçid | buraxılmayıb | gəlməyib. Açıqlamadan sonra qrup üzrə "imtahan-qiymət cədvəli" mövcud QR sənəd infrastrukturunda yeni sənəd növü kimi yaradılır; onu `office` bağlayır. Protokol və cədvəl Task 45-in saxlanmış yüklü verilmə yolundan keçir. Sual statistikası və oxşar səhv cavab cütlərinin siyahısı müəllimə siqnal kimi verilir.

**Acceptance criteria:**
- [x] Saxlanan hər hansı hadisənin (sonuncu daxil) dəyişdirilməsi və ya silinməsi `exam-verify`-ı yıxır və ilk qırıq halqanı göstərir (dilim 1: sonuncunun silinməsi `--root` ilə tutulur; protokoldakı kök dilim 3-dədir)
- [x] Təslimdən sonra `exam_answers.value`-nun və ya bağlanandan sonra `exam_attempts` balının bazada birbaşa dəyişdirilməsi `exam-verify`-ı yıxır və cəhdi göstərir; `yenidən aç`-dan sonrakı yeni təslim yıxmır
- [x] Protokolun QR-i doğrulanır və eyni kökü göstərir; zəncir və protokol sətri bazada yenidən hesablanıb yazılandan sonra `exam-verify --root <e-poçtdakı kök>` yıxılır
- [x] İki prosesdən 500 paralel hadisə boşluqsuz bir zəncir verir (`seq` 1..N) və `exam-verify` keçir (dilim 1: `tests/integration/test_exam_verify.py`, `test_exam_chain_concurrency.py`)
- [x] Açıqlanan ballar jurnalda görünür, açıqlama auditdədir; oxşarlıq siyahısını yalnız müəllim görür
- [x] Vahid test: imtahan komponentinə çevrilmiş 16,9 bal keçmir, 17,0 keçir (imtahan minimumu 17)
- [x] Təkrar imtahanın nəticəsi ilk nəticəni silmir; hər iki cəhd müəllimə və dekanlığa görünür
- [x] Bağlanmış cədvəldən sonra imtahan balını yalnız `office` dəyişir: səbəb və apellyasiya müraciətinin (`grade_appeal`) və ya əmrin nömrəsi ilə; dəyişiklik qiymət jurnalındadır

**Verification:**
- [x] `python -m pytest tests/integration/test_exam_verify.py tests/unit/test_exam_chain.py tests/unit/test_exam_scaling.py tests/integration/test_exam_release.py tests/integration/test_exam_statement.py tests/integration/test_exam_chain_concurrency.py -q`
- [x] `python backend/manage.py exam-verify 1`

**Dependencies:** Task 26, Task 29, Task 36 (dilim 2: outbox və e-poçt), Task 45
**Files likely touched:** `backend/zeka/modules/exam/{domain,service,repo}.py`, `backend/zeka/modules/journal/service.py`, `backend/zeka/legacy/docs.py`, `backend/manage.py`, `frontend/js/teacher.js`
**Estimated scope:** M

## Checkpoint D: Task 23–30 sonra

- [x] 300 simulyasiya olunmuş tələbə ilə sınaq imtahanı: `python tools/loadtest.py --scenario exam --users 300 --seconds 300 --dataset faculty` 0 itki və p95 < 500 ms verir. Əmr Task 27-də yazılır və Task 30-dan sonra yenidən işlədilir (hash zənciri və nəzarətçi sorğusu yükə əlavə olunur) — Checkpoint D-dən sonra: 3 000 / 3 000, itki 0, p95 11 ms, lövhə p95 28 ms (`docs/perf/baseline.md`)
- [ ] Windows kompüterində SEB ilə əl sınağı (sahib)
- [x] Rəy axını və `security-review` keçib: `docs/review/checkpoint-d-2026-11-19.md` (bir Medium tapıntı düzəldilib, borclu testlər yazılıb)
- [ ] Sahiblə baxış: SEB (TM-8, SEC-3, TM-17), nəzarətçi vaxtı (TM-14), sual bazası (TM-13), təkrar imtahan hüququ, oxşarlıq həddi (AR-8), SF-14/J2

---

## Faza 5 — Köməkçi, sual-cavab, icma, inteqrasiya

## Task 31: Kampus köməkçisi: otaq tapma və marşrut

**Description:** Marşrut qrafı: düyünlər (giriş, pilləkən, lift, dəhliz kəsişməsi, otaq qapısı), tillər (uzunluq, pilləsiz keçid). CSV idxalı. `facilities/domain.py`-də Dijkstra. Mətn addımları; mərtəbə planı şəkli verilibsə nişanla. Köməkçi niyyətləri: otaq kodu və ya adı, "növbəti dərsim hardadır", müəllimin otağı və qəbul saatı. QR-dən başlanğıc nöqtəsi (`/r/{kod}?to=`). Pilləsiz seçim. Pilot korpus: dalğa 0 cədvəlində ən azı bir dərsi olan korpus; siyahı Task 18-in otaq bağlama hesabatından çıxır. Düyün və til CSV-sini Task 31 sahibin verdiyi mərtəbə planlarından qaralayır; sahibin təyin etdiyi şəxs 5 marşrutu yerində yoxlayır (SPEC Open Questions 25).

**Acceptance criteria:**
- [x] Pilot korpuslarda Task 18-də idxal olunmuş hər otaq qrafda düyündür; istənilən iki otaq arasında marşrut qayıdır və ya çatışmayan bağlantı yazılır — demo-nun sintetik qrafında (`content/routes/`); real CSV sahibin mərtəbə planlarından gəlir (açıq), idxal hesabatı düyünü olmayan otaqları və yolsuz qapıları sadalayır
- [x] Pilləsiz marşrut heç vaxt pilləkəndən keçmir (200 təsadüfi qraf + demo-da bütün qapı cütləri)
- [x] "Növbəti dərsim" cavabı cədvəllə eynidir; cavab 2 saniyədən tez gəlir (tələbə və müəllimin öz iCal lenti ilə müqayisə). Müəllimin qəbul saatı niyyəti Task 34-də əlavə olunub; mərtəbə planı şəklində nişan plan verilənə qədər yoxdur

**Verification:**
- [x] `python -m pytest tests/unit/test_routing.py tests/integration/test_assistant_rooms.py -q` (12 keçdi)

**Dependencies:** Task 18, Task 19
**Files likely touched:** `backend/zeka/modules/facilities/{domain,repo}.py`, `backend/migrations/0310_routes.sql` (marşrut qrafının düyün və til cədvəlləri), `backend/zeka/modules/assistant/{service,routes}.py`, `frontend/js/chat.js`, `frontend/js/facilities.js`
**Estimated scope:** M

## Task 32: Kampus köməkçisi: bilik bazası idarəsi və insana ötürmə

**Description:** Bilik bazası məqalələri bazaya keçir: versiya, mənbə (sənəd, bənd), əməliyyat keçidi, yenidən baxış tarixi; admin ekranı. Dəyişiklik indeks siqnalı verir. Mənbə tapılmayanda köməkçi dəstək sorğusu və ya müəllim sualı yaratmağı təklif edir, söhbət konteksti ilə. `tests/eval/assistant_az.jsonl`: 50 sual (qayda, xidmət, otaq, əhatədən kənar) və işlədici.

**Acceptance criteria:**
- [x] Redaktə olunan məqalə növbəti sualda hər prosesdə istifadə olunur (`test_kb_admin`, `test_multiworker_state::test_a_knowledge_base_article_…`)
- [x] Hər cavab ya mənbə, ya insana ötürmə daşıyır; ikisi də olmayan cavab yoxdur (`assistant.service.campus_answer` təmin edir; qiymətləndirmədə 0)
- [x] Qiymətləndirmə dəstində ən azı 45/50 düzgün mənbə (48/50; iki səhv: davamiyyət faizi sualı qayıb məqaləsinə gedir, "Rektorun maşını" qiymətləndirmə məqaləsinə)

**Verification:**
- [x] `python -m pytest tests/integration/test_kb_admin.py -q`
- [x] `python tools/eval_assistant.py tests/eval/assistant_az.jsonl`

**Dependencies:** Task 7, Task 31
**Files likely touched:** `backend/zeka/modules/assistant/{service,repo,routes}.py`, `backend/migrations/0320_kb.sql`, `frontend/js/admin-kb.js`, `tests/eval/assistant_az.jsonl`, `tools/eval_assistant.py`
**Estimated scope:** M

## Task 33: Müəllimə sual və fənn forumu

**Description:** Mövcud `teacher_questions` mövzulara çevrilir: fənn, müəllif, həmyaşıdlara anonimlik, başlıq, mətn, həftə və ya mövzu etiketi, status. Cavablar, müəllimin "təsdiqlənmiş cavab" işarəsi. Materiallardan AI qaralaması yalnız müəllimə görünür, təsdiqdən sonra dərc olunur. Cavablanmış sual fənn FAQ-ına keçə bilir və tutor indeksinə düşür. Şikayət və gizlətmə.

**Acceptance criteria:**
- [x] Fənnin mövzularını yalnız ora yazılanlar və fənnin müəllimi oxuyur (`test_qa`; moderator yalnız şikayət növbəsində görür)
- [x] Anonim müəllifi tələbələr görmür; fənnin müəllimi və `qa.moderate` icazəsi olan görür
- [x] AI qaralaması təsdiqdən əvvəl tələbəyə göstərilmir; FAQ-a keçən cavaba tutor istinad edə bilir

**Verification:**
- [x] `python -m pytest tests/integration/test_qa.py -q`

**Dependencies:** Task 13
**Files likely touched:** `backend/zeka/modules/qa/{domain,service,repo,routes}.py`, `backend/migrations/0330_qa.sql`, `frontend/js/qa.js`, `frontend/js/teacher.js`
**Estimated scope:** M

## Task 34: Qəbul saatları

**Description:** Müəllim həftəlik vaxt aralıqları təyin edir (otaq və ya onlayn keçid). Tələbə yer tutur və ləğv edir. Görüş hər iki tərəfin cədvəlində və iCal lentində görünür. Xatırlatma bildirişi.

**Acceptance criteria:**
- [x] Bir aralıq iki dəfə tutula bilmir (paralel sorğu testi; unikal indeks olmadan test düşür)
- [x] Görüş hər iki iCal lentində görünür
- [x] Ləğv qarşı tərəfə bildiriş göndərir (həm tələbə, həm müəllim tərəfindən; xatırlatma bir dəfə)

**Verification:**
- [x] `python -m pytest tests/integration/test_office_hours.py -q`

**Dependencies:** Task 19, Task 33
**Files likely touched:** `backend/zeka/modules/qa/office_hours.py`, `backend/zeka/modules/qa/routes.py`, `backend/migrations/0340_office_hours.sql`, `frontend/js/qa.js`
**Estimated scope:** M

## Task 35: Klublar və kanallar

**Description:** Klub (ad, təsvir, rəhbər, dekanlığın təsdiqi), üzvlük sorğusu, kanallar, mesajlar (≤ 2 000 simvol), `GET .../messages?since_id=` ilə 3 saniyəlik sorğu, elan kanalı (yalnız rəhbər yazır), tədbirlər mövcud xəbər və qeydiyyat axını ilə. Moderasiya: şikayət → növbə; mesajı gizlət, üzvü müddətli sustur, kənarlaşdır. İlk yazıdan əvvəl davranış qaydalarının qəbulu. Saxlama müddəti (susmaya görə 180 gün) fon işi ilə. İstifadəçi üzrə limit.

**Acceptance criteria:**
- [x] Üzv olmayan hər kanal marşrutunda 403 alır (marşrut cədvəlindən: `test_community_access`)
- [x] Şikayət olunan mesaj `community.moderate` icazəsi olanların növbəsinə düşür; hər moderasiya addımı auditdədir
- [x] Susdurulan üzvün yazısı susdurmanın bitmə vaxtı ilə rədd olunur; müddəti keçən mesajları fon işi silir

**Verification:**
- [x] `python -m pytest tests/integration/test_community.py tests/security/test_community_access.py -q`

**Dependencies:** Task 13, Task 36
**Files likely touched:** `backend/zeka/modules/community/{domain,service,repo,routes}.py`, `backend/migrations/0365_community.sql` (Task 36-dan asılıdır: boş bazada `0360`-dan sonra işləyir), `frontend/js/community.js`, `frontend/css/m-community.css`
**Estimated scope:** L (iki dilim: üzvlük və mesaj; moderasiya)

## Task 36: E-poçt bildirişləri və dövri işlər

**Description:** `core/jobs.py`: bazada iş cədvəli, icarə müddətli tək işçi dövrü nəzarətçinin başlatdığı və yenidən başlatdığı ayrıca uşaq prosesdə; `smtplib.SMTP(timeout=10)`. `outbox`: alıcı, şablon, parametrlər, dil, status, cəhd sayı, növbəti cəhd. `smtplib` və STARTTLS. Mövcud bildiriş növləri üçün üç dildə şablon. İstifadəçinin növ və kanal üzrə seçimi. İki dilim: (1) iş icraçısı və dövri işlər; (2) outbox və e-poçt. Tapşırıq mərhələ 4-ün siyahısındadır, amma saat 22–36-da qurulur (`tasks/plan.md`, Paralel zolaqlar): Task 26 dilim 1-dən, Task 30 dilim 2-dən asılıdır.

Dövri işlər (dilim 1). Bu gün heç nə öz-özünə işləmir: vaxta bağlı iş yalnız sorğu gələndə və ya server açılanda görülür (`docs/CODEMAP.md`, inventar 34). İş icraçısı dövri işləri də işlədir: `jobs.periodic(ad, interval, funksiya)` reyestri və `job_runs(name, started_at, finished_at, status, detail)` son icra qeydi. Növbəti icra son uğurlu icradan hesablanır; icraçı dayanıb qalxanda buraxılmış interval bir dəfə işlənir. İşlər:

- `retention.purge`, gündəlik: `store.purge_expired` (söhbət), vaxtı keçmiş sessiyalar, birdəfəlik açarlar və limit sayğacları. Task 35 və Task 40 öz cədvəllərini bu işə qoşur.
- `reminders.sla`, 15 dəqiqədən bir: müraciətin və dəstək sorğusunun SLA-sı və son tarix xatırlatmaları; hər hədd üçün bir bildiriş. Tapşırığın son tarixi Task 22-də, qəbul saatı Task 34-də eyni işə qoşulur.
- `lessons.generate`, gündəlik: Task 19-un idempotent dərs yaradılması, cari semestrin `teaching_end` tarixinə qədər.
- `exam.autosubmit`, dəqiqədə bir: son vaxtı keçmiş, təslim olunmamış imtahan cəhdləri. Funksiya Task 26-dadır və iş orada qeydiyyatdan keçir.
- `radar.snapshot`, həftəlik: Radar-ın həftəlik görüntüsü (bu gün onu yalnız seed yazır).

`manage.py jobs status` hər işin son icrasını və nəticəsini göstərir.

**Acceptance criteria:**
- [x] SMTP kəsintisi mesajı gecikdirir, itirmir (saxta SMTP serveri ilə test; artan fasilə ilə təkrar cəhd)
- [x] Bağlantını qəbul edib cavab verməyən saxta SMTP: cəhd 15 saniyədə uğursuz sayılır, növbədəki digər işlər davam edir, öldürülən web işçisi yenə 2 saniyəyə bərpa olunur
- [x] Növü bağlayan istifadəçi həmin növdən e-poçt almır
- [x] Hər e-poçt alıcının dilindədir
- [x] Saat irəli çəkilən test (`core/clock.py`): interval keçəndə reyestrdəki hər dövri iş düz bir dəfə işləyir və `job_runs`-da uğurlu qeyd var; interval keçməyibsə növbəti dövrə heç nə işlətmir; iki icraçı proseslə də hər iş bir dəfə işləyir
- [x] Test reyestrdəki iş adlarını gözlənilən siyahı ilə tutuşdurur: `retention.purge`, `reminders.sla`, `lessons.generate`, `radar.snapshot`; `exam.autosubmit` siyahıya Task 26-da əlavə olunur
- [x] Xəta verən dövri iş `job_runs`-da səbəblə qalır, digər işləri saxlamır və növbəti dövrədə təkrar cəhd olunur

**Verification:**
- [x] `python -m pytest tests/integration/test_jobs.py tests/integration/test_email_outbox.py tests/integration/test_periodic_jobs.py -q` (dilim 1: `test_jobs.py`, `test_periodic_jobs.py` keçir)
- [x] `python backend/manage.py jobs status`

**Dependencies:** Task 7; `lessons.generate` işi Task 19 birləşdiriləndən sonra qoşulur
**Files likely touched:** `backend/zeka/core/jobs.py`, `backend/zeka/modules/comms/{service,repo,routes}.py`, `backend/migrations/0360_comms.sql` (`jobs`, `job_runs`, `outbox`), `backend/manage.py`, `backend/zeka/legacy/{store,radar}.py`, `content/email-templates/`, `tests/integration/test_periodic_jobs.py`
**Estimated scope:** L (iki dilim, iki commit: iş icraçısı və dövri işlər; outbox və e-poçt)

## Task 37: İnteqrasiya mərkəzi

**Description:** Əhatəli API açarları (hash ilə saxlanır, açar üzrə limit, audit). İmzalı webhook-lar (HMAC-SHA256, təkrar cəhd, `urlopen(timeout=10)`): `grade.published`, `attendance.barred`, `exam.released`. İxraclar: OneRoster CSV arxivi, qiymətlər CSV, davamiyyət CSV, sütunları tənzimlənən reyestr ixracı, "Tələbə-məzun" operatoru üçün dəyişiklik siyahısı: verilən tarixdən bəri `student_status_events`, 10 günlük müddətə qalan gün, "daxil edildi" işarəsi (`reported_at`). Fərziyyə: 10 gün əmr tarixindən (`order_date`) sayılır; 225 nömrəli Fərmanla yoxlanmalıdır (SPEC Open Questions 17). `manage.py export --kind grades|attendance|oneroster [--since <ISO vaxt>]`: `--since` qiymət və davamiyyətdə yalnız həmin andan sonra yazılan və ya dəyişən sətirləri verir (kəsiddən sonrakı geri qayıtma üçün, `tasks/plan.md`). Ekran və əmr eyni ixrac servisini çağırır; ikinci ixrac yolu yoxdur. "Tətbiqlər" səhifəsi: adminin rola görə qurduğu, qalan xarici sistemlərə aparan kafellər. `docs/API.md` yenilənir.

**Acceptance criteria:**
- [x] Açar yalnız öz əhatəsindəki marşrutları çağıra bilir (cookie heç bir açar marşrutuna, açar heç bir cookie marşrutuna çatmır)
- [x] Webhook çatdırılması imzalanır, təkrar cəhd olunur və jurnala yazılır
- [x] OneRoster ixracı boş nüsxəyə idxal olunanda eyni reyestri verir, qeydiyyatın `beginDate`/`endDate` sahələri daxil (dövrə testi; qruplar OneRoster növü olmadığı üçün nüsxədə əvvəlcə yaradılır)
- [x] Dəyişiklik siyahısı verilən tarixdən sonrakı hər status hadisəsini 10 günlük müddətə qalan günlə göstərir; operator "daxil edildi" işarələyəndə `reported_at` yazılır və hadisə növbəti siyahıda işarəli çıxır (10 gün `order_date`-dən: 225 nömrəli Fərmanla yoxlanmalıdır)
- [x] `manage.py export --kind attendance --since T` və `--kind grades --since T` yalnız T-dən sonra yazılan və ya dəyişən sətirləri verir; ekrandakı ixrac eyni sətirləri verir

**Verification:**
- [x] `python -m pytest tests/integration/test_api_tokens.py tests/integration/test_webhooks.py tests/integration/test_oneroster_roundtrip.py tests/integration/test_status_change_list.py tests/integration/test_export_since.py -q`
- [x] `python backend/manage.py export --kind attendance --since 2026-12-01T00:00:00+04:00`

**Dependencies:** Task 16, Task 36
**Files likely touched:** `backend/zeka/modules/integration/{tokens,webhooks,export,routes}.py`, `backend/manage.py`, `backend/migrations/0370_integration.sql`, `frontend/js/apps.js`, `docs/API.md`
**Estimated scope:** L (üç dilim: açar, webhook, ixrac və kafel)

## Task 46: E-xidmətlərin dürüstlüyü

**Description:** Bu gün `issue` istənilən addımda qəbul olunur və bütün addımları bir rol icra edir; 13 müraciət növündən 10-u müraciət sətrindən kənar heç nə dəyişmir, amma hazır cavab mətni dəyişiklik olduğunu deyir (`docs/CODEMAP.md` L34, L35). Üç dəyişiklik, iki dilim: (1) addımın icraçısı; (2) təsir və prod rejimində təklif.

Addımın icraçısı. `request_types.steps`-in hər addımı rol id-si daşıyır (Task 13 cədvəlindən; əhatə `role_grants`-dən). `POST /api/requests/{id}/action` cari addımı yalnız həmin addıma təyin olunmuş rolla irəli aparır, qaytarır və ya rədd edir; `issue` yalnız son addımda qəbul olunur. `admin` addım icraçısı deyil. Hər əməl icraçısı ilə mövcud `request_events`-də qalır. Bildiriş yalnız növbəti addımın roluna, əhatəsi daxilində gedir.

Təsir. Hər növ `effect` sahəsi daşıyır: `none` və ya kodda qeydiyyatı olan təsirin adı (məsələn `attendance.excuse`, `student_status.leave`, `document.issue`). Təsir son addımda, eyni tranzaksiyada, təminatçı modulun `service.py` funksiyası ilə icra olunur; `document.issue` Task 45-in saxlanmış yüklü verilmə yolundan keçir. `effect = none` olan növün cavabı sərbəst mətn deyil, tək faktiki şablondan qurulur: müraciət qeydə alınıb, hansı bölmə baxıb, qərar nədir, Zəka-da başqa qeyd dəyişməyib. 13 növün hər biri üçün seçim (təsir icra olunur və ya mətn şablona keçir) `content/seed.json`-da və data miqrasiyasında yazılır.

Prod rejimində təklif. `request_types.enabled` sütunu: prod rejimində susmaya görə 0, demo rejimində 1. Admin növü açır və bağlayır; bu yalnız bayraqdır, forma və addım redaktoru yoxdur (SPEC Out of Scope). Bağlı növ kataloqda (`GET /api/services`), axtarışda və köməkçinin əməliyyat düyməsində görünmür; ona `POST /api/requests` 404 qaytarır. `effect`-i kodda qeydiyyatda olmayan növ açılmır. Açma və bağlama auditdədir. Prod bazasına növlər, formalar və addımlar `0461_request_types.sql` data miqrasiyası ilə düşür (seed prod rejimində işləmir, Task 5); mətnlər `content/seed.json`-dakı ilə eynidir ki, tərcümə açarları üst-üstə düşsün.

**Acceptance criteria:**
- [x] 3 addımlı `academic_leave` müraciətində ilk addımda `issue` 409 qaytarır; hər addımı yalnız həmin addıma təyin olunmuş rol irəli aparır, başqa rol (`admin` daxil) 403 alır. Qeyd: həmin növdə heç bir addımı olmayan rol (məsələn `academic_leave`-də `dept_head`) müraciəti görmür və 404 alır (Task 13: mövcudluq açılmır); sahibin qərarı
- [x] Hər addımın icraçısı, əməli və vaxtı müraciətin tarixçəsində görünür
- [x] Test bütün müraciət növlərini gəzir: `effect` ≠ `none` olan növdə son addımdan sonra təsir bazadadır (`absence_excuse`: davamiyyət sətri üzrlüdür; `academic_leave`: `student_status_events` sətri var); `effect = none` olan növün cavabı faktiki şablondan qurulub və belə növ üçün sərbəst `answer` mətni varsa test yıxılır
- [x] Prod rejimində admin heç bir növ açmayıbsa `GET /api/services` boş kataloq qaytarır və `POST /api/requests` 404 verir; açılan növ görünür; açma audit hadisəsi yazır; demo rejimində bütün növlər açıqdır
- [x] `effect`-i kodda qeydiyyatda olmayan növü açmaq cəhdi 400 qaytarır
- [x] `0461_request_types.sql`-dəki növ adları və cavab mətnləri `content/seed.json`-dakı ilə eynidir (test)

**Verification:**
- [x] `python -m pytest tests/integration/test_service_honesty.py -q`

**Dependencies:** Task 13, Task 15, Task 20, Task 45
**Files likely touched:** `backend/zeka/legacy/r_services.py`, `backend/migrations/0460_request_steps.sql` (`request_types.enabled`, `request_types.effect`), `backend/migrations/0461_request_types.sql` (data: növlər, formalar, addımlar və rolları), `content/seed.json`, `frontend/js/services.js`, `frontend/js/admin-settings.js`, `tests/integration/test_service_honesty.py`
**Estimated scope:** L (iki dilim, iki commit: addımın icraçısı; təsir və prod rejimində təklif)

## Checkpoint E: Task 31–37 və Task 46 sonra

- [x] 50 suallıq dəstdə mənbə düzgünlüyü ≥ 90% (48/50 = 96%, mənbəsiz və ötürməsiz cavab 0)
- [x] Hər yeni modul təhlükəsizlik matrisindədir (288 marşrut)
- [x] Prod rejimində yalnız adminin açdığı müraciət növləri təklif olunur; `python backend/manage.py jobs status` beş dövri işin hər biri üçün son uğurlu icranı göstərir (səkkiz iş: 8/8)
- [ ] Rəy axını keçib; sahiblə baxış

---

## Faza 6 — Miqrasiya, sərtləşdirmə, buraxılış

## Task 38: ETL və uzlaşdırma

**Description:** `tools/etl/`: mənbə faylı növü üzrə adapter, sütun xəritəsi `content/mappings/<mənbə>.json`-da, çevirmələr (ad normallaşdırma, qrup kodu, qiymət şkalası). Yükləmə Task 16-dakı idxal servisindən keçir (quru sınaq, ya tam ya heç, idempotentlik, `import_links`). Bu tapşırıq reyestrə və `manage.py import`-a jurnal növlərini əlavə edir: `--kind attendance|attendance-opening|grades`. Bu növlərdə `--as-of <tarix>` məcburidir: sətirlərin kəsid tarixi (`as_of`) ondan gəlir. `backend/zeka/modules/migration/loaders.py` sətirləri doğrulayır və `journal/service.py`-nin açıq funksiyalarını çağırır; jurnal cədvəllərinə birbaşa yazmır.

Cari semestrin davamiyyəti iki formadan biri ilə gəlir (SPEC Open Questions 2). (a) `attendance`, dərs səviyyəsi: tədris vahidinin `sourcedId`-si, tələbənin `sourcedId`-si, tarix, başlama saatı, status; dərs (tədris vahidi, tarix, başlama saatı) açarı ilə tapılır, tapılmasa həmin açarla yaradılır (Task 19). (b) `attendance-opening`, köhnə sistem yalnız yekun verirsə açılış qalığı: tələbə × fənn üzrə kəsid tarixinə qədər keçilmiş saat, üzrsüz və üzrlü qayıb saatı (yükləyici Task 20-dədir). Dərs səviyyəli ixracda tədris vahidi və ya başlama saatı yoxdursa, adapter qeydləri tələbə × fənn üzrə `attendance-opening` sətirlərinə cəmləyir. Bir tələbə × fənn üçün yalnız bir forma qəbul olunur; ikinci forma rədd olunur. `grades`: tələbə × fənn × komponent × bal × maksimum (yükləyici Task 21-dədir). Hər idxal sətri `source='legacy'` və kəsid tarixi (`as_of`) daşıyır; qiymət jurnalında müəllif idxal edən hesabdır, səbəb idxal faylının adı və SHA-256-sıdır. A variantında (`tasks/plan.md`, "Qeydin sahibi") eyni növlər paralel dövrün müqayisəsi üçün təkrar idxal olunur.

Tarixi yekun qiymətlər `results` idxal növü ilə gəlir (tələbə, fənn, semestr, kredit, bal); bu növü də reyestrə bu tapşırıq əlavə edir. Uzlaşdırma keçəndə `history_reconciled_at` qoyulur. Köhnə sistemdə verilən status əmrləri `status-events` növü ilə gəlir (tələbənin `sourcedId`-si, növ, əmr nömrəsi, əmr tarixi, qüvvəyə minmə tarixi, qrup): `directory/service.py` ilə `student_status_events`-ə yazılır (Task 15), `entered_by` idxal edən hesabdır. Eyni (tələbə, əmr nömrəsi, əmr tarixi) üzrə Zəka-da artıq daxil edilmiş hadisə ikinci dəfə yaradılmır, mənbə ilə bağlanır (`import_links`). `manage.py reconcile --wave N --source <ad>`: varlıq üzrə say (istifadəçi, fənn, tədris vahidi, qeydiyyat, status əmri, cədvəl, davamiyyət açılış qalığı və ya dərs səviyyəli davamiyyət, bal), açar sahələrin yoxlama cəmi, əl yoxlaması üçün 50 təsadüfi qeyd, fərq hesabatı. Uzlaşdırma yalnız həmin mənbə üçün `import_links`-də olan sətirləri müqayisə edir; hesabata ixrac anı və hər mənbə faylının SHA-256-sı yazılır. Açar sahələrə tələbə × fənn üzrə üzrsüz və üzrlü saat, tələbə × fənn × komponent üzrə bal daxildir. Kəşf birinci saatdan başlayır: köhnə sistemlərin ixrac formatı.

**Acceptance criteria:**
- [x] Verilən ixraclar üzərində quru sınaq izahsız sətir qalmayan xəritə və doğrulama hesabatı verir (sintetik ixraclarla: `content/mappings/sample-sis.json`; real ixrac formatı sahibdən gözlənilir)
- [x] İdxaldan sonra uzlaşdırma hər varlıq üçün mənbə sayı = mənbə ilə bağlı (`import_links`) sətir sayı göstərir
- [x] Zəka-da yaradılan sətir fərq sayılmır; hesabatda ixrac anı və fayl SHA-256-ları var
- [x] Davamiyyət və qiymət uzlaşdırılır: tələbə × fənn üzrə qayıb saatı cəmi (üzrsüz və üzrlü ayrıca) və (tələbə, fənn, komponent, bal) yoxlama cəmi mənbə ilə bərabərdir
- [ ] Pilot fakültənin 50 təsadüfi tələbəsinin qayıb faizi kəsid tarixində köhnə sistemin rəqəmi ilə eynidir; dekanlıq təsdiqləyir (`reconcile` 50 təsadüfi qeydi verir; müqayisə real ixracla dekanlığındır)
- [x] Açılış qalığı olan tələbə × fənn üçün `as_of`-a qədərki dərs səviyyəli sətir rədd olunur, dərs səviyyəli sətri olan üçün açılış qalığı rədd olunur: qayıb iki dəfə sayılmır
- [x] Köhnə sistemdə verilən status əmri `status-events` idxalından sonra `student_status_events`-dədir və tələbəni qüvvəyə minmə tarixindən sonrakı dərs siyahılarından çıxarır; eyni əmr Zəka-da əvvəlcədən daxil edilibsə ikinci hadisə yaranmır
- [x] Təkrar işlətmə dublikat yaratmır
- [x] Yazan idxal hər hansı imtahan `gedir` statusunda olanda başlamır (`--force` yalnız audit qeydi ilə); 200 000 sətirdən böyük yükləmə fayllara bölünür, hər fayl ayrıca atomardır

**Verification:**
- [x] `python -m pytest tests/migration/test_etl.py -q`
- [x] `python backend/manage.py reconcile --wave 0 --source <mənbə>` (sintetik mənbə ilə; `--dir` dalğanın fayllarının qovluğudur)

**Dependencies:** Task 16, Task 20, Task 21, Task 26
**Files likely touched:** `tools/etl/{adapters,transforms,run}.py`, `content/mappings/`, `backend/manage.py`, `backend/zeka/modules/migration/loaders.py`, `backend/zeka/modules/journal/service.py`, `tests/migration/test_etl.py`, `tests/fixtures/attendance_lessons.csv`, `tests/fixtures/attendance_opening.csv`, `tests/fixtures/grades.csv`, `tests/fixtures/status_events.csv`
**Estimated scope:** L (iki dilim: jurnal növləri və yükləyicilər; ETL adapterləri və uzlaşdırma). Dilim 1 Task 21 bitən kimi, saat 22–36 zolağında qurulur; dilim 2 saat 62–72-də. Task 26 asılılığı yalnız dilim 2-nin son meyarına aiddir.

## Task 39: Ölçülmüş göstəricilər və akkreditasiya sübutu

**Description:** `events` cədvəli (kim, nə, nə vaxt, modul) nüvə qarmağı ilə yazılır. Göstəricilər hesablanır: rol üzrə həftəlik aktiv istifadəçi, jurnalın doldurulma faizi, müraciətin icra müddəti və SLA, mənbəli cavab payı, imtahan sayı. `r_admin.py` və `staff.js`-dəki sabit rəqəmlər çıxarılır. Akkreditasiya səhifəsi: 3.5.1, 3.5.3, 5.4.2–5.4.8 göstəriciləri üzrə canlı say və keçidlər; ixrac.

**Acceptance criteria:**
- [x] Heç bir panel kafeli sabit rəqəmdən qidalanmır (test analitika modulunu yoxlayır və hər kafelin sorğusu olduğunu təsdiqləyir)
- [x] Hər kafel öz tərifini və zaman aralığını göstərir
- [x] Sübut səhifəsi ixrac olunur

**Verification:**
- [x] `python -m pytest tests/integration/test_insight.py -q`

**Dependencies:** Task 21, Task 30
**Files likely touched:** `backend/zeka/core/events.py`, `backend/zeka/modules/insight/{service,repo,routes}.py`, `backend/migrations/0390_events.sql`, `backend/zeka/legacy/r_admin.py`, `frontend/js/staff.js`
**Estimated scope:** M

## Task 40: Məxfilik: razılıq, saxlama, ixrac, silmə

**Description:** Məqsəd üzrə razılıq qeydi: mətnin versiyası, vaxt, üsul. Saxlama işi: söhbət, icma, jurnallar tenant ayarına görə. `GET /api/me/export`: istifadəçinin öz məlumatı. Silmə sorğusu axını; qanunla saxlanmalı akademik qeydlər anonimləşdirilir. Məxfilik bildirişi üç dildə. `docs/privacy/data-inventory.md`: cədvəl × məqsəd × müddət × hüquqi əsas; maddə 15 qeydiyyatı üçün əsas.

**Acceptance criteria:**
- [x] İxrac istifadəçiyə bağlı hər cədvəl sətrini ehtiva edir (test istifadəçi açarı olan cədvəlləri sadalayır). İstisna: `exam_forms` və açıqlanmamış imtahan balı ixraca düşmür; açıqlamadan sonra ixrac yalnız tələbənin öz cavablarını və balını verir, sual mətni və açar yoxdur. İstisna `data-inventory.md`-də yazılır; Task 26-nın sızma testi `/api/me/export`-u da çağırır.
- [x] Silmə inventara uyğun silir və ya anonimləşdirir və auditdədir
- [x] Xarici AI yalnız cari mətn versiyası üçün yazılmış razılıqla çağırılır
- [x] Sahibin qərarları (2026-11-21):
  - AI tutor və kampus köməkçisi hər rol üçün yalnız cari `ai` razılığı ilə işləyir; razılıq yoxdursa, 403 qaytarır və
    heç nə saxlamır.
  - Profildə razılığı geri götürmək olar; geri götürmə söhbətləri silir.
  - Razılıq pəncərəsi yalnız AI səhifəsində çıxır və "İndi yox" düyməsi var.
  - Xarici AI xidmətinin adı və ölkəsi bildirişdə ayardan göstərilir; başqa xidmət yeni versiyadır.
  - Radar risk balı ixracdadır.
  - Hüquqi suallar `docs/privacy/data-inventory.md`, "Qərarlar" bölməsində həll olunub.

**Verification:**
- [x] `python -m pytest tests/integration/test_privacy.py -q`

**Dependencies:** Task 36
**Files likely touched:** `backend/zeka/modules/identity/privacy.py`, `backend/zeka/core/jobs.py`, `backend/migrations/0400_privacy.sql`, `docs/privacy/data-inventory.md`, `frontend/js/main.js`
**Estimated scope:** M

## Task 41: Təhlükəsizlik baxışı və NIST nəzarət matrisi

**Description:** Bütün fərq üzərində rəy axını və `security-review` skili. `docs/security/nist-csf-profile.md`: CSF 2.0 funksiyası → nəzarət → SP 800-53 Rev. 5.2.0 id-si → sübut (fayl və ya test) → status. `docs/security/hecvat-lite.md`. İmtahan və kimlik üçün təhdid modeli (STRIDE cədvəli). `/.well-known/security.txt`. `docs/research/04-nist-ve-uygunluq.md`-dəki 22-ci nəzarət SI-7-yə xəritələnir, sübut Task 30 testləridir; AU-10 "iddia olunmur" statusu ilə yazılır (imza yoxdur). Qəbul edilmiş risklər təhdid modelində yazılır: TOTP toxumunun bazada açıq saxlanması (Task 12), sənəd hash-inin açarsız olması (Task 45).

**Acceptance criteria:**
- [ ] Təsdiqlənən hər tapıntının düzəlişi və reqressiya testi var; təkzib olunan hər tapıntının təkzibi yazılıb
- [ ] Matrisdəki hər "72 saat" nəzarəti koda və ya testə keçid verir
- [ ] Buraxılışda açıq yüksək səviyyəli tapıntı yoxdur

**Verification:**
- [ ] `python -m pytest tests/security -q`
- [ ] `docs/security/review-log.md`: tapıntı, hökm, düzəliş

**Dependencies:** Task 37
**Files likely touched:** `docs/security/`, `frontend/.well-known/security.txt`, rəyin göstərdiyi fayllar
**Estimated scope:** M

## Task 42: E2E, əlçatanlıq və yük testi

**Description:** Playwright tüstü testi: Task 13-dəki hər rol × 3 dil × masaüstü və mobil. İmtahanın oflayn daxil e2e testi. 10 əsas səhifədə axe-core (WCAG 2.2 AA). Yük: imtahan 500 istifadəçi 30 dəqiqə, gündəlik qarışıq 1 000 istifadəçi; hər ikisi `--dataset university` ilə; maşının nüvə sayı, yaddaşı və işçi sayı nəticə faylında. İmtahan ssenarisi 60 saniyə ərzində 500 girişlə başlayır. Xaos: imtahan ortasında `kill -9`, məşğul baza, SMTP kəsintisi. Nəticələr `docs/perf/`-də.

**Acceptance criteria:**
- [ ] E2E dəsti CI-da yaşıldır; axe 10 səhifədə ciddi və kritik pozuntu tapmır
- [ ] İmtahan yükü və gündəlik qarışıq 1 000 istifadəçi: p95 < 500 ms, itən cavab 0 (server sayı = müştəri sayı), 5xx 0 (`university` dəsti)
- [ ] `tests/load/test_query_plans.py` qarışıq və imtahan ssenarilərinin marşrutlarını da yoxlayır: 1 000 sətirdən böyük cədvəl üzrə `SCAN` yoxdur
- [ ] `kill -9`-dan sonra hər cəhd saxlanmış bütün cavablarla davam edir
- [ ] Məşğul baza: 2 saniyə saxlanan yazma kilidi zamanı 5xx = 0, itən cavab 0

**Verification:**
- [ ] `npx playwright test --trace off`
- [ ] `python tools/loadtest.py --scenario exam --users 500 --seconds 1800 --dataset university`
- [ ] `python tools/loadtest.py --scenario mixed --users 1000 --dataset university --seconds 600`
- [ ] `python -m pytest tests/load/test_query_plans.py -q`
- [ ] Yük sınağından sonra `python backend/manage.py exam-verify <yük imtahanının id-si>` keçir

**Dependencies:** Task 30; Task 35 (kəsilməyibsə)
**Files likely touched:** `tests/e2e/*.spec.js`, `tools/loadtest.py`, `tests/load/test_query_plans.py`, `docs/perf/`, `.github/workflows/ci.yml`
**Estimated scope:** M

## Task 43: Runbook-lar

**Description:** `docs/runbooks/`: yerləşdirmə və geri qaytarma; backup və bərpa (açarın iki nüsxəsi serverdən kənarda saxlanır: sahib və AzTU İT); imtahan günü (24 saat əvvəl yoxlama, gediş, insident, kağız ehtiyat; protokol çap olunur və imzalanır; imtahan bağlananda `manage.py backup` işlədilir); insident cavabı; fakültənin qoşulması (idxal → uzlaşdırma → təlim); dalğa üzrə kəsid siyahısı (T0 və T1 anları, "Qeydin sahibi" cədvəli, geri qayıtma yolu: `manage.py export --since <kəsid anı>` və köhnə sistemin yazma rejiminə qaytarılması; yazan idxallar dərs saatlarından kənar işlədilir). Yerləşdirmə və imtahan günü runbook-larında host saatının yoxlaması var: `timedatectl show -p NTPSynchronized --value` → `yes`.

**Acceptance criteria:**
- [ ] Hər runbook hədəf və ya sınaq serverində bir dəfə icra olunub, çıxışı əlavə edilib
- [ ] Bərpanın müddəti ölçülüb və yazılıb
- [ ] Geri qayıtma ixracı sınaq serverində bir dəfə icra olunub, müddəti ölçülüb
- [ ] İmtahan günü runbook-u Task 42-nin imtahan yük sınağında və SEB əl sınağının təkrarında istifadə olunub

**Verification:**
- [ ] Əl yoxlaması: başqa adam yalnız runbook və açarın kənar nüsxəsi ilə bərpanı icra edir

**Dependencies:** Task 9, Task 8, Task 37, Task 42
**Files likely touched:** `docs/runbooks/*.md`
**Estimated scope:** S

## Task 44: Buraxılış

**Description:** Hədəf serverə yerləşdirmə, ilk administrator, hədəf serverdə `university` yük testi (canlı məlumatdan əvvəl, ayrıca müvəqqəti bazada), dalğa 0 məlumatının idxalı, uzlaşdırma, hər rol üçün tüstü yoxlaması, backup cədvəli, izləmə (sağlamlıq, disk, backup yaşı, göndərmə xətası), SPEC-in Success Criteria siyahısı üzrə keç və ya keçmə baxışı, `v1.0.0` teqi.

**Acceptance criteria:**
- [ ] Keç və ya keçmə siyahısı sahib tərəfindən təsdiqlənib
- [ ] Hədəf serverdə, canlı məlumat idxal olunmazdan əvvəl, ayrıca müvəqqəti bazada `loadtest --scenario mixed --users 1000 --dataset university --seconds 300` və `--scenario exam --users 500 --dataset university --seconds 300`: p95 < 500 ms, itki 0; nəticə `docs/perf/target.md`-də, müvəqqəti baza silinib
- [ ] T0 ixracına qarşı uzlaşdırma fərqi 0 və ya izahlı; T0 `docs/runbooks/release-v1.md`-də yazılıb
- [ ] Cədvəl üzrə avtomatik göndərilmiş backup ikinci maşında, açarın kənar nüsxəsi ilə bərpa olunub
- [ ] Backup yaşı > 26 saat, boş disk < 20% və göndərmə xətası üçün adı yazılmış alıcıya xəbərdarlıq qurulub; hər biri sınaqda bir dəfə işə salınıb
- [ ] Pilot istifadəçilərin ilk real girişləri uğurludur

**Verification:**
- [ ] `python tools/loadtest.py --scenario mixed --users 1000 --dataset university --seconds 300`
- [ ] `python tools/loadtest.py --scenario exam --users 500 --dataset university --seconds 300`
- [ ] `python backend/manage.py reconcile --wave 0 --source <mənbə>`
- [ ] `infra/restore.sh` ikinci maşında

**Sahibin verəcəkləri (BOŞ YERLƏR, 2026-11-21).** Sahib bu dəyərləri sonra verəcək, yerləri saxlanılsın. Dəyər
`docs/runbooks/release-v1.md`-dəki "Sahibin verəcəkləri" cədvəlinə yazılır və burada işarələnir:
- [ ] 1. Hədəf server: host, əməliyyat sistemi, disk, backup üçün ikinci host → `infra/.env` (serverdə), `release-v1.md`.
  Gələnə qədər yerləşdirmə, serverdə yük testi, bərpa sınağı və izləmə bloklanır.
- [ ] 2. Windows-da SEB 3.x ilə əl sınağı → `release-v1.md`, "Əl sınaqları". Gələnə qədər Task 28-in son meyarı və `seb`
  rejimli ilk real imtahan bloklanır.
- [ ] 3. İstinad `.seb` faylı və açarı → `tests/fixtures/reference.seb`, `reference.seb.key`. Gələnə qədər Task 28-in
  Config Key meyarı bloklanır: test faylı gözləyir və bu yoxlamanı buraxır.
- [ ] 4. İnsident əlaqələri (adlar, telefonlar) → hədəf serverdəki `docs/runbooks/incident.md`, git-ə yazılmır. Gələnə
  qədər insident cavabının hazırlığı və Checkpoint F-də sahibin qərarı bloklanır.
- [ ] 5. Təhlükəsizlik əlaqəsi və yoxlanma tarixi → `ZEKA_SECURITY_CONTACT`, `ZEKA_SECURITY_EXPIRES` (serverdə
  `infra/.env`). Gələnə qədər `/.well-known/security.txt` verilmir.
- [ ] 6. T0 anı → `release-v1.md`, "Anlar"; idxalda `--as-of`. Gələnə qədər dalğa 0-ın idxalı və uzlaşdırma bloklanır.

**Dependencies:** Task 38, Task 41, Task 42, Task 43
**Files likely touched:** `infra/.env` (serverdə), `docs/runbooks/release-v1.md`, `docs/perf/target.md`
**Estimated scope:** S

## Checkpoint F: buraxılış qapısı

- [ ] SPEC-dəki bütün Success Criteria təsdiqlənib və ya istisna yazılı qeyd olunub
- [ ] Hədəf serverdə bərpa sınağı və `university` yük testi keçib; ilk fakültənin T0 ixracına qarşı uzlaşdırma fərqi 0 və ya izahlı; T0 release runbook-da yazılıb
- [ ] Açıq yüksək səviyyəli təhlükəsizlik tapıntısı yoxdur
- [ ] Sahibin yazılı buraxılış qərarı

## Task 48: Semestr cədvəli qurucusu

**Description:** Bu gün dərs cədvəlinin sətirləri yalnız əl ilə yazılır (Task 19); Forma №3-dən gələn tədris vahidləri (Task 47) özü cədvələ düşmür. Qurucu semestrin bütün girişlərini bir yerə yığır, toqquşmasız cədvəl layihəsini hesablayır, dekanlıq və kafedralar layihəyə baxır, tədris şöbəsi onu effektiv tarixdən dərc edir. Dizayn: Task 48-in son dizaynı (`f3work/tt-design.md`, repozitoriyadan kənarda; §13-də üç dilim).

Dilim 1 (bu tapşırığın modeli və həlledicisi). Miqrasiyalar `0480`–`0483`: semestrin hazırlığı, vahidin ehtiyacları, qrupun növbəsi, müəllimin və otağın məşğulluq xanaları, həftəlik bloklar (təcrübə, hərbi hazırlıq, bağlı həftələr, məzuniyyət), Forma №3 idxalının nəticəsi, hesablamalar, versiyalar, yerləşdirmələr, yerləşdirilməyənlər, rəylər, qeydlər; `rooms.schedulable`, `rooms.dedicated`; `timetable.meeting_key`, `period`, `version_id`. Universitet ayarlarında `timetable` bölməsi və onun yoxlaması (qanuni 30 saat hədd yalnız aşağı salına bilər). `timetable/domain.py`: həftə dəstinin qrammatikası (`all | odd | even | N[-M],…`) və Task 19 qaydalarının maskalara keçməsi, həftəlik bölgü qaydası, iclaslar, müstəqil yoxlayıcı (H1–H14, H16), skor kartı, plan və Forma №3 saatlarının hesabatı, bütöv dəstdə saat toqquşması. `timetable/solver.py` (təmiz, I/O yoxdur): ilkin quruluş (çıxarma ilə), tavlama (köçürmə, dəyişmə, sökmə və yenidən qurma), kilidlər, istinad versiyasına sabitlik, təmir (`from_week`, keçmiş həftələr dəyişmir), hissə-hissə davam etmə, yerləşdirilməyən iclasın səbəbləri. `tools/ttbench.py` sintetik kafedra və universitet.

Dilim 2: repo, servis, marşrutlar, `timetable.work` və `timetable.health` işləri, dərc (sətirlər, dərslər, rəsmi sənəd, bildiriş), matris, i18n, inteqrasiya testləri. Dilim 3: tədris şöbəsi, dekanlıq, kafedra və müəllim səhifələri, brauzer testləri.

**Acceptance criteria (dilim 1):**
- [x] `0480`–`0483` cari sxemli, sətirləri olan bazaya tətbiq olunur; mövcud sətirlər dəyişmir, otaq susmaya görə cədvələ açıqdır və ortaqdır, əl ilə yazılmış sətrin iclası yoxdur; semestrdə eyni anda bir aktiv hesablama (`test_0480_to_0483_keep_the_rows_already_there`)
- [x] `test_privacy.py` yeni şəxs sütunları ilə keçir (inventar, sənəd, ixrac, silmə, tam cədvəl oxunmur); `test_layers.py` `solver.py`-ni təmiz fayllar sırasında yoxlayır (saat, `os`, repo, servis yoxdur)
- [x] Xüsusiyyət testləri 200 təsadüfi nümunədə keçir: nəticə, quruluşun ortasında kəsilmiş vəziyyət və ləğv olunmuş hesablama yoxlayıcıdan keçir; dərc olunacaq sətirlərdə saat toqquşması yoxdur; həlledicinin xərci skor kartı ilə eynidir; eyni toxum eyni baytlar verir, N iterasiya N/2 + JSON + N/2-yə bərabərdir; saatla dayandırılıb davam etdirilən hesablama eyni nəticəni verir; yerləşdirilməyən iclasın heç bir otaqda heç bir boş qiyməti yoxdur (≤ 12 iclas, tam yoxlama); kilidli yerləşdirmələr qalır, qaydanı pozan kilid yerləşdirilmir; dəyişiklik olmayan təmir heç nəyi köçürmür, bir müəllimin yeni xanasından sonra yalnız həmin müəllimin iclasları köçür; `from_week`-dən əvvəlki həftələrə toxunulmur
- [x] Qızıl imza Python 3.11, 3.12 və 3.13-də eynidir (3.10 CI-da)
- [x] Hər sərt qayda yoxlayıcıda pozulmuş və pozulmamış nümunə ilə; həftəlik bölgü cədvəli (6, 7.5, 8, 10, 14, 15, 18, 20, 24, 30, 45, 60 saat); `odd` ilə `1-3` toqquşur; `conflicts_all` cüt-cüt qaydaya bərabərdir; saat hesabatı fərqin səbəbini adlandırır (`test_tt_rules.py`)
- [x] Real RT + MR payız vahidləri (888 vahid, 956 iclas, sintetik otaqlar, tam model): 0 sərt pozuntu, 0 yerləşdirilməyən (ölçmə repozitoriyadan kənarda; adlar oxunmur və yazılmır)
- [x] `tests/load/test_tt_perf.py` kafedra sütununa cavab verir (1 250 vahid, 300 qrup, 90 müəllim, 60 otaq): hazırlıq ≤ 1 s, ilk tam layihə ≤ 3 s, 50 000 iterasiya ≤ 30 s, yoxlama və skor kartı ≤ 1 s, yaddaş ≤ 80 MB, 0 sərt pozuntu, 0 yerləşdirilməyən, layihənin yazılması bir qısa tranzaksiyada; universitet sütunu ölçülüb `docs/perf/timetable.md`-də yazılıb
- [x] Əl ilə yazma yolu əvvəlki kimidir (`test_timetable_conflicts.py` və Task 19 inteqrasiya testləri)
- [x] `timetable` ayar bölməsi administratorun mövcud ayar marşrutu ilə saxlanır; səhv quruluşlu dəyər (siyahı içində siyahı və ya obyekt) tərcümə olunmuş 400 olur, heç vaxt 500 yox (`test_the_timetable_settings_are_checked`)

**Acceptance criteria (dilim 2 və 3):** dizaynın §13-ü; bu tapşırığın sonrakı commit-lərində buraya köçürülür.

**Verification:**
- [x] `python -m pytest tests/unit/test_tt_rules.py tests/unit/test_tt_props.py tests/unit/test_timetable_conflicts.py tests/unit/test_layers.py -q`
- [x] `python -m pytest tests/load/test_tt_perf.py tests/migration/test_schema_migrations.py tests/integration/test_privacy.py -q`
- [x] `python tools/ttbench.py --units 1250` və `--units 16700 --groups 4000 --teachers 1200 --rooms 800`

**Dependencies:** Task 15, Task 18, Task 19, Task 47 (vahidlər yalnız cədvəllərdən oxunur, oxucunun Python tiplərindən yox)
**Files likely touched:** `backend/migrations/0480_timetable_inputs.sql`, `0481_rooms_schedulable.sql`, `0482_forma3_imports.sql`, `0483_timetable_versions.sql`, `backend/zeka/core/tenant.py`, `backend/zeka/modules/tenant/service.py`, `backend/zeka/modules/timetable/{domain,solver}.py`, `backend/zeka/modules/identity/repo.py`, `docs/privacy/data-inventory.md`, `tools/ttbench.py`, `docs/perf/timetable.md`, `tests/unit/test_tt_rules.py`, `tests/unit/test_tt_props.py`, `tests/load/test_tt_perf.py`
**Estimated scope:** XL (üç dilim, hər biri ayrı commit)
