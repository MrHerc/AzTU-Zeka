# Tapşırıqlar: Zəka V1

Mənbə: `SPEC.md`, `tasks/plan.md` · Vəziyyət: **təsdiq gözləyir**
Ölçü: S = 1–2 fayl, M = 3–5 fayl, L = 5–8 fayl. Yollar T03-dən sonrakı quruluşa görədir.
Hər tapşırıq üçün ümumi şərt: `python -m pytest -q`, `ruff check .`, `mypy` yaşıl; yeni sətirlər üç dildə.

---

## Phase 0 — Birləşdirmə və bünövrə

## Task 1: Beş PR-ı birləşdir

**Description:** `trial/integration` sınaq budağının nəticəsi iş budağına gətirilir. Sıra: #3, #5, #4, #2, #1; hər biri `-Xignore-cr-at-eol` ilə. HTTP qatında #5-in `web.Body` oxuyucusu və #3-ün bütün qoruyucuları qalır. #3 və #4-ün `tests/selftest.py`-a yazdığı yoxlamalar pytest-ə köçürülür.

**Acceptance criteria:**
- [ ] Test sayı ən azı 639 + köçürülən təhlükəsizlik və Radar yoxlamalarıdır; heç bir test zəiflədilməyib, keçilməyib, silinməyib
- [ ] #3-ün qoruyucuları yerindədir: CSRF, sorğu ölçüsü və `Transfer-Encoding` yoxlaması, başlıq doğrulaması, limitlər, giriş kodu, sessiya müddəti
- [ ] `python tools/i18n.py stats` en və ru üçün 100% göstərir

**Verification:**
- [ ] `python -m pytest -q`
- [ ] `ruff check . && mypy && for f in static/js/*.js; do node --check "$f"; done`
- [ ] `python run.py --reset --port 5123` açılır, `/api/bootstrap` 200 qaytarır

**Dependencies:** None
**Files likely touched:** `app/web.py`, `app/r_core.py`, `app/r_academy.py`, `app/r_learning.py`, `tests/integration/test_security_review.py`, `tests/integration/test_radar.py`, `README.md`, tərcümə kataloqları
**Estimated scope:** L (birləşdirmə; yeni funksiya yazılmır)

## Task 2: Sətir sonlarını sabitlə

**Description:** `.gitattributes` əlavə olunur (`* text=auto eol=lf`, `*.bat text eol=crlf`, ikili fayllar `binary`). Bütün repo bir ayrıca commit-də normallaşdırılır. Həmin commit-də başqa dəyişiklik olmur.

**Acceptance criteria:**
- [ ] `git ls-files --eol | grep -c "i/crlf"` 0 qaytarır
- [ ] Normallaşdırma commit-i `git diff -w` ilə boşdur
- [ ] `start_demo.bat` Windows-da işləyir (CRLF qalır)

**Verification:**
- [ ] `git ls-files --eol | awk '{print $1}' | sort | uniq -c`
- [ ] `python -m pytest -q`

**Dependencies:** Task 1
**Files likely touched:** `.gitattributes`, bütün CRLF faylları (yalnız sətir sonu)
**Estimated scope:** S

## Task 3: Repo-nu dilə və qata görə böl

**Description:** `git mv` ilə köçürmə, iki commit: (1) `app/` → `backend/zeka/core/` və `backend/zeka/legacy/`, `run.py` → `backend/run.py`; (2) `static/` → `frontend/`, Docker və yerləşdirmə faylları → `infra/`. İdxal yolları, statik qovluq yolu, CI, `pyproject.toml`, README və `CLAUDE.md` yenilənir. Qat qaydasını yoxlayan test əlavə olunur.

**Acceptance criteria:**
- [ ] Davranış dəyişmir: bütün testlər dəyişdirilmədən (yalnız idxal yolu) yaşıldır
- [ ] `git log --follow` köçürülən fayllar üçün tarixçəni göstərir (təmiz adlandırma)
- [ ] `tests/unit/test_layers.py`: heç bir `domain.py` `core.web`, `core.db` və ya `sqlite3` idxal etmir

**Verification:**
- [ ] `python -m pytest -q`
- [ ] `python backend/run.py --port 5123` açılır; əsas səhifə və `/static/` yolları işləyir
- [ ] `docker build -f infra/Dockerfile .`

**Dependencies:** Task 2
**Files likely touched:** bütün `app/`, `static/` (köçürmə), `backend/run.py`, `pyproject.toml`, `.github/workflows/*.yml`, `CLAUDE.md`, `README.md`
**Estimated scope:** L (mexaniki köçürmə, iki commit)

## Task 4: Miqrasiya mühərriki

**Description:** `core/migrate.py`: `schema_migrations(version, name, checksum, applied_at)` cədvəli, `backend/migrations/NNNN_ad.sql` faylları, hər miqrasiya ayrıca tranzaksiyada. `0001_baseline.sql` indiki sxemdir. Prod rejimində `store.init()` bazanı heç vaxt silmir. `manage.py migrate | status`.

**Acceptance criteria:**
- [ ] Sxem versiyası 3 olan demo bazası miqrasiyadan sonra hər cədvəldə eyni sətir sayına malikdir
- [ ] Tətbiq olunmuş miqrasiya faylı dəyişdirilibsə (checksum) və ya baza daha yeni versiyadadırsa, server açılmır və səbəbi yazır
- [ ] Hər miqrasiyadan əvvəl bazanın nüsxəsi yaradılır

**Verification:**
- [ ] `python -m pytest tests/migration/test_schema_migrations.py -q`
- [ ] `python backend/manage.py status`

**Dependencies:** Task 3
**Files likely touched:** `backend/zeka/core/migrate.py`, `backend/zeka/core/db.py`, `backend/migrations/0001_baseline.sql`, `backend/manage.py`, `tests/migration/test_schema_migrations.py`
**Estimated scope:** M

## Task 5: İş rejimləri: demo və prod

**Description:** `core/config.py` bütün ayarları mühit dəyişənlərindən oxuyur. `ZEKA_MODE=prod`: demo giriş marşrutları, seed və reset qeydiyyatdan keçmir. Loopback olmayan ünvanda prod rejimi məcburidir. `manage.py create-admin` ilk administratoru yaradır.

**Acceptance criteria:**
- [ ] Prod rejimində `/api/auth/demo`, `/demo/login`, `/api/admin/reset` 404 qaytarır
- [ ] `--host 0.0.0.0` demo rejimində açılmır
- [ ] Boş prod bazası yalnız `create-admin` ilə yaradılan hesabla açılır; heç bir sintetik istifadəçi yoxdur

**Verification:**
- [ ] `python -m pytest tests/integration/test_modes.py -q`
- [ ] `ZEKA_MODE=prod python backend/run.py` və `curl -s -o /dev/null -w "%{http_code}" -X POST localhost:5070/api/auth/demo`

**Dependencies:** Task 4
**Files likely touched:** `backend/zeka/core/config.py`, `backend/run.py`, `backend/manage.py`, `backend/zeka/legacy/r_core.py`, `backend/zeka/legacy/r_admin.py`
**Estimated scope:** M

## Task 6: Handler qapısı və çox proses

**Description:** Handler icrası sayı məhdud semaforla əhatələnir (`ZEKA_HANDLERS`, susmaya görə 2). Növbə vaxtı bitəndə 503 və `Retry-After`. `run.py --workers N`: `SO_REUSEPORT` ilə eyni portu paylaşan N proses, düşəni yenidən başladan nəzarətçi, səliqəli dayanma. `/healthz` əlavə olunur. `tools/loadtest.py` yazılır.

**Acceptance criteria:**
- [ ] 300 paralel müştəri, oxu ssenarisi: 0 xəta, tək prosesdə ≥ 200 sorğu/san (ölçülmüş baza: 221)
- [ ] 4 proses tək prosesin ən azı 2,5 mislini verir
- [ ] Semafor sızmır: 1 000 xətalı sorğudan sonra normal sorğu cavab alır; öldürülən proses 2 saniyəyə bərpa olunur

**Verification:**
- [ ] `python tools/loadtest.py --scenario read --users 300 --seconds 30`
- [ ] `python -m pytest tests/integration/test_concurrency.py -q`

**Dependencies:** Task 3
**Files likely touched:** `backend/zeka/core/web.py`, `backend/run.py`, `tools/loadtest.py`, `tests/integration/test_concurrency.py`
**Estimated scope:** M

## Task 7: Proses-lokal vəziyyəti bazaya köçür

**Description:** Birdəfəlik sənəd açarları (`common._DOC_KEYS`) və limit sayğacları (`security.py`) cədvələ keçir. Axtarış indeksləri hər prosesdə qurulur; `index_version` ayarı dəyişəndə növbəti sorğuda yenilənir.

**Acceptance criteria:**
- [ ] A prosesinin verdiyi açarı B prosesi bir dəfə qəbul edir, ikinci istifadə rədd olunur
- [ ] Limit proses sayına vurulmur: N proseslə də eyni hədd tətbiq olunur
- [ ] A prosesindən yüklənən material B prosesində növbəti sorğuda axtarışda çıxır

**Verification:**
- [ ] `python -m pytest tests/integration/test_multiworker_state.py -q` (iki prosesli server ilə)

**Dependencies:** Task 4, Task 6
**Files likely touched:** `backend/zeka/core/security.py`, `backend/zeka/legacy/common.py`, `backend/zeka/legacy/engine.py`, `backend/migrations/0002_shared_state.sql`
**Estimated scope:** M

## Task 8: Backup və bərpa

**Description:** `infra/backup.sh`: `sqlite3 .backup` ilə ardıcıl nüsxə, yükləmələrin arxivi, sıxılma, `openssl enc -aes-256-cbc -pbkdf2` ilə şifrələmə, SHA-256 manifest. Saxlama: 7 gündəlik, 4 həftəlik. `infra/restore.sh` manifesti yoxlayır, yeni qovluğa bərpa edir, `PRAGMA integrity_check` işlədir.

**Acceptance criteria:**
- [ ] Təmiz qovluğa bərpa hər cədvəldə eyni sətir sayını və hər yükləmə üçün eyni SHA-256-nı verir
- [ ] Açar faylı olmadan backup uğursuz bitir, şifrəsiz fayl yaratmır
- [ ] CI-da backup → bərpa sınağı işləyir

**Verification:**
- [ ] `infra/backup.sh && infra/restore.sh backups/latest.enc /tmp/restore-test`
- [ ] `python -m pytest tests/migration/test_backup_restore.py -q`

**Dependencies:** Task 4
**Files likely touched:** `infra/backup.sh`, `infra/restore.sh`, `tests/migration/test_backup_restore.py`, `.github/workflows/ci.yml`
**Estimated scope:** M

## Task 9: Yerləşdirmə: Docker, Caddy, sağlamlıq yoxlaması

**Description:** `infra/Dockerfile` (root olmayan istifadəçi, sağlamlıq yoxlaması), `infra/compose.yml` (tətbiq + Caddy; həcmlər: məlumat, backup, sertifikat), `infra/Caddyfile` (TLS, HSTS, sorğu ölçüsü həddi 16 MB), `infra/.env.example`. Giriş jurnalı JSON formatında stdout-a.

**Acceptance criteria:**
- [ ] `docker compose up -d` sonra `https://localhost/healthz` 200 qaytarır; HSTS, CSP, `nosniff` başlıqları var
- [ ] Konteyner root kimi işləmir; `docker compose restart` məlumatı saxlayır
- [ ] `.env.example`-dəki hər dəyişən `docs/runbooks/deploy.md`-də izah olunub

**Verification:**
- [ ] `docker compose -f infra/compose.yml up -d && curl -sk -D- https://localhost/healthz`
- [ ] `docker compose -f infra/compose.yml exec app id -u` (0 deyil)

**Dependencies:** Task 5, Task 6
**Files likely touched:** `infra/Dockerfile`, `infra/compose.yml`, `infra/Caddyfile`, `infra/.env.example`
**Estimated scope:** M

## Checkpoint A: Task 1–9 sonra

- [ ] Bütün testlər yaşıl; rəy axını (tap → təkzib et → düzəlt) keçib
- [ ] `docker compose up` ilə HTTPS açılır; yenidən başlatma məlumatı saxlayır
- [ ] 300 paralel müştəridə 0 xəta; bərpa sınağı keçir
- [ ] Sahiblə baxış; commit və push icazəsi

---

## Phase 1 — Kimlik və reyestr

## Task 10: Hesablar və parol

**Description:** `users` cədvəlinə `email`, `password_hash`, `must_change`, `status`, `failed_count`, `locked_until` əlavə olunur. `POST /api/auth/login`, parol dəyişmə, adminin birdəfəlik müvəqqəti parol verməsi. Hash: `hashlib.scrypt`, parametrlər sətirdə saxlanır. Siyasət NIST SP 800-63B-4 üzrə: tək amildə ≥ 15 simvol, MFA ilə ≥ 8, ən azı 64-ə icazə, tərkib qaydası və dövri dəyişmə yoxdur, zəif parol siyahısı. Prod rejimində rol seçimi ekranı giriş forması ilə əvəz olunur.

**Acceptance criteria:**
- [ ] Yanlış parol və mövcud olmayan istifadəçi eyni cavabı verir; müqayisə sabit vaxtlıdır
- [ ] 10 uğursuz cəhd hesabı 15 dəqiqə kilidləyir və audit hadisəsi yazır
- [ ] Qısa və siyahıdakı parollar tərcümə olunmuş səbəblə rədd olunur; hash parametri dəyişəndə növbəti girişdə yenidən hesablanır

**Verification:**
- [ ] `python -m pytest tests/unit/test_passwords.py tests/integration/test_auth_login.py -q`

**Dependencies:** Task 5
**Files likely touched:** `backend/zeka/modules/identity/{domain,service,repo,routes}.py`, `backend/migrations/0003_identity.sql`, `frontend/js/main.js`, `content/password-blocklist.txt`
**Estimated scope:** M

## Task 11: Sessiya sərtləşdirməsi

**Description:** Sessiya id-sinin SHA-256-sı saxlanır. `last_seen`, `scope`, `mfa_at` sütunları. Boş və mütləq müddət rola görə: işçi 1 saat və 24 saat, tələbə 8 saat və 30 gün (tenant ayarı). `X-Session` başlığı və JSON-dakı token silinir, yalnız kuki qalır. Giriş və hüquq dəyişikliyində id yenilənir. "Sessiyalarım" siyahısı və ləğv.

**Acceptance criteria:**
- [ ] Baza nüsxəsində istifadə edilə bilən sessiya tokeni yoxdur
- [ ] Boş və mütləq müddət serverdə tətbiq olunur (saat irəli çəkilən test)
- [ ] `X-Session` başlığı nəzərə alınmır; girişdən və MFA-dan sonra sessiya id-si dəyişir

**Verification:**
- [ ] `python -m pytest tests/integration/test_sessions.py -q`

**Dependencies:** Task 10
**Files likely touched:** `backend/zeka/modules/identity/{service,repo}.py`, `backend/zeka/legacy/common.py`, `frontend/js/core.js`, `frontend/js/main.js`
**Estimated scope:** M

## Task 12: İşçi rolları üçün TOTP

**Description:** RFC 6238 (HMAC-SHA1, 30 saniyə, 6 rəqəm, ±1 pəncərə), təkrar istifadəyə qarşı son sayğac saxlanır. Qoşulma mövcud `qr.py` ilə `otpauth://` QR-i göstərir. 10 bərpa kodu, hash ilə. Qiymət yazan və ya idarə edən hər rol üçün məcburi; tələbə üçün könüllü.

**Acceptance criteria:**
- [ ] RFC 6238 test vektorları keçir
- [ ] İkinci amili olmayan işçi yalnız qoşulma marşrutlarına çata bilən sessiya alır
- [ ] Eyni kod öz pəncərəsində iki dəfə qəbul olunmur; bərpa kodu bir dəfə işləyir

**Verification:**
- [ ] `python -m pytest tests/unit/test_totp.py tests/integration/test_mfa.py -q`

**Dependencies:** Task 11
**Files likely touched:** `backend/zeka/modules/identity/{domain,service,routes}.py`, `frontend/js/main.js`, `backend/migrations/0003_identity.sql`
**Estimated scope:** M

## Task 13: Rol və icazə modeli

**Description:** Rollar: `student`, `teacher`, `dept_head`, `dean_office`, `academic_office`, `proctor`, `leader`, `admin`. `role_grants(user_id, role, scope_type, scope_id)`: bir istifadəçi bir neçə rolu əhatə ilə daşıya bilir. Marşrut dekoratoru `perm="journal.write"` qəbul edir; icazə xəritəsi `core/perms.py`-dədir. Təhlükəsizlik testi marşrut cədvəlindən rol × marşrut matrisi qurur və `tests/security/matrix.json` ilə müqayisə edir.

**Acceptance criteria:**
- [ ] Matrisdə olmayan yeni marşrut test dəstini yıxır
- [ ] `dept_head` yalnız öz kafedrasının, `teacher` yalnız öz fənninin məlumatını görür və dəyişir
- [ ] Çox rollu istifadəçi aktiv rolu dəyişəndə sessiya id-si yenilənir və audit yazılır

**Verification:**
- [ ] `python -m pytest tests/security/test_authz_matrix.py -q`

**Dependencies:** Task 11
**Files likely touched:** `backend/zeka/core/perms.py`, `backend/zeka/core/web.py`, `backend/zeka/modules/identity/repo.py`, `tests/security/matrix.json`, `tests/security/test_authz_matrix.py`
**Estimated scope:** M

## Task 14: SSO: ümumi OIDC müştərisi

**Description:** Authorization Code + PKCE, `state`, `nonce`. Kəşf ünvanı ayardan. Token və `userinfo` birbaşa TLS ilə alınır. İddia → istifadəçi uyğunlaşdırması (`email` və ya tələbə nömrəsi). Avtomatik hesab yaradılması susmaya görə bağlıdır. Testlər stdlib ilə yazılmış saxta IdP-yə qarşıdır.

**Acceptance criteria:**
- [ ] Saxta IdP ilə tam axın keçir; `state` və ya `nonce` uyğunsuzluğu rədd olunur
- [ ] Tanınmayan istifadəçi hesab yaradılmadan "hesab tapılmadı" alır
- [ ] IdP MFA təsdiqləmirsə, işçi üçün yerli TOTP tələbi qalır

**Verification:**
- [ ] `python -m pytest tests/integration/test_oidc.py -q`

**Dependencies:** Task 12
**Files likely touched:** `backend/zeka/modules/identity/sso.py`, `backend/zeka/modules/identity/routes.py`, `tests/integration/test_oidc.py`, `frontend/js/main.js`
**Estimated scope:** M

## Task 15: Struktur və reyestr idarəsi

**Description:** Cədvəllər: `faculties`, `departments`, `specialties`, `academic_terms`; `study_groups` və `courses` bunlara bağlanır. Admin və tədris şöbəsi üçün siyahı, axtarış, yaratma, dəyişmə, deaktiv etmə ekranları. İki dilim: (1) struktur və semestr, (2) istifadəçi, fənn, qeydiyyat.

**Acceptance criteria:**
- [ ] Hər varlıq üçün yaratma, dəyişmə, deaktiv etmə doğrulama və audit ilə işləyir; silmə yoxdur
- [ ] Deaktiv istifadəçi girə bilmir, tarixçəsi qalır
- [ ] Siyahılar serverdə səhifələnir (səhifədə ≤ 50) və serverdə axtarılır

**Verification:**
- [ ] `python -m pytest tests/integration/test_directory_admin.py -q`
- [ ] Əl yoxlaması: admin kimi fakültə → kafedra → qrup → tələbə yarat, tələbə kimi gir

**Dependencies:** Task 13
**Files likely touched:** `backend/zeka/modules/directory/{domain,service,repo,routes}.py`, `backend/migrations/0004_directory.sql`, `frontend/js/admin-directory.js`, `frontend/js/shell.js`, `frontend/css/m-admin.css`
**Estimated scope:** L (iki dilim, iki commit)

## Task 16: Kütləvi idxal

**Description:** `manage.py import --kind orgs|terms|users|courses|classes|enrollments|rooms|timetable --file F [--dry-run]`. OneRoster 1.2 CSV sütun adları və Azərbaycanca başlıq qarşılıqları qəbul olunur. `sourcedId` üzrə idempotent yeniləmə. Fayl ya tam idxal olunur, ya heç. Admin ekranında yükləmə və quru sınaq önizləməsi. Aktivləşdirmə kodları: birdəfəlik, müddətli, dekanlıq üçün CSV.

**Acceptance criteria:**
- [ ] 10 000 sətirlik istifadəçi faylı 60 saniyədən tez idxal olunur; təkrar işlətmə 0 dəyişiklik bildirir
- [ ] 3 səhv sətri olan fayl heç nə yazmır və 3 sətri nömrə və səbəblə göstərir
- [ ] Aktivləşdirmə kodu bir dəfə işləyir və müddəti bitəndə rədd olunur

**Verification:**
- [ ] `python -m pytest tests/integration/test_import.py -q`
- [ ] `python backend/manage.py import --kind users --file tests/fixtures/users_10k.csv --dry-run`

**Dependencies:** Task 15
**Files likely touched:** `backend/zeka/modules/integration/importer.py`, `backend/manage.py`, `frontend/js/admin-import.js`, `tests/fixtures/*.csv`
**Estimated scope:** M

## Task 17: Tenant ayarları

**Description:** Universitet profili, loqo, qiymət sxemi (komponentlər, çəkilər, imtahan minimumu, keçid balı, hərf şkalası), davamiyyət həddi, dərs saatları, reyestr prefiksi, semestr tarixləri, bayram günləri ayarlara keçir. Admin ekranı. Kodda sabit yazılmış AzTU dəyərləri çıxarılır: `r_academy.py` (`PREREQ`), `docs.py`, `r_learning.py`, `store.py`, `student.js`.

**Acceptance criteria:**
- [ ] Sxemi 30/10/10/50 və imtahan minimumu 17-yə dəyişmək kodu dəyişmədən hesablanan nəticəni dəyişir
- [ ] Sadalanan fayllarda köhnə sabitlər qalmır
- [ ] İkinci, uydurma universitet konfiqurasiyası ilə inteqrasiya testləri keçir

**Verification:**
- [ ] `python -m pytest tests/integration/test_tenant_settings.py -q`

**Dependencies:** Task 15
**Files likely touched:** `backend/zeka/core/tenant.py`, `backend/zeka/legacy/{r_academy,docs,r_learning}.py`, `frontend/js/admin-settings.js`, `frontend/js/student.js`
**Estimated scope:** M

## Checkpoint B: Task 10–17 sonra

- [ ] Prod rejimində parolsuz yol yoxdur; rol × marşrut matrisi yaşıl
- [ ] 10 000 tələbə idxal olunur və aktivləşdirmə kodu ilə öz hesabına girir
- [ ] Rəy axını keçib; sahiblə baxış

---

## Phase 2 — Akademik nüvə

## Task 18: Korpus, otaq və otaq QR-i

**Description:** Cədvəllər: `buildings`, `floors`, `rooms` (kod, növ, tutum, əlçatanlıq). CSV idxalı. Otaq səhifəsi `/r/{kod}`: otağın adı, indiki və növbəti dərs. Hər korpus üçün çap olunan QR vərəqi (mövcud `qr.py`). `timetable.room` mətn sahəsi otağa bağlanır; uyğunlaşmayan sətirlər hesabatda.

**Acceptance criteria:**
- [ ] Hər otağın sabit QR ünvanı var; səhifə indiki və növbəti dərsi cədvəldən göstərir
- [ ] Girişsiz baxışda tələbə adı və ya şəxsi məlumat görünmür
- [ ] Mövcud cədvəl sətirləri otağa bağlanır və ya hesabatda sadalanır

**Verification:**
- [ ] `python -m pytest tests/integration/test_facilities.py -q`
- [ ] Əl yoxlaması: çap olunan QR telefonla oxunur və otaq səhifəsini açır

**Dependencies:** Task 16
**Files likely touched:** `backend/zeka/modules/facilities/{domain,service,repo,routes}.py`, `backend/migrations/0005_facilities.sql`, `frontend/js/facilities.js`
**Estimated scope:** M

## Task 19: Cədvəl idarəsi və iCal

**Description:** Tədris şöbəsi cədvəl sətirlərini yaradır və dəyişir: fənn, gün, saat, otaq, növ, həftə nümunəsi. Saxlananda otaq, müəllim və qrup toqquşması yoxlanır. Semestr üçün dərslər yaradılır, bayram günləri buraxılır. Dərsin ləğvi və ya köçürülməsi qeydiyyatdakılara bildiriş göndərir. İstifadəçi üzrə ləğv edilə bilən tokenli iCal lenti.

**Acceptance criteria:**
- [ ] Toqquşan sətir rədd olunur və toqquşmanın nə ilə olduğu yazılır
- [ ] Yaradılan dərslər həftə nümunəsinə uyğundur və bayramları buraxır
- [ ] iCal lenti RFC 5545 sahələrini və `TZID=Asia/Baku` daşıyır; dəyişiklikdən sonra yenilənir

**Verification:**
- [ ] `python -m pytest tests/unit/test_timetable_conflicts.py tests/integration/test_timetable.py -q`
- [ ] Əl yoxlaması: lent Google Calendar və Outlook-a əlavə olunur

**Dependencies:** Task 18
**Files likely touched:** `backend/zeka/modules/timetable/{domain,service,repo,routes}.py`, `frontend/js/timetable-admin.js`
**Estimated scope:** M

## Task 20: Davamiyyət jurnalı

**Description:** Müəllim bugünkü dərsi açır, siyahı susmaya görə "iştirak edir", istisnaları işarələyir. Saxlama idempotentdir. Düzəliş pəncərəsi (ayar, 48 saat) bitəndən sonra dəyişiklik kafedra müdirindən və səbəbdən keçir. Üzrlü qayıb axını qalır. Tələbə × fənn üzrə buraxılmış saat faizi və status: normal, xəbərdarlıq, imtahana buraxılmır.

**Acceptance criteria:**
- [ ] 30 nəfərlik dərs bir sorğu ilə qeyd olunur; eyni sorğunun təkrarı nəticəni dəyişmir
- [ ] Pəncərədən sonra müəllimin düzəlişi rədd olunur; kafedra müdirinin düzəlişi səbəblə yazılır
- [ ] Üzrlü qayıb sayılmır; hədd tenant ayarındandır; status tələbəyə, müəllimə və dekanlığa görünür

**Verification:**
- [ ] `python -m pytest tests/unit/test_attendance_rules.py tests/integration/test_attendance_journal.py -q`

**Dependencies:** Task 19, Task 17
**Files likely touched:** `backend/zeka/modules/journal/{domain,service,repo,routes}.py`, `frontend/js/journal.js`, `frontend/css/m-journal.css`
**Estimated scope:** M

## Task 21: Qiymət jurnalı

**Description:** Komponentlər dərc olunmuş sillabusdan və ya tenant sxemindən gəlir. Cədvəl şəklində daxiletmə, Excel-dən yapışdırma. Qaralama → dərc. Dərcdən sonrakı dəyişiklik səbəb tələb edir və jurnala düşür. Yekun bal, imtahan minimumu, hərf qiyməti. Tələbənin qiymət səhifəsi və transkript real məlumatdan oxuyur.

**Acceptance criteria:**
- [ ] Həddən kənar və rəqəm olmayan dəyər xana səviyyəsində tərcümə olunmuş mesajla rədd olunur
- [ ] Dərcdən sonrakı hər dəyişikliyin müəllifi, köhnə və yeni dəyəri, səbəbi qiymət jurnalındadır
- [ ] Yekun və hərf tenant sxeminə, imtahan minimumu daxil, uyğundur; tələbə yalnız dərc olunmuş balı görür

**Verification:**
- [ ] `python -m pytest tests/unit/test_grading_rules.py tests/integration/test_grade_journal.py -q`

**Dependencies:** Task 20
**Files likely touched:** `backend/zeka/modules/journal/{domain,service,repo,routes}.py`, `backend/migrations/0006_journal.sql`, `frontend/js/journal.js`, `backend/zeka/legacy/r_learning.py`
**Estimated scope:** M

## Task 22: Tapşırıqlar

**Description:** Müəllim tapşırıq yaradır: mətn, son tarix, maksimum bal, komponent, gecikmə qaydası. Tələbə fayl və ya mətn göndərir (mövcud fayl API-si). Müəllim rəy və bal yazır; bal jurnal komponentinə düşür.

**Acceptance criteria:**
- [ ] Son tarixdən sonrakı göndəriş qaydaya görə "gecikib" işarələnir və ya rədd olunur
- [ ] Yalnız fənnə yazılan tələbə göndərə bilir; göndərişi yalnız sahibi və fənnin müəllimi oxuyur
- [ ] Qiymətləndirilən bal jurnalda uyğun komponentdə görünür

**Verification:**
- [ ] `python -m pytest tests/integration/test_assignments.py -q`

**Dependencies:** Task 21
**Files likely touched:** `backend/zeka/modules/learning/assignments.py`, `backend/zeka/modules/learning/routes.py`, `backend/migrations/0007_assignments.sql`, `frontend/js/assignments.js`
**Estimated scope:** M

## Checkpoint C: Task 18–22 sonra

- [ ] Müəllim dərsdə davamiyyət və bal yazır; tələbə dərhal görür
- [ ] 25% həddi və imtahana buraxılış avtomatik hesablanır
- [ ] Rəy axını keçib; sahiblə baxış

---

## Phase 3 — Sillabus və imtahan

## Task 23: Struktur sillabus

**Description:** `syllabus_versions` cədvəli: versiya, status, doğrulanmış JSON. Sahələr: nəticələr (id, mətn, Bloom səviyyəsi), həftəlik plan (mövzu, nəticələr, fəaliyyət), qiymətləndirmə (komponent, çəki), qaydalar (davamiyyət, gecikmə, AI siyasəti), ədəbiyyat. Mövcud səhifə redaktora çevrilir; mövcud generator ilkin doldurma kimi qalır.

**Acceptance criteria:**
- [ ] Çəkilərin cəmi 100 deyilsə və ya imtahan çəkisi tenant qaydasına uyğun deyilsə saxlanmır
- [ ] Hər saxlama yeni qaralama versiyası yaradır; dərc olunmuş versiya dəyişdirilə bilmir
- [ ] Çap görünüşündə bütün dəyərlər escape olunur

**Verification:**
- [ ] `python -m pytest tests/unit/test_syllabus_validation.py tests/integration/test_syllabus.py -q`

**Dependencies:** Task 17
**Files likely touched:** `backend/zeka/modules/syllabus/{domain,service,repo,routes}.py`, `backend/migrations/0008_syllabus.sql`, `frontend/js/academy.js`
**Estimated scope:** M

## Task 24: Çərçivə xəritəsi və NICE idxalı

**Description:** `frameworks(key, version, title, source_url)` və `framework_items(framework_id, code, kind, parent, title)`. `manage.py import-framework --file`: NIST-in dərc etdiyi NICE Framework Components v2.2.0 JSON faylını oxuyur. Bloom və EQF daxili gəlir. Nəticə ↔ bənd xəritəsi üçün axtarışlı seçim. Əhatə hesabatı: iş rolu üzrə hansı bilik, bacarıq və tapşırıq bəyanatı hansı fənnin nəticəsi ilə örtülür; CSV ixracı.

**Acceptance criteria:**
- [ ] NICE idxalı idempotentdir və versiyanı saxlayır; yeni versiya idxal olunanda köhnə xəritələr oxunaqlı qalır
- [ ] Bir nəticə bir neçə çərçivənin bəndləri ilə işarələnə bilir
- [ ] Proqram üzrə əhatə hesabatı örtülməyən bəyanatları sadalayır

**Verification:**
- [ ] `python -m pytest tests/integration/test_frameworks.py -q`
- [ ] `python backend/manage.py import-framework --file content/frameworks/nice-components-2.2.0.json`

**Dependencies:** Task 23
**Files likely touched:** `backend/zeka/modules/syllabus/frameworks.py`, `backend/migrations/0008_syllabus.sql`, `content/frameworks/`, `frontend/js/academy.js`
**Estimated scope:** M

## Task 25: Təsdiq axını və fənnin konfiqurasiyası

**Description:** Statuslar: qaralama → təqdim olunub → kafedra təsdiqləyib → dərc olunub; hər addımda şərhlə geri qaytarma. Versiyalar arası fərq görünüşü. Dərc olunanda: jurnal komponentləri, fənnin davamiyyət həddi, AI siyasətinə görə tutor rejimi, imtahan planının ilkin dəyərləri təyin olunur. Tələbə fənn səhifəsində dərc olunmuş sillabusu görür.

**Acceptance criteria:**
- [ ] Zəncirdə yalnız növbəti rol statusu irəli apara bilir
- [ ] Dərc fənnin qiymət komponentlərini və tutor rejimini sillabusdakı kimi dəyişir
- [ ] Bal artıq yazılıbsa, dərc tədris şöbəsinin açıq, auditli icazəsi olmadan bloklanır; tələbə yalnız dərc olunmuş versiyanı görür

**Verification:**
- [ ] `python -m pytest tests/integration/test_syllabus_workflow.py -q`

**Dependencies:** Task 23, Task 21
**Files likely touched:** `backend/zeka/modules/syllabus/{service,routes}.py`, `backend/zeka/modules/journal/service.py`, `frontend/js/academy.js`, `frontend/js/student.js`
**Estimated scope:** M

## Task 26: İmtahan nüvəsi

**Description:** Cədvəllər: `exams` (pəncərə, müddət, plan, qoruma rejimi, şəbəkə siyahısı, status), `exam_forms` (tələbə üzrə sual və variant sırası, toxum), `exam_attempts`, `exam_answers`. `domain.py`: plana görə hovuzlardan variant qurulması (nəticə və çətinlik üzrə say), toxumla təkrarlanan qarışdırma, son vaxt, avtomatik təslim. Qiymətləndirmə imtahan bağlananda mövcud `engine.grade` ilə.

**Acceptance criteria:**
- [ ] İki tələbə fərqli sual və variant sırası alır; eyni tələbə həmişə eyni variantı alır
- [ ] `deadline_at`-dan sonrakı cavab server saatı ilə rədd olunur; iki dəfə başlatma eyni cəhdi qaytarır
- [ ] Nəticə açıqlanana qədər tələbəyə gedən heç bir imtahan cavabında `answer` və ya `explanation` yoxdur (bütün imtahan marşrutları üzrə sxem testi)

**Verification:**
- [ ] `python -m pytest tests/unit/test_exam_rules.py tests/integration/test_exam_core.py -q`

**Dependencies:** Task 13, Task 21
**Files likely touched:** `backend/zeka/modules/exam/{domain,service,repo,routes}.py`, `backend/migrations/0009_exam.sql`
**Estimated scope:** L (iki dilim: variant və cəhd dövrü)

## Task 27: İmtahan əhatəli sessiya və imtahan səhifəsi

**Description:** Tələbə imtahana girəndə sessiya `exam:{id}` əhatəsi alır. Router bu əhatəli sessiyaya yalnız `scope="exam"` marşrutlarını açır. `frontend/exam.html` və `js/exam.js`: naviqasiyasız səhifə; vəziyyətlər: yoxlanır, hazırdır, gedir, təslim olunub. Hər dəyişiklikdə və 20 saniyədən bir avtomatik saxlama; oflayn növbə və təkrar cəhd; yenidən yükləmədən sonra davam. Yeni giriş köhnə sessiyanı bağlayır.

**Acceptance criteria:**
- [ ] Avtomatik test imtahan əhatəli sessiya ilə bütün marşrut cədvəlini keçir: imtahandan kənar hər marşrut 403 qaytarır
- [ ] Oflayn yazılan cavablar bağlantı qayıdanda çatdırılır (şəbəkə söndürülən e2e test)
- [ ] İkinci giriş birincini bir sorğu ərzində bağlayır; ekrandakı taymer server son vaxtını keçmir

**Verification:**
- [ ] `python -m pytest tests/security/test_exam_scope.py -q`
- [ ] `npx playwright test tests/e2e/exam.spec.js --trace off`

**Dependencies:** Task 26
**Files likely touched:** `backend/zeka/core/web.py`, `backend/zeka/modules/exam/routes.py`, `frontend/exam.html`, `frontend/js/exam.js`, `frontend/css/m-exam.css`, `tests/security/test_exam_scope.py`
**Estimated scope:** M

## Task 28: SEB inteqrasiyası

**Description:** `modules/exam/seb.py`: `plistlib` ilə konfiqurasiya (`startURL`, `quitURL`, `hashedQuitPassword`, URL filtri, `sendBrowserExamKey`, `browserWindowWebView=3`, `allowVirtualMachine=false`, mübadilə buferi və ekran şəkli bağlı). Config Key: `originatorVersion` çıxarılır, boş lüğətlər silinir, açarlar böyük-kiçik hərfə baxmadan sıralanır, sıx JSON, SHA-256. `GET /exam/{id}/config.seb?k=`, `sebs://` keçidi. Yoxlama: başlıq (`X-SafeExamBrowser-ConfigKeyHash`) və JS API (`SafeExamBrowser.security.updateKeys`); server `sha256(fraqmentsiz URL + açar)` ilə sabit vaxtlı müqayisə edir; yoxlanan URL-də sessiya üzrə birdəfəlik dəyər var.

**Acceptance criteria:**
- [ ] Sahibin verdiyi nümunə `.seb` faylı üçün hesablanan Config Key SEB Config Tool-un göstərdiyi açarla eynidir
- [ ] `seb` rejimində səhv və ya olmayan hash ilə cəhd başlamır; bir sessiyada tutulan hash başqasında rədd olunur
- [ ] Yaradılan fayl Windows-da SEB 3.x ilə açılır və yalnız imtahanı göstərir (əl sınağı)

**Verification:**
- [ ] `python -m pytest tests/unit/test_seb_config_key.py tests/integration/test_seb_verify.py -q`
- [ ] Əl sınağı: SEB qurulmuş kompüterdə `sebs://` keçidi

**Dependencies:** Task 27
**Files likely touched:** `backend/zeka/modules/exam/seb.py`, `backend/zeka/modules/exam/routes.py`, `exam/template.plist`, `frontend/js/exam.js`, `frontend/js/teacher.js`, `tests/fixtures/reference.seb`
**Estimated scope:** M

## Task 29: Nəzarətçi paneli

**Description:** İmtahan üzrə `proctor` təyinatı. 5 saniyəlik sorğu ilə canlı lövhə: siyahı statusu, irəliləyiş, son görünmə, hadisələr (fokus itkisi, tam ekrandan çıxış, yenidən qoşulma, ünvan dəyişməsi). Səbəbi məcburi əməliyyatlar: vaxt əlavə et, dayandır, davam etdir, cəhdi bitir, yenidən aç. Girişdə şəbəkə siyahısı yoxlanır.

**Acceptance criteria:**
- [ ] `allowed_cidrs`-dən kənar ünvandan giriş rədd olunur və jurnala yazılır
- [ ] Hər nəzarətçi əməliyyatı səbəb tələb edir və imtahan jurnalında görünür
- [ ] Tələbənin vəziyyət dəyişməsi lövhədə 10 saniyə ərzində əks olunur

**Verification:**
- [ ] `python -m pytest tests/integration/test_proctor.py -q`

**Dependencies:** Task 27
**Files likely touched:** `backend/zeka/modules/exam/{service,routes}.py`, `frontend/js/proctor.js`, `frontend/css/m-exam.css`
**Estimated scope:** M

## Task 30: Hash zəncirli protokol və nəticənin jurnala keçməsi

**Description:** `exam_events` yalnız əlavə olunur: `hash = sha256(prev_hash + kanonik hadisə)`. `manage.py exam-verify <id>` zənciri yoxlayır. Bağlananda mövcud sənəd infrastrukturu ilə protokol: faktlar, saylar, insidentlər, zəncirin kökü, QR. Müəllim nəticəni açıqlayır; ballar jurnalın imtahan komponentinə yazılır. Sual statistikası və oxşar səhv cavab cütlərinin siyahısı müəllimə siqnal kimi verilir.

**Acceptance criteria:**
- [ ] Saxlanan hər hansı hadisənin dəyişdirilməsi və ya silinməsi `exam-verify`-ı yıxır və ilk qırıq halqanı göstərir
- [ ] Protokolun QR-i doğrulanır və eyni kökü göstərir
- [ ] Açıqlanan ballar jurnalda görünür, açıqlama auditdədir; oxşarlıq siyahısını yalnız müəllim görür

**Verification:**
- [ ] `python -m pytest tests/unit/test_exam_chain.py tests/integration/test_exam_release.py -q`
- [ ] `python backend/manage.py exam-verify 1`

**Dependencies:** Task 26, Task 29
**Files likely touched:** `backend/zeka/modules/exam/{domain,service,repo}.py`, `backend/zeka/legacy/docs.py`, `backend/manage.py`, `frontend/js/teacher.js`
**Estimated scope:** M

## Checkpoint D: Task 23–30 sonra

- [ ] 300 simulyasiya olunmuş tələbə ilə sınaq imtahanı: 0 itki, p95 < 500 ms
- [ ] Windows kompüterində SEB ilə əl sınağı (sahib)
- [ ] Rəy axını və `security-review` keçib; sahiblə baxış

---

## Phase 4 — Köməkçi, sual-cavab, icma, inteqrasiya

## Task 31: Kampus köməkçisi: otaq tapma və marşrut

**Description:** Marşrut qrafı: düyünlər (giriş, pilləkən, lift, dəhliz kəsişməsi, otaq qapısı), tillər (uzunluq, pilləsiz keçid). CSV idxalı. `facilities/domain.py`-də Dijkstra. Mətn addımları; mərtəbə planı şəkli verilibsə nişanla. Köməkçi niyyətləri: otaq kodu və ya adı, "növbəti dərsim hardadır", müəllimin otağı və qəbul saatı. QR-dən başlanğıc nöqtəsi (`/r/{kod}?to=`). Pilləsiz seçim.

**Acceptance criteria:**
- [ ] Pilot korpuslardakı istənilən iki otaq arasında marşrut qayıdır və ya hansı bağlantının çatışmadığı yazılır
- [ ] Pilləsiz marşrut heç vaxt pilləkəndən keçmir
- [ ] "Növbəti dərsim" cavabı cədvəllə eynidir; cavab 2 saniyədən tez gəlir

**Verification:**
- [ ] `python -m pytest tests/unit/test_routing.py tests/integration/test_assistant_rooms.py -q`

**Dependencies:** Task 18, Task 19
**Files likely touched:** `backend/zeka/modules/facilities/domain.py`, `backend/zeka/modules/assistant/{service,routes}.py`, `frontend/js/chat.js`, `frontend/js/facilities.js`
**Estimated scope:** M

## Task 32: Kampus köməkçisi: bilik bazası idarəsi və insana ötürmə

**Description:** Bilik bazası məqalələri bazaya keçir: versiya, mənbə (sənəd, bənd), əməliyyat keçidi, yenidən baxış tarixi; admin ekranı. Dəyişiklik indeks siqnalı verir. Mənbə tapılmayanda köməkçi dəstək sorğusu və ya müəllim sualı yaratmağı təklif edir, söhbət konteksti ilə. `tests/eval/assistant_az.jsonl`: 50 sual (qayda, xidmət, otaq, əhatədən kənar) və işlədici.

**Acceptance criteria:**
- [ ] Redaktə olunan məqalə növbəti sualda hər prosesdə istifadə olunur
- [ ] Hər cavab ya mənbə, ya insana ötürmə daşıyır; ikisi də olmayan cavab yoxdur
- [ ] Qiymətləndirmə dəstində ən azı 45/50 düzgün mənbə

**Verification:**
- [ ] `python -m pytest tests/integration/test_kb_admin.py -q`
- [ ] `python tools/eval_assistant.py tests/eval/assistant_az.jsonl`

**Dependencies:** Task 7, Task 31
**Files likely touched:** `backend/zeka/modules/assistant/{service,repo,routes}.py`, `backend/migrations/0010_kb.sql`, `frontend/js/admin-kb.js`, `tests/eval/assistant_az.jsonl`, `tools/eval_assistant.py`
**Estimated scope:** M

## Task 33: Müəllimə sual və fənn forumu

**Description:** Mövcud `teacher_questions` mövzulara çevrilir: fənn, müəllif, həmyaşıdlara anonimlik, başlıq, mətn, həftə və ya mövzu etiketi, status. Cavablar, müəllimin "təsdiqlənmiş cavab" işarəsi. Materiallardan AI qaralaması yalnız müəllimə görünür, təsdiqdən sonra dərc olunur. Cavablanmış sual fənn FAQ-ına keçə bilir və tutor indeksinə düşür. Şikayət və gizlətmə.

**Acceptance criteria:**
- [ ] Fənnin mövzularını yalnız ora yazılanlar və fənnin müəllimi oxuyur
- [ ] Anonim müəllifi tələbələr görmür; müəllim və moderator görür
- [ ] AI qaralaması təsdiqdən əvvəl tələbəyə göstərilmir; FAQ-a keçən cavaba tutor istinad edə bilir

**Verification:**
- [ ] `python -m pytest tests/integration/test_qa.py -q`

**Dependencies:** Task 13
**Files likely touched:** `backend/zeka/modules/qa/{domain,service,repo,routes}.py`, `backend/migrations/0011_qa.sql`, `frontend/js/qa.js`, `frontend/js/teacher.js`
**Estimated scope:** M

## Task 34: Qəbul saatları

**Description:** Müəllim həftəlik vaxt aralıqları təyin edir (otaq və ya onlayn keçid). Tələbə yer tutur və ləğv edir. Görüş hər iki tərəfin cədvəlində və iCal lentində görünür. Xatırlatma bildirişi.

**Acceptance criteria:**
- [ ] Bir aralıq iki dəfə tutula bilmir (paralel sorğu testi)
- [ ] Görüş hər iki iCal lentində görünür
- [ ] Ləğv qarşı tərəfə bildiriş göndərir

**Verification:**
- [ ] `python -m pytest tests/integration/test_office_hours.py -q`

**Dependencies:** Task 19, Task 33
**Files likely touched:** `backend/zeka/modules/qa/office_hours.py`, `backend/zeka/modules/qa/routes.py`, `frontend/js/qa.js`
**Estimated scope:** S

## Task 35: Klublar və kanallar

**Description:** Klub (ad, təsvir, rəhbər, dekanlığın təsdiqi), üzvlük sorğusu, kanallar, mesajlar (≤ 2 000 simvol), `GET .../messages?since_id=` ilə 3 saniyəlik sorğu, elan kanalı (yalnız rəhbər yazır), tədbirlər mövcud xəbər və qeydiyyat axını ilə. Moderasiya: şikayət → növbə; mesajı gizlət, üzvü müddətli sustur, kənarlaşdır. İlk yazıdan əvvəl davranış qaydalarının qəbulu. Saxlama müddəti (susmaya görə 180 gün) fon işi ilə. İstifadəçi üzrə limit.

**Acceptance criteria:**
- [ ] Üzv olmayan hər kanal marşrutunda 403 alır
- [ ] Şikayət olunan mesaj moderator növbəsinə düşür; hər moderasiya addımı auditdədir
- [ ] Susdurulan üzvün yazısı susdurmanın bitmə vaxtı ilə rədd olunur; müddəti keçən mesajları fon işi silir

**Verification:**
- [ ] `python -m pytest tests/integration/test_community.py tests/security/test_community_access.py -q`

**Dependencies:** Task 13, Task 36
**Files likely touched:** `backend/zeka/modules/community/{domain,service,repo,routes}.py`, `backend/migrations/0012_community.sql`, `frontend/js/community.js`, `frontend/css/m-community.css`
**Estimated scope:** L (iki dilim: üzvlük və mesaj; moderasiya)

## Task 36: E-poçt bildirişləri

**Description:** `core/jobs.py`: bazada iş cədvəli, icarə müddətli tək işçi dövrü nəzarətçi prosesdə. `outbox`: alıcı, şablon, parametrlər, dil, status, cəhd sayı, növbəti cəhd. `smtplib` və STARTTLS. Mövcud bildiriş növləri üçün üç dildə şablon. İstifadəçinin növ və kanal üzrə seçimi.

**Acceptance criteria:**
- [ ] SMTP kəsintisi mesajı gecikdirir, itirmir (saxta SMTP serveri ilə test; artan fasilə ilə təkrar cəhd)
- [ ] Növü bağlayan istifadəçi həmin növdən e-poçt almır
- [ ] Hər e-poçt alıcının dilindədir

**Verification:**
- [ ] `python -m pytest tests/integration/test_jobs.py tests/integration/test_email_outbox.py -q`

**Dependencies:** Task 7
**Files likely touched:** `backend/zeka/core/jobs.py`, `backend/zeka/modules/comms/{service,repo,routes}.py`, `backend/migrations/0013_comms.sql`, `content/email-templates/`
**Estimated scope:** M

## Task 37: İnteqrasiya mərkəzi

**Description:** Əhatəli API açarları (hash ilə saxlanır, açar üzrə limit, audit). İmzalı webhook-lar (HMAC-SHA256, təkrar cəhd): `grade.published`, `attendance.barred`, `exam.released`. İxraclar: OneRoster CSV arxivi, qiymətlər CSV, sütunları tənzimlənən reyestr ixracı. "Tətbiqlər" səhifəsi: adminin rola görə qurduğu, qalan xarici sistemlərə aparan kafellər. `docs/API.md` yenilənir.

**Acceptance criteria:**
- [ ] Açar yalnız öz əhatəsindəki marşrutları çağıra bilir
- [ ] Webhook çatdırılması imzalanır, təkrar cəhd olunur və jurnala yazılır
- [ ] OneRoster ixracı boş nüsxəyə idxal olunanda eyni reyestri verir (dövrə testi)

**Verification:**
- [ ] `python -m pytest tests/integration/test_api_tokens.py tests/integration/test_webhooks.py tests/integration/test_oneroster_roundtrip.py -q`

**Dependencies:** Task 16, Task 36
**Files likely touched:** `backend/zeka/modules/integration/{tokens,webhooks,export,routes}.py`, `backend/migrations/0014_integration.sql`, `frontend/js/apps.js`, `docs/API.md`
**Estimated scope:** L (üç dilim: açar, webhook, ixrac və kafel)

## Checkpoint E: Task 31–37 sonra

- [ ] 50 suallıq dəstdə mənbə düzgünlüyü ≥ 90%
- [ ] Hər yeni modul təhlükəsizlik matrisindədir
- [ ] Rəy axını keçib; sahiblə baxış

---

## Phase 5 — Miqrasiya, sərtləşdirmə, buraxılış

## Task 38: ETL və uzlaşdırma

**Description:** `tools/etl/`: mənbə faylı növü üzrə adapter, sütun xəritəsi `content/mappings/<mənbə>.json`-da, çevirmələr (ad normallaşdırma, qrup kodu, qiymət şkalası). Yükləmə Task 16-dakı idxal servisindən keçir. `manage.py reconcile --wave N`: varlıq üzrə say, açar sahələrin yoxlama cəmi, əl yoxlaması üçün 50 təsadüfi qeyd, fərq hesabatı. Kəşf birinci saatdan başlayır: köhnə sistemlərin ixrac formatı.

**Acceptance criteria:**
- [ ] Verilən ixraclar üzərində quru sınaq izahsız sətir qalmayan xəritə və doğrulama hesabatı verir
- [ ] İdxaldan sonra uzlaşdırma hər varlıq üçün bərabər say göstərir
- [ ] Təkrar işlətmə dublikat yaratmır

**Verification:**
- [ ] `python -m pytest tests/migration/test_etl.py -q`
- [ ] `python backend/manage.py reconcile --wave 0`

**Dependencies:** Task 16, Task 21
**Files likely touched:** `tools/etl/{adapters,transforms,run}.py`, `content/mappings/`, `backend/manage.py`, `tests/migration/test_etl.py`
**Estimated scope:** M

## Task 39: Ölçülmüş göstəricilər və akkreditasiya sübutu

**Description:** `events` cədvəli (kim, nə, nə vaxt, modul) nüvə qarmağı ilə yazılır. Göstəricilər hesablanır: rol üzrə həftəlik aktiv istifadəçi, jurnalın doldurulma faizi, müraciətin icra müddəti və SLA, mənbəli cavab payı, imtahan sayı. `r_admin.py` və `staff.js`-dəki sabit rəqəmlər çıxarılır. Akkreditasiya səhifəsi: 3.5.1, 3.5.3, 5.4.2–5.4.8 göstəriciləri üzrə canlı say və keçidlər; ixrac.

**Acceptance criteria:**
- [ ] Heç bir panel kafeli sabit rəqəmdən qidalanmır (test analitika modulunu yoxlayır və hər kafelin sorğusu olduğunu təsdiqləyir)
- [ ] Hər kafel öz tərifini və zaman aralığını göstərir
- [ ] Sübut səhifəsi ixrac olunur

**Verification:**
- [ ] `python -m pytest tests/integration/test_insight.py -q`

**Dependencies:** Task 21, Task 30
**Files likely touched:** `backend/zeka/core/events.py`, `backend/zeka/modules/insight/{service,repo,routes}.py`, `backend/zeka/legacy/r_admin.py`, `frontend/js/staff.js`
**Estimated scope:** M

## Task 40: Məxfilik: razılıq, saxlama, ixrac, silmə

**Description:** Məqsəd üzrə razılıq qeydi: mətnin versiyası, vaxt, üsul. Saxlama işi: söhbət, icma, jurnallar tenant ayarına görə. `GET /api/me/export`: istifadəçinin öz məlumatı. Silmə sorğusu axını; qanunla saxlanmalı akademik qeydlər anonimləşdirilir. Məxfilik bildirişi üç dildə. `docs/privacy/data-inventory.md`: cədvəl × məqsəd × müddət × hüquqi əsas; maddə 15 qeydiyyatı üçün əsas.

**Acceptance criteria:**
- [ ] İxrac istifadəçiyə bağlı hər cədvəl sətrini ehtiva edir (test istifadəçi açarı olan cədvəlləri sadalayır)
- [ ] Silmə inventara uyğun silir və ya anonimləşdirir və auditdədir
- [ ] Xarici AI yalnız cari mətn versiyası üçün yazılmış razılıqla çağırılır

**Verification:**
- [ ] `python -m pytest tests/integration/test_privacy.py -q`

**Dependencies:** Task 36
**Files likely touched:** `backend/zeka/modules/identity/privacy.py`, `backend/zeka/core/jobs.py`, `docs/privacy/data-inventory.md`, `frontend/js/main.js`
**Estimated scope:** M

## Task 41: Təhlükəsizlik baxışı və NIST nəzarət matrisi

**Description:** Bütün fərq üzərində rəy axını və `security-review` skili. `docs/security/nist-csf-profile.md`: CSF 2.0 funksiyası → nəzarət → SP 800-53 Rev. 5.2.0 id-si → sübut (fayl və ya test) → status. `docs/security/hecvat-lite.md`. İmtahan və kimlik üçün təhdid modeli (STRIDE cədvəli). `/.well-known/security.txt`.

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

**Description:** Playwright tüstü testi: rollar × 3 dil × masaüstü və mobil. İmtahanın oflayn daxil e2e testi. 10 əsas səhifədə axe-core (WCAG 2.2 AA). Yük: imtahan 500 istifadəçi 30 dəqiqə, gündəlik qarışıq 1 000 istifadəçi. Xaos: imtahan ortasında `kill -9`, məşğul baza, SMTP kəsintisi. Nəticələr `docs/perf/`-də.

**Acceptance criteria:**
- [ ] E2E dəsti CI-da yaşıldır; axe 10 səhifədə ciddi və kritik pozuntu tapmır
- [ ] İmtahan yükü: p95 < 500 ms, itən cavab 0 (server sayı = müştəri sayı)
- [ ] `kill -9`-dan sonra hər cəhd saxlanmış bütün cavablarla davam edir

**Verification:**
- [ ] `npx playwright test --trace off`
- [ ] `python tools/loadtest.py --scenario exam --users 500 --seconds 1800`

**Dependencies:** Task 30, Task 35
**Files likely touched:** `tests/e2e/*.spec.js`, `tools/loadtest.py`, `docs/perf/`, `.github/workflows/ci.yml`
**Estimated scope:** M

## Task 43: Runbook-lar

**Description:** `docs/runbooks/`: yerləşdirmə və geri qaytarma; backup və bərpa; imtahan günü (24 saat əvvəl yoxlama, gediş, insident, kağız ehtiyat); insident cavabı; fakültənin qoşulması (idxal → uzlaşdırma → təlim); dalğa üzrə kəsid siyahısı.

**Acceptance criteria:**
- [ ] Hər runbook hədəf və ya sınaq serverində bir dəfə icra olunub, çıxışı əlavə edilib
- [ ] Bərpanın müddəti ölçülüb və yazılıb
- [ ] İmtahan günü runbook-u sınaq imtahanında istifadə olunub

**Verification:**
- [ ] Əl yoxlaması: başqa adam yalnız runbook ilə bərpanı icra edir

**Dependencies:** Task 9, Task 8
**Files likely touched:** `docs/runbooks/*.md`
**Estimated scope:** S

## Task 44: Buraxılış

**Description:** Hədəf serverə yerləşdirmə, ilk administrator, dalğa 0 məlumatının idxalı, uzlaşdırma, hər rol üçün tüstü yoxlaması, backup cədvəli, izləmə (sağlamlıq, disk, backup yaşı), SPEC-in Success Criteria siyahısı üzrə keç və ya keçmə baxışı, `v1.0.0` teqi.

**Acceptance criteria:**
- [ ] Keç və ya keçmə siyahısı sahib tərəfindən təsdiqlənib
- [ ] Uzlaşdırma fərqi 0; canlı nüsxənin backup-ı ikinci maşında bərpa olunub
- [ ] Pilot istifadəçilərin ilk real girişləri uğurludur

**Verification:**
- [ ] `python backend/manage.py reconcile --wave 0`
- [ ] `infra/restore.sh` ikinci maşında

**Dependencies:** Task 38, Task 41, Task 42, Task 43
**Files likely touched:** `infra/.env` (serverdə), `docs/runbooks/release-v1.md`
**Estimated scope:** S

## Checkpoint F: buraxılış qapısı

- [ ] SPEC-dəki bütün Success Criteria təsdiqlənib və ya istisna yazılı qeyd olunub
- [ ] Hədəf serverdə bərpa sınağı keçib; ilk fakültənin uzlaşdırma fərqi 0
- [ ] Açıq yüksək səviyyəli təhlükəsizlik tapıntısı yoxdur
- [ ] Sahibin yazılı buraxılış qərarı
