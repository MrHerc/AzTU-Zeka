# Implementation Plan: Zəka V1 — AzTU-nun mövcud sistemlərinin əvəzlənməsi

Source spec: `SPEC.md` · Tapşırıqlar: `tasks/todo.md` · Vəziyyət: **təsdiq gözləyir** · Tarix: 2026-11-16

## Overview

72 saatda Zəka demodan işləyən məhsula çevrilir: real hesablar, itməyən məlumat, müəllimin yazdığı jurnal,
icra olunan sillabus, SEB ilə imtahan, otaq tapan köməkçi, müəllimə sual, klublar, idxal və kəsid alətləri.
Bir fakültə 72-ci saatda real məlumatla işə başlayır. Qalan fakültələr eyni alətlərlə dalğa-dalğa keçir.

İş 6 mərhələ, 46 tapşırıqdır (T01–T46; T45 Faza 3-də, T46 Faza 5-dədir). Fazalar 1–6 nömrələnir; Faza 1 bünövrədir. Hər tapşırıq bir şaquli dilimdir: sxem, servis, marşrut, interfeys, test.
Hər mərhələ yoxlama nöqtəsi ilə bağlanır. Nöqtə keçilməsə növbəti mərhələ başlamır.

## Architecture Decisions

| # | Qərar | Əsas | Yenidən baxma şərti |
|---|---|---|---|
| A1 | Beş PR əvvəlcə birləşdirilir, sonra restruktur gedir. | Restruktur açıq PR-larla toqquşardı. Birləşdirmə tamamlanıb: commit `9d23e99`, 698 test yaşıl. | — |
| A2 | Repo dilə və qata görə bölünür: `backend/`, `frontend/`, `infra/`, `exam/`. Modulun içində `domain / service / repo / routes`. | Sahibin tələbi. Modul daxilində qat bölgüsü köhnə kodu tədricən köçürməyə imkan verir. | — |
| A3 | Köhnə `r_*.py` faylları `legacy/`-yə köçürülür, davranışı dəyişmir. Yeni modullar birbaşa qatlı yazılır. | Böyük partlayışla yenidən yazmaq 639 testi və 5 PR-ın düzəlişlərini riskə atır. | Modul toxunulanda qatlara bölünür. |
| A4 | HTTP qatı qalır, qabağına Caddy qoyulur. Tətbiqin portu kənara açılmır; müştəri ünvanı yalnız Caddy-nin yazdığı `X-Forwarded-For`-dan oxunur (`ZEKA_PROXY_HOPS=1`). | PR #3 və #5 protokol səhvlərini bağlayıb. Caddy TLS və HTTP normallaşdırmanı götürür. | Yük testi tələb edərsə ASGI. |
| A5 | Proses başına eyni anda 2 handler; nüvə başına bir proses (`SO_REUSEPORT`); xarici çağırışlar ayrıca həddə (`ZEKA_SLOW`). | Ölçülüb (demo baza, tək marşrut): məhdudiyyətsiz 47 sorğu/san və 300 müştəridə 150 xəta; 2 handler ilə 226 sorğu/san və 0 xəta. | — |
| A6 | Proses-lokal vəziyyət bazaya köçürülür: birdəfəlik açarlar, limit sayğacları. Axtarış indeksi hər prosesdə qurulur, dəyişiklik siqnalı ilə yenilənir. | Çox proses üçün şərtdir. | İşçi başlanğıcı və ya indeks yaddaşı T07-də ölçülən həddi keçərsə: SQLite FTS5. |
| A7 | SQLite WAL qalır, miqrasiya mühərriki əlavə olunur. SQL yalnız `repo.py`-də. | Bir fakültə üçün fərziyyədir, yük testi təsdiqləyir (T07, T42, T44); quraşdırma tək konteynerdir. | `university` yük testi (T42, T44) hədəf serverdə p95 < 500 ms-i tutmursa: Postgres tapşırığı dalğa 1-dən əvvəl. |
| A8 | Parol hash-i `hashlib.scrypt`; konfiqurasiya ilə PBKDF2-HMAC-SHA-256. | Standart kitabxanadadır, yaddaş-ağırdır. PBKDF2 NIST-in təsdiqlədiyi yeganə sxemdir, tələb olunsa keçid bir ayardır. | — |
| A9 | SSO ümumi OIDC müştərisidir (code + PKCE). ID token imzası yoxlanmır, token son nöqtəsinə birbaşa TLS bağlantısına güvənilir. | OIDC Core 3.1.3.7 bənd 6 kod axınında buna icazə verir; həmin bölmənin qalan yoxlamaları (`iss`, `aud`, `exp`, `nonce`) və 5.3.2 tətbiq olunur. JWKS eyni TLS ilə gəldiyi üçün imza yoxlaması əlavə etibar lövbəri vermir. Hesab (`iss`, `sub`) ilə bağlanır. | AzTU SSO-su SAML-dırsa `cryptography` icazəsi. FAL iddiası tələb olunsa və ya token ön kanaldan gəlsə: JWKS ilə RS256 yoxlaması (stdlib ilə, asılılıqsız). |
| A10 | İmtahanın əsl qoruması serverdədir: imtahan əhatəli sessiya, server taymeri, tək sessiya, şəbəkə siyahısı. SEB əlavə qatdır. | SEB Config Key yalnız konfiqurasiyanı bildiyini sübut edir; `.seb` faylı olan onu saxtalaşdıra bilər. | — |
| A11 | İmtahan hadisələri, hər təslimin cavab hash-i və hər bal hash zənciri ilə yazılır; kök QR-lı protokola düşür və e-poçtla bazadan kənara göndərilir. | Sonradan dəyişdirilmə aşkar olunur: zəncir bazada yenidən hesablansa belə kök kənardakı nüsxə ilə üst-üstə düşmür. Mövcud QR sənəd infrastrukturu təkrar istifadə olunur. | Rəddedilməzlik tələb olunsa: SİMA/ASAN İmza (Out of Scope). |
| A12 | Sillabus fənnin konfiqurasiyasıdır: dərc olunan versiya jurnal komponentlərini, davamiyyət həddini, tutor rejimini və imtahan planını təyin edir. Davamiyyət həddini yalnız aşağı sala bilər (≤ tenant həddi). | Bir həqiqət mənbəyi; akkreditasiya üçün nəticə → sual → nəticə zənciri. | — |
| A13 | Çərçivələr CASE modelinə bənzər cədvəldə saxlanır: çərçivə, versiya, bənd id, valideyn. | NICE, Bloom, EQF, ABET eyni mexanizmlə işləyir; versiya dəyişəndə köhnə xəritə qalır. | — |
| A14 | Klub mesajları 3 saniyəlik sorğu ilə gəlir (`since_id`). | WebSocket yeni infrastruktur tələb edir; klub söhbəti üçün 3 saniyə kifayətdir. | Gecikmə şikayəti: SSE. |
| A15 | Bildirişlər baza növbəsindən gedir; fon işi `smtplib` ilə göndərir və təkrar cəhd edir. | Xarici növbə sistemi lazım deyil. | — |
| A16 | Otaq marşrutu qraf üzərində Dijkstra-dır: düyünlər giriş, pilləkən, lift, otaq. Yerləşmə QR lövbərlərlə. | Bina daxilində GPS işləmir; mayak avadanlığı lazım olmur. | — |
| A17 | AI susmaya görə oflayn mühərrikdir. Hər cavab mənbə göstərir, yoxdursa insana ötürür. | Maddə 14. Qoruyucusuz AI tutor qiyməti aşağı salır (2026 sınağı). | LLM seçimi: Open Questions 6. |
| A18 | Kamera, səs, üz ilə proktorinq yoxdur. | Maddə 9.5 biometrikadır. AzTU-da imtahanlar onsuz da video ilə yazılır. | — |
| A19 | Vaxt bir mənbədən gəlir: `core/clock.py`. Proses saat qurşağından asılı deyil; qurşaq `ZEKA_TZ`-dir (susmaya görə `Asia/Baku`). Yeni cədvəllər anı UTC-də, ofsetlə saxlayır (`2026-12-01T06:00:00+00:00`; `Z` yox: CI testləri Python 3.10-da da işlədir, o isə `Z`-ni oxumur). Divar saatı qaydaları (bugün, həftə günü, `HH:MM`, insanın daxil etdiyi pəncərə və son tarix) `clock.local()` ilə hesablanır. Legacy sütunlar Asia/Baku lokal qalır və bu, `0001_baseline.sql`-də yazılır. Legacy və yeni vaxt sütunu SQL-də müqayisə olunmur. Sahib bunu T10-dan əvvəl təsdiqləyir; ucuz variant SPEC Open Questions 22-dədir və seçilən variant bu sətirdə yazılır. | Konteyner UTC-dədir, qaydalar Bakı vaxtı ilədir (AUDIT R-04, CODEMAP L17). Hash zəncirli hadisə sonradan düzəldilə bilmir. | Yay vaxtı olan qurşaqda tenant və ya Postgres mərhələsi: legacy sütunlar da çevrilir. |

## Dependency Graph

```
platform ── identity ── directory ──┬── facilities ──┐
                                    │                ├── timetable ── journal ──┬── radar
                                    │                │                          ├── services (qiymətə əsaslanan sənəd; T45: sənədin verilmə yolu) ── exam (protokol)
                                    │                │                          └── exam (buraxılış siyahısı, nəticənin jurnala yazılması)
                                    ├── syllabus ────┼── learning ── exam
                                    │                │
                                    ├── qa           └── assistant
                                    ├── community
                                    ├── comms (T36: e-poçt növbəsi) ── exam (zəncir kökünün göndərilməsi)
                                    └── integration, migration        insight ← hamısı
```

Kritik yol (`tasks/todo.md` asılılıqlarından ən uzun zəncir, 19 tapşırıq):
T02→T03→T04→T05→T10→T11→T13/1→T15/1→T17→T19→T20→T21→T26→T27→T29→T30→T42→T43→T44.
T15/2 (tədris vahidi) T17 ilə paralel gedir və T19-dan əvvəl bitməlidir.
`facilities` (T18, T31), idxal (T16), `syllabus`, `qa`, `community`, `comms`, T13/2, T45, T46 bu zəncirdən kənardır və paralel gedir.
T36 Faza 5-in siyahısındadır, amma zolaq 3-də saat 22–36-da qurulur: dilim 1 (iş icraçısı və dövri işlər) T26-dan, dilim 2 (outbox və e-poçt) T30-dan əvvəl bitməlidir. T45 də zəncirdə deyil və T30-dan əvvəl bitməlidir.

## Task List

Tam mətn, qəbul meyarları və yoxlama addımları `tasks/todo.md`-dədir.

### Faza 1 — Birləşdirmə və bünövrə · saat 0–10

- [x] T01 Beş PR-ı birləşdir — 698 test yaşıl, commit `9d23e99`
- [x] T02 Sətir sonlarını sabitlə — `cfe023a`
- [x] T03 Repo-nu dilə və qata görə böl — `2d7455b`, `93f28dd`
- [x] T04 Miqrasiya mühərriki — `b85ab5e`
- [x] T05 İş rejimləri: demo və prod — `af5259e`, `c96880e`
- [x] T06 Handler qapısı və çox proses — `b2ecc6f`, `83eeebb`
- [x] T07 Proses-lokal vəziyyəti bazaya köçür — `95a348c` və dilim 2 (indekslər, ölçmə)
- [x] T08 Backup və bərpa — `backend/zeka/core/backup.py`, `docs/runbooks/backup.md`
- [x] T09 Yerləşdirmə: Docker, Caddy, sağlamlıq yoxlaması — `docs/runbooks/deploy.md`

### Checkpoint A · saat 10
- [ ] Bütün testlər yaşıl; `docker compose up` ilə HTTPS açılır; yenidən başlatma məlumatı saxlayır
- [ ] 300 paralel müştəridə 0 xəta (`demo` və `faculty` dəstləri); bərpa sınağı keçir

### Faza 2 — Kimlik və reyestr · saat 10–22

- [x] T10 Hesablar və parol — `backend/zeka/modules/identity/`
- [ ] T11 Sessiya sərtləşdirməsi
- [ ] T12 İşçi rolları üçün TOTP
- [ ] T13 Rol və icazə modeli
- [ ] T14 SSO: ümumi OIDC müştərisi
- [ ] T15 Struktur və reyestr idarəsi
- [ ] T16 Kütləvi idxal
- [ ] T17 Tenant ayarları

### Checkpoint B · saat 22
- [ ] Prod rejimində parolsuz yol yoxdur; rol × marşrut matrisi yaşıl
- [ ] 10 000 tələbə idxal olunur və aktivləşdirmə kodu ilə öz hesabına girir
- [ ] Sınaq nüsxəsi sabit adla açılır: `curl https://<ad>/healthz` (`-k` olmadan) sahibin SEB kompüterindən 200 qaytarır; sintetik məlumatla işləyir; hər yoxlama nöqtəsində push-dan sonra `docs/runbooks/deploy.md` ilə yenilənir. Ad saat 22-yə hazır deyilsə: T18, T19, T28-in əl yoxlamaları LAN-da http ilə (`seb://`) aparılır, `sebs://` sınağı və Google Calendar abunəliyi T44-ün meyarına yazılır
- [ ] Sahib rol cədvəlini və `qa.moderate`, `community.moderate` bölgüsünü təsdiqləyib (T13; SPEC Open Questions 24)

### Faza 3 — Akademik nüvə · saat 22–36

- [ ] T18 Korpus, otaq və otaq QR-i
- [ ] T19 Cədvəl idarəsi və iCal
- [ ] T20 Davamiyyət jurnalı
- [ ] T21 Qiymət jurnalı
- [ ] T22 Tapşırıqlar və material faylı
- [ ] T45 Sənədin bütövlüyü

### Checkpoint C · saat 36
- [ ] Müəllim dərsdə davamiyyət və bal yazır; tələbə dərhal görür
- [ ] 25% həddi və imtahana buraxılış avtomatik hesablanır
- [ ] Verilmiş sənəd saxlanmış yükdən göstərilir; bazada dəyişdirilən yük `/verify`-da "sənəd dəyişdirilib" verir

### Faza 4 — Sillabus və imtahan · saat 36–52

- [ ] T23 Struktur sillabus
- [ ] T24 Çərçivə xəritəsi və NICE idxalı
- [ ] T25 Təsdiq axını və fənnin konfiqurasiyası
- [ ] T26 İmtahan nüvəsi
- [ ] T27 İmtahan əhatəli sessiya və imtahan səhifəsi
- [ ] T28 SEB inteqrasiyası
- [ ] T29 Nəzarətçi paneli
- [ ] T30 Hash zəncirli protokol və nəticənin jurnala keçməsi

### Checkpoint D · saat 52
- [ ] 300 simulyasiya olunmuş tələbə ilə sınaq imtahanı: `python tools/loadtest.py --scenario exam --users 300 --seconds 300 --dataset faculty` 0 itki və p95 < 500 ms verir. Əmr T27-də yazılır və T30-dan sonra yenidən işlədilir (hash zənciri və nəzarətçi sorğusu yükə əlavə olunur)
- [ ] Windows kompüterində SEB ilə əl sınağı (sahib)

### Faza 5 — Köməkçi, sual-cavab, icma, inteqrasiya · saat 52–62

- [ ] T31 Kampus köməkçisi: otaq tapma və marşrut
- [ ] T32 Kampus köməkçisi: bilik bazası idarəsi və insana ötürmə
- [ ] T33 Müəllimə sual və fənn forumu
- [ ] T34 Qəbul saatları
- [ ] T35 Klublar və kanallar
- [ ] T36 E-poçt bildirişləri və dövri işlər — saat 22–36-da qurulur (zolaq 3); T26 və T30 ondan asılıdır
- [ ] T37 İnteqrasiya mərkəzi
- [ ] T46 E-xidmətlərin dürüstlüyü

### Checkpoint E · saat 62
- [ ] 50 suallıq dəstdə mənbə düzgünlüyü ≥ 90%
- [ ] Hər yeni modul təhlükəsizlik matrisindədir
- [ ] Prod rejimində yalnız adminin açdığı müraciət növləri təklif olunur; `python backend/manage.py jobs status` beş dövri işin hər biri üçün son uğurlu icranı göstərir

### Faza 6 — Miqrasiya, sərtləşdirmə, buraxılış · saat 62–72

- [ ] T38 ETL və uzlaşdırma
- [ ] T39 Ölçülmüş göstəricilər və akkreditasiya sübutu
- [ ] T40 Məxfilik: razılıq, saxlama, ixrac, silmə
- [ ] T41 Təhlükəsizlik baxışı və NIST nəzarət matrisi
- [ ] T42 E2E, əlçatanlıq və yük testi
- [ ] T43 Runbook-lar
- [ ] T44 Buraxılış

### Checkpoint F · saat 72 — buraxılış qapısı
- [ ] SPEC-dəki bütün Success Criteria təsdiqlənib və ya istisna yazılı qeyd olunub
- [ ] Hədəf serverdə bərpa sınağı və `university` yük testi keçib; ilk fakültənin T0 ixracına qarşı uzlaşdırma fərqi 0 və ya izahlı; T0 release runbook-da yazılıb

## Paralel zolaqlar

Kritik yol ardıcıl gedir. Qalan iş ayrı iş qovluqlarında (worktree) paralel aparılır və növbə ilə birləşdirilir.

| Saat | Zolaq 1 (kritik yol) | Zolaq 2 | Zolaq 3 | Sahib |
|---|---|---|---|---|
| 0–10 | T02–T07 (T01 tamamlanıb) | T08, T09 | T38 kəşf: köhnə ixrac formatları | Hostinq, server girişi, sınaq nüsxəsinin DNS adı |
| 10–22 | T10, T11, T13/1, T15/1, T17 | T15/2, T16 (T15/1-dən sonra) | T12, T14 (T11-dən sonra); T13/2 (T15/1-dən sonra) | Köhnə sistemlərdən ilk ixraclar; fakültə seçimi |
| 22–36 | T19–T21 | T18, sonra T22 (T21-dən sonra) | T36, T45; T38 dilim 1 (T21-dən sonra) | Otaq siyahısı, korpus girişləri, mərtəbə planları; SMTP məlumatı |
| 36–52 | T26–T30 | T23–T25 | T33, T34 | SEB qurulmuş 2 kompüter; SEB Config Tool-da "Use SEB settings file for: starting an exam" seçimi ilə, parol və sertifikat seçilmədən, şifrələnməmiş saxlanmış bir `.seb` faylı və alətin göstərdiyi Config Key; `www.nist.gov` və `csrc.nist.gov` üçün şəbəkə icazəsi və ya NICE Framework Components v2.2.0 JSON faylı |
| 52–62 | T31, T32, T46 | T35, T37 | T39, T40 | Bilik bazası mətnləri: qaydalar, əsasnamələr |
| 62–72 | T41, T42 | T38 dilim 2 və dalğa 0 idxalı, T43 (T42-dən sonra) | — | Sınaq istifadəçiləri; buraxılış qərarı |

T44 zolaq deyil: T38, T41, T42, T43 bitəndən sonra son addımdır.
Zolaq daxilində tapşırıq `tasks/todo.md`-dəki asılılığı bağlananda başlayır.
Zolaq 2 və 3 sonrakı mərhələnin siyahısındakı tapşırığı əvvəl başladır (T36, T33, T34, T39, T40). Yoxlama nöqtəsi keçilməyəndə kritik yolun növbəti tapşırığı başlamır.

## Miqrasiya və kəsid

Prinsip: heç bir dalğa imtahan sessiyasının ortasında bağlanmır. Hər dalğada köhnə sistem oxunaqlı qalır.

| Dalğa | Vaxt | Zəka-ya keçən | Köhnə sistem | Bağlanma şərti |
|---|---|---|---|---|
| 0 | 72 saat | Bir fakültə: giriş, cədvəl, otaq, davamiyyət (kəsid tarixinə qədər idxal olunmuş qayıblar: dərs səviyyəli sətir və ya açılış qalığı + həmin tarixdən sonra Zəka-da yazılan), cari ballar (komponent üzrə idxal), sillabus, köməkçi, sual-cavab, klub | Əsas mənbə və hüquqi qeyd qalır: imtahana buraxılış statusu bu dalğada köhnə sistemdən götürülür; Zəka statusu qalığın tarixi ilə göstərir. Pilot fakültənin müəllimi kəsid tarixindən davamiyyəti və balı hər iki sistemə yazır; gündəlik fərq hesabatı köhnə sistemin ixracını Zəka ilə müqayisə edir (A variantı; "Qeydin sahibi" cədvəli). Sahib B variantını seçsə (SPEC Open Questions 19), bu xana "T0-dan davamiyyət və bal yalnız Zəka-ya yazılır; köhnə sistemə daxiletmə dekan əmri ilə dayanır" olur | T0 ixracına qarşı uzlaşdırma fərqi 0 və ya sətir-sətir izahlı; 300 nəfərlik sınaq imtahanı; paralel dövrdə köhnə sistemdə verilən hər status əmri təkrar idxaldan (T38, `status-events` növü) sonra Zəka-dadır; `university` yük testi hədəf serverdə keçib, keçməyibsə Postgres tapşırığı dalğa 1-dən əvvəl planlaşdırılıb |
| 1 | 2–4 həftə | Bütün fakültələr: jurnal, cədvəl, tapşırıq; SSO | Paralel iş zamanı yazılır, gecəlik müqayisə; kəsiddən (T1) sonra jurnal, cədvəl və tapşırıq modulları yalnız oxunur. "Yalnız oxunur" rejiminə keçid iki şərtdən sonradır: ən azı bir real status əmri Zəka-da daxil edilib (eyni əmr köhnə sistemdə də yazılır: T1-ə qədər sahib odur); "Tələbə-məzun" operatoru dəyişiklik siyahısından (T37) istifadə edib | Mənbə ilə bağlı sətirlərdə 14 ardıcıl gecə fərq 0 və ya izahlı; kəsiddən sonra köhnə sistemdə T1-dən sonra yazı 0; dəstək sorğuları sabitləşib |
| 2 | Qış sessiyası | İmtahanlar SEB ilə; protokollar; apellyasiya; e-xidmətlər (transkript və keçmiş semestr qiymətinə əsaslanan sənədlər istisna: dalğa 3-də, tarixi qiymətlər köçürüləndən sonra açılır) | İmtahan nəticələri ehtiyat kimi köhnə sistemin imtahan moduluna da yazılır (kim yazır: sahibin qərarı, SPEC Open Questions 19); qalan modullar yalnız oxunur | Hər imtahanın protokolu və zəncir kökü var |
| 3 | Yaz semestrinin əvvəli | Zəka əsas sistemdir; tədris planı və fənn qeydiyyatı modulu (sprintdən sonrakı tapşırıq); tarixi məlumat köçürülür; dövlət sistemlərinə ixrac | Arxiv | Rektorluğun yazılı qəbulu; arxivin bərpa sınağı; yaz semestrinin qeydiyyatı (qrup × fənn, seçmələr, təkrar fənlər) köhnə sistemdən ixrac, idxal və uzlaşdırma ilə Zəka-dadır; qeydiyyat modulu Zəka-da qəbul olunana qədər köhnə Academic modulu arxivlənmir |

T0: dalğa 0-ın idxal olunduğu ixracın anı. T1: dalğa 1-in kəsid anı; köhnə sistemin jurnal, cədvəl və tapşırıq modulları həmin anda yalnız oxunan rejimə keçir. Hər iki an `docs/runbooks/release-v1.md`-də və kəsid siyahısında yazılır (T43, T44).

### Qeydin sahibi

Hər varlığın hər anda bir sahib sistemi var. Sahib köhnə sistemdirsə, mənbə ilə bağlı sətrin Zəka-da dəyişdirilməsi təkrar idxalda konflikt hesabatına düşür (T16); Zəka-da yaradılan sətir uzlaşdırmada fərq sayılmır (T38). Sahib Zəka-dırsa, köhnə sistemdə həmin varlığa yazılan sətir fərqdir. Sahib cədvəli saat 10-da təsdiqləyir (SPEC Open Questions 19).

| Varlıq | Sahib sistem | Kim yazır | Sinxron istiqaməti |
|---|---|---|---|
| Şəxslər, struktur, fənn, cari semestrin qeydiyyatı, status əmrləri | T1-ə qədər köhnə sistem; T1-dən sonra Zəka | T1-ə qədər köhnə sistemin operatorları; T1-dən sonra tədris şöbəsi və admin (T15) | T1-ə qədər köhnə sistem → Zəka (təkrar idxal, T16; status əmrləri T38-in `status-events` növü ilə); T1-dən sonra Zəka → ixrac (T37) |
| Yeni semestrin fənn qeydiyyatı | Köhnə Academic modulu; qeydiyyat modulu Zəka-da qəbul olunandan sonra Zəka (dalğa 3, SPEC Open Questions 18) | Köhnə sistemin operatorları | Köhnə sistem → Zəka (`classes` və `enrollments` idxalı) |
| Cədvəl, otaq | İlk idxaldan Zəka (köhnə sistemdə yoxdur) | Tədris şöbəsi (T19), admin (T18) | Fayl → Zəka; təkrar idxal yalnız konflikt hesabatı ilə (T16) |
| Davamiyyət, cari ballar | Dalğa 0: sahibin qərarı, A və ya B; qərara qədər A. T1-dən sonra Zəka | A: köhnə sistem əsasdır, pilot müəllimlər T1-ə qədər hər iki sistemə yazır. B: T0-dan yalnız Zəka-ya yazılır; köhnə sistemə daxiletmə dekan əmri ilə dayanır | A: köhnə sistem → Zəka; fərqdə köhnə sistemin dəyəri qalır, T1-də qalıq və ballar yenidən idxal olunur (`--prefer source`, auditli). B: T0 ixracı bir dəfə idxal olunur; sonra sinxron yoxdur |
| İmtahan nəticələri | Dalğa 2-yə qədər köhnə sistem; dalğa 2-dən Zəka | Dalğa 2-dən Zəka (T30); köhnə sistemin imtahan moduluna ehtiyat nüsxəni kimin yazdığı sahibin qərarıdır | Zəka → köhnə sistem (ehtiyat nüsxə, T37 ixracı) |

Dalğa 2 başlamazdan əvvəl sahibin qərarı (SPEC Open Questions 20): imtahan günü RPO. Bağlananda backup kifayətdir, yoxsa imtahan zamanı dövri backup; ikinci halda T42 imtahan yük testi backup işləyərkən p95 < 500 ms verməlidir.

Hər dalğanın addımları:

1. **İnventar.** Köhnə sistemin cədvəlləri, sahələri, həcmi, sahibi.
2. **Xəritə.** Mənbə sahəsi → Zəka sahəsi; itən və ya çevrilən hər sahə yazılır.
3. **Quru sınaq.** `import --dry-run`: heç nə yazılmır, xəta hesabatı çıxır.
4. **İdxal.** İdempotent: təkrar işlətmə dəyişiklik yaratmır. Zəka-da dəyişdirilmiş sətir üstünə yazılmır, konflikt hesabatına düşür (T16).
5. **Uzlaşdırma.** Mənbə ilə bağlı sətirlər üzrə, ixrac anına qarşı: sətir sayı, yoxlama cəmi, 50 təsadüfi qeydin dekanlıqla əl yoxlaması.
6. **Paralel iş.** Dalğa 0: T1-ə qədər; dalğa 1: ən azı 14 gecə. İki sistem yan-yana; fərqlər gündəlik hesabatda. Kim harada yazır: "Qeydin sahibi" cədvəli.
7. **Kəsid.** Köhnə sistem yalnız oxunur. Köhnə sistemin sahib olduğu davamiyyət qalığı və ballar kəsid anında yenidən idxal olunur (`as_of` = kəsid tarixi). Geri qayıtma pəncərəsi: kəsiddən sonra N gün (sahib təyin edir, susmaya görə 14). Pəncərədə geri qayıtma belə aparılır: Zəka həmin varlıqlar üçün yalnız oxunur, `manage.py export --kind grades|attendance|oneroster --since <kəsid anı>` (T37) çıxışı dekanlığa verilir və ya köhnə sistemə idxal olunur, köhnə sistem yazma rejiminə qaytarılır. Pəncərədən sonra yalnız irəli düzəliş.

## Rəy axını

Hər mərhələnin sonunda, yoxlama nöqtəsindən əvvəl:

1. **Tap.** Altı rəyçi dəyişikliyi müstəqil oxuyur: kod, təhlükəsizlik, səssiz xəta, test, Python, təhlükəsizlik auditi.
   Təriflər `ecc` və `agent-skills` pluginlərinin agent fayllarından götürülür.
2. **Təkzib et.** Hər tapıntı ayrı agentə verilir. Tapşırığı tapıntını kodda yoxlayıb təkzib etməkdir.
3. **Düzəlt.** Yalnız təkzib olunmayan tapıntı düzəldilir, hər biri reqressiya testi ilə.
4. **Təhlükəsizlik.** `security-review` skili mərhələnin bütün fərqi üzərində işlədilir.

## Risks and Mitigations

| Risk | Təsir | Azaltma |
|---|---|---|
| Təhlükəsizlik iş axını iş budağında işləmir | Orta | CI iş budağında yaşıldır (Python 3.10–3.13 və Windows, üç ardıcıl commit). `security.yml` (gitleaks, pip-audit, bandit) bu budaqda işə düşməyib: T02-dən əvvəl əl ilə işə salınır və ya tetikləyicisi iş budağını əhatə edəcək şəkildə düzəldilir. |
| Köhnə sistemlərdən ixrac gecikir və ya natamamdır | Yüksək | İdxal OneRoster CSV şablonu ilə də işləyir: dekanlıq Excel-dən doldura bilər. Şablon dəstinə `attendance-opening.csv` və `grades.csv` daxildir. Kəşf birinci saatdan başlayır. |
| Dalğa 3-də qeydiyyat mənbəyi yoxdur | Yüksək | Yaz qeydiyyatı arxivdən əvvəl köhnə sistemdən ixrac olunur; modul Dalğa 3-dən əvvəl ayrıca tapşırıqdır. |
| SEB real cihazda fərqli davranır | Yüksək | Config Key alqoritmi SEB mənbə kodundan götürülüb; sahibin verdiyi `.seb` və açarla müqayisə testi; saat 52-də əl sınağı. İmtahanın qoruması SEB-dən asılı deyil (A10). |
| SQLite bir fakültədən artıq yükü çəkmir | Orta | `faculty` və `university` dəstlərində yük testi (T07, T42, T44); SQL yalnız `repo.py`-dədir; Postgres keçidi ayrıca tapşırıqdır. |
| İmtahan zamanı server düşür | Yüksək | Hər cavab ayrıca yazılır; proses öldürmə testi; nəzarətçi vaxt əlavə edə bilir; kağız ehtiyat planı runbook-dadır. |
| Server və ya disk itir | Yüksək | Hər backup ikinci hosta gedir; açar serverdən kənardadır; bərpa müddəti ölçülüb (T43); RPO 24 saat, imtahan günü imtahan bağlananda. |
| Maddə 8: ekran razılığı hüquqi baxımdan yetərsiz sayılır | Orta | Əsas funksiyalar üçün qanuni əsas universitetin öhdəliyidir; razılıq yalnız əlavə AI emalı üçün; hüquqşünas rəyi (Open Questions 10). |
| Xarici LLM şəxsi məlumat alır | Yüksək | Susmaya görə bağlıdır; açılanda maskalama və ayrıca razılıq (PR #3). |
| 46 tapşırıq 72 saata sığmır | Orta | Kəsmə sırası yan işi silir; kritik zəncirdə gecikmə üçün incəltmə siyahısı aşağıdadır. |
| Tək nəfərlik rəy | Orta | Çoxagentli rəy və təkzib; hər düzəliş testlə; sahib yoxlama nöqtələrində baxır. |
| Bulud sessiyası bağlanır, commit olunmamış iş itir | Yüksək | Hər yoxlama nöqtəsində commit və push (icazə ilə). |

### Kəsmə sırası

Vaxt çatmasa bu sıra ilə növbəti versiyaya keçir. Kritik yol və təhlükəsizlik kəsilmir.

1. T34 Qəbul saatları
2. T35 Klublar və kanallar
3. T22-nin tapşırıq axını (dilim 1; material faylı dilimi qalır)
4. T37 İnteqrasiya mərkəzinin webhook hissəsi
5. T39-un akkreditasiya hesabatı
6. T14 SSO (yerli hesab və MFA qalır)

Kritik zəncirdə incəltmə (tapşırıq qalır, bənd növbəti versiyaya keçir):

- T30: sual statistikası və oxşar səhv cavab siyahısı.
- T21: Excel-dən yapışdırma (cari ballar `grades` CSV şablonu ilə gəlir).
- T19: ləğv və köçürmə bildirişi.
- T11: "Sessiyalarım" siyahısı.

Kəsiləndə sənədlərdə dəyişən mətn:

- T30-un nəticə yazısı (`exam_id`, `attempt_no`) və imtahan-qiymət cədvəli kəsilərsə: SPEC Out of Scope-a "Təkrar imtahan, akademik borc siyahısı və imzalı imtahan-qiymət cədvəli" yazılır; dalğa 2-nin "Köhnə sistem" xanası "Rəsmi nəticə, təkrar imtahan və akademik borc köhnə sistemdə qalır; Zəka nəticəni ixrac edir" olur. T26-dakı imtahan siyahısı (buraxılış qapısı) heç bir halda kəsilmir.
- Sahib T15-in status əmrləri hissəsini (`student_status_events`) sprintdən çıxarsa (SPEC Open Questions 17): dalğa 1-in "Köhnə sistem" xanası "kontingent əmrləri dalğa 3-ə qədər köhnə sistemdə yazılır" olur; eyni cümlə SPEC Out of Scope-a yazılır; "Qeydin sahibi" cədvəlində status əmrlərinin sahibi dalğa 3-ə qədər köhnə sistem olur; bu hissənin qurulması dalğa 1-in ön şərti kimi yazılır.

## Sahibin addımları

| Nə vaxt | Nə | Niyə |
|---|---|---|
| Saat 0 | Bu spesifikasiya və planın təsdiqi; commit və push qaydası | Qurmağa başlamaq üçün |
| Saat 0 | İş budağından `main`-ə PR açılması və köhnə beş PR-ın bağlanması üzrə qərar | T01 (tamamlanıb) |
| Saat 0 | Hostinq qərarı və server girişi; sınaq nüsxəsi üçün DNS adı; sertifikat üsulu (ACME və ya AzTU-nun verdiyi sertifikat); imtahan auditoriyasının alt şəbəkəsi (CIDR) və oradan serverin 443 portuna çıxış (Open Questions 3, 5) | T09, T18, T19, T28, T29, T44 |
| Saat 0 | Backup üçün ölkə daxilində ikinci host və açarın saxlanma yeri (Open Questions 20) | T08, T44 |
| Saat 0 (ən geci saat 36) | Sessiya mühitinin şəbəkə icazəsinə `www.nist.gov` və `csrc.nist.gov` əlavə et; mümkün deyilsə NICE Framework Components v2.2.0 JSON faylını dəyişdirmədən `content/frameworks/nice-components-2.2.0.json` kimi ver. İstəyə görə `www.imsglobal.org`: T16-nın sütun adlarını OneRoster spesifikasiyası ilə tutuşdurmaq üçün | T24 (T16) |
| Saat 6 | Köhnə sistemlərin siyahısı və ilk ixraclar; pilot fakültə üçün cari semestrin davamiyyəti (tələbə × fənn: keçilmiş, buraxılmış və üzrlü saat) və cari balları (tələbə × fənn × komponent) daxil; davamiyyət dərs səviyyəsində, yoxsa yekun kimi verilir, cari ballar harada saxlanır (Open Questions 2). İxrac yoxdursa dekanlıq `attendance-opening.csv` və `grades.csv` şablonlarını doldurur | T16, T20, T21, T38 |
| Saat 10 | İlk fakültə, fənlər, müəllimlər; real cədvəl ixracı: qrup, yarımqrup, dərs növü, müəllim sütunları ilə (Open Questions 14). Tədris vahidi modeli cavabdan asılı olmayaraq qəbul olunur: düz hal onun xüsusi halıdır | T15–T17, T19 |
| Saat 10 | Davamiyyət və qiymətləndirmə əsasnaməsi; rəsmi akademik təqvim: son tədris günü, sessiya tarixləri (Open Questions 15) | T15, T17, T20, T21 |
| Saat 10 | Open Questions 17 üzrə qərar: status əmrlərini kim daxil edir (öz fakültəsi üzrə `office`, yoxsa yalnız `academic_office`); status əmrləri sprintdə qalırmı | T15, T37 |
| Saat 10 | "Qeydin sahibi" cədvəlinin təsdiqi; kəsid tarixi (`journal.cutover_date` ayarı və idxalın `as_of` dəyəri); dalğa 0 üçün A və ya B (yazı sistemi); dekan əmri; geri qayıtma pəncərəsinin günü (Open Questions 9, 19) | T16, T17, T20, T38, T43 |
| Saat 10 | A19 üzrə qərar, T10 başlamazdan əvvəl: vaxtın saxlanma qaydası (Open Questions 22) | T05, T10 |
| Saat 22 | Otaq siyahısı, korpus girişləri; dalğa 0 korpuslarının mərtəbə planları (PDF və ya şəkil); qraf qaralamasını yoxlayacaq şəxs (Open Questions 25) | T18, T31 |
| Saat 22 | SMTP məlumatı | T36 |
| Saat 22 (Checkpoint B) | Open Questions 24 üzrə qərar: rol cədvəli; dekanlığın rol id-si (`office` qalır, yoxsa `dean_office`); `qa.moderate` və `community.moderate` kimdədir | T13, T33, T35 |
| Saat 36 | SEB qurulmuş 2 Windows kompüteri; SEB Config Tool-da "Use SEB settings file for: starting an exam" seçimi ilə, parol və sertifikat seçilmədən, şifrələnməmiş saxlanmış bir `.seb` faylı və alətin göstərdiyi Config Key | T28 |
| Saat 36 | Open Questions 11 və 12 üzrə qərar: açıqlamadan sonra sual açarının tələbəyə göstərilməsi; cəhd gedərkən adi girişin imtahan sessiyasını bağlamaması | T26, T27 |
| Saat 36 | Open Questions 16 üzrə qərar: təkrar imtahan qaydası; imtahan-qiymət cədvəlini kim imzalayır | T26, T30 |
| Saat 52 | Qaydalar, əsasnamələr, tələbə bələdçisi mətnləri | T32 |
| Saat 62 | Sınaq istifadəçiləri; buraxılış qərarı | T44 |
| Dalğa 2 başlamazdan əvvəl | İmtahan günü RPO (Open Questions 20); köhnə sistemin imtahan moduluna ehtiyat nəticəni kim yazır (Open Questions 19) | T42, T43 |
| Yaz qeydiyyatı açılmazdan əvvəl | Open Questions 18 üzrə qərar: yaz semestrinin fənn qeydiyyatı harada aparılır | Dalğa 3-ün bağlanma şərti |

Open Questions 13, 21 və 23 susmaya görə dəyərlə gedir. Cavab gözlənilmir; sahib istəsə dəyişir.

## Open Questions

`SPEC.md`-dəki suallar. Plana ən çox təsir edənlər: 2 (ixrac formatı), 3 (hostinq), 4 (SSO protokolu), 5 (auditoriyalar), 9 (ilk fakültə və kəsid tarixi), 19 (qeydin sahibi), 20 (backup hostu və RPO), 22 (vaxtın saxlanması), 24 (rol cədvəli).
