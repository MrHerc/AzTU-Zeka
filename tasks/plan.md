# Implementation Plan: Zəka V1 — AzTU-nun mövcud sistemlərinin əvəzlənməsi

Source spec: `SPEC.md` · Tapşırıqlar: `tasks/todo.md` · Vəziyyət: **təsdiq gözləyir** · Tarix: 2026-11-16

## Overview

72 saatda Zəka demodan işləyən məhsula çevrilir: real hesablar, itməyən məlumat, müəllimin yazdığı jurnal,
icra olunan sillabus, SEB ilə imtahan, otaq tapan köməkçi, müəllimə sual, klublar, idxal və kəsid alətləri.
Bir fakültə 72-ci saatda real məlumatla işə başlayır. Qalan fakültələr eyni alətlərlə dalğa-dalğa keçir.

İş 6 mərhələ, 44 tapşırıqdır. Hər tapşırıq bir şaquli dilimdir: sxem, servis, marşrut, interfeys, test.
Hər mərhələ yoxlama nöqtəsi ilə bağlanır. Nöqtə keçilməsə növbəti mərhələ başlamır.

## Architecture Decisions

| # | Qərar | Əsas | Yenidən baxma şərti |
|---|---|---|---|
| A1 | Beş PR əvvəlcə birləşdirilir, sonra restruktur gedir. | Restruktur açıq PR-larla toqquşardı. Sınaq birləşdirməsi `trial/integration` budağında aparılır. | — |
| A2 | Repo dilə və qata görə bölünür: `backend/`, `frontend/`, `infra/`, `exam/`. Modulun içində `domain / service / repo / routes`. | Sahibin tələbi. Modul daxilində qat bölgüsü köhnə kodu tədricən köçürməyə imkan verir. | — |
| A3 | Köhnə `r_*.py` faylları `legacy/`-yə köçürülür, davranışı dəyişmir. Yeni modullar birbaşa qatlı yazılır. | Böyük partlayışla yenidən yazmaq 639 testi və 5 PR-ın düzəlişlərini riskə atır. | Modul toxunulanda qatlara bölünür. |
| A4 | HTTP qatı qalır, qabağına Caddy qoyulur. | PR #3 və #5 protokol səhvlərini bağlayıb. Caddy TLS və HTTP normallaşdırmanı götürür. | Yük testi tələb edərsə ASGI. |
| A5 | Proses başına eyni anda 2 handler; nüvə başına bir proses (`SO_REUSEPORT`). | Ölçülüb: məhdudiyyətsiz 47 sorğu/san və 300 müştəridə 150 xəta; 2 handler ilə 226 sorğu/san və 0 xəta. | — |
| A6 | Proses-lokal vəziyyət bazaya köçürülür: birdəfəlik açarlar, limit sayğacları. Axtarış indeksi hər prosesdə qurulur, dəyişiklik siqnalı ilə yenilənir. | Çox proses üçün şərtdir. | — |
| A7 | SQLite WAL qalır, miqrasiya mühərriki əlavə olunur. SQL yalnız `repo.py`-də. | Bir fakültə üçün kifayətdir; quraşdırma tək konteynerdir. | 10 000 tələbə eyni anda: Postgres. |
| A8 | Parol hash-i `hashlib.scrypt`; konfiqurasiya ilə PBKDF2-HMAC-SHA-256. | Standart kitabxanadadır, yaddaş-ağırdır. PBKDF2 NIST-in təsdiqlədiyi yeganə sxemdir, tələb olunsa keçid bir ayardır. | — |
| A9 | SSO ümumi OIDC müştərisidir (code + PKCE). ID token imzası yoxlanmır, token son nöqtəsinə birbaşa TLS bağlantısına güvənilir. | OIDC Core 3.1.3.7 buna icazə verir; RS256 üçün asılılıq lazım olmur. | AzTU SSO-su SAML-dırsa `cryptography` icazəsi. |
| A10 | İmtahanın əsl qoruması serverdədir: imtahan əhatəli sessiya, server taymeri, tək sessiya, şəbəkə siyahısı. SEB əlavə qatdır. | SEB Config Key yalnız konfiqurasiyanı bildiyini sübut edir; `.seb` faylı olan onu saxtalaşdıra bilər. | — |
| A11 | İmtahan hadisələri hash zənciri ilə yazılır; zəncirin kökü QR-lı protokola düşür. | Sonradan dəyişdirilmə aşkar olunur. Mövcud QR sənəd infrastrukturu təkrar istifadə olunur. | — |
| A12 | Sillabus fənnin konfiqurasiyasıdır: dərc olunan versiya jurnal komponentlərini, davamiyyət həddini, tutor rejimini və imtahan planını təyin edir. | Bir həqiqət mənbəyi; akkreditasiya üçün nəticə → sual → nəticə zənciri. | — |
| A13 | Çərçivələr CASE modelinə bənzər cədvəldə saxlanır: çərçivə, versiya, bənd id, valideyn. | NICE, Bloom, EQF, ABET eyni mexanizmlə işləyir; versiya dəyişəndə köhnə xəritə qalır. | — |
| A14 | Klub mesajları 3 saniyəlik sorğu ilə gəlir (`since_id`). | WebSocket yeni infrastruktur tələb edir; klub söhbəti üçün 3 saniyə kifayətdir. | Gecikmə şikayəti: SSE. |
| A15 | Bildirişlər baza növbəsindən gedir; fon işi `smtplib` ilə göndərir və təkrar cəhd edir. | Xarici növbə sistemi lazım deyil. | — |
| A16 | Otaq marşrutu qraf üzərində Dijkstra-dır: düyünlər giriş, pilləkən, lift, otaq. Yerləşmə QR lövbərlərlə. | Bina daxilində GPS işləmir; mayak avadanlığı lazım olmur. | — |
| A17 | AI susmaya görə oflayn mühərrikdir. Hər cavab mənbə göstərir, yoxdursa insana ötürür. | Maddə 14. Qoruyucusuz AI tutor qiyməti aşağı salır (2026 sınağı). | LLM seçimi: Open Questions 6. |
| A18 | Kamera, səs, üz ilə proktorinq yoxdur. | Maddə 9.5 biometrikadır. AzTU-da imtahanlar onsuz da video ilə yazılır. | — |

## Dependency Graph

```
platform ── identity ── directory ──┬── facilities ──┐
                                    │                ├── timetable ── journal ──┬── radar
                                    │                │                          └── services (qiymətə əsaslanan sənəd)
                                    ├── syllabus ────┼── learning ── exam
                                    │                │
                                    ├── qa           └── assistant
                                    ├── community
                                    ├── comms
                                    └── integration, migration        insight ← hamısı
```

Kritik yol: `platform` → `identity` → `directory` → `timetable` → `journal` → `exam`.
`facilities`, `syllabus`, `qa`, `community`, `comms` kritik yoldan kənardır və paralel gedir.

## Task List

Tam mətn, qəbul meyarları və yoxlama addımları `tasks/todo.md`-dədir.

### Phase 0 — Birləşdirmə və bünövrə · saat 0–10

- [x] T01 Beş PR-ı birləşdir — 698 test yaşıl, commit `9d23e99`
- [ ] T02 Sətir sonlarını sabitlə
- [ ] T03 Repo-nu dilə və qata görə böl
- [ ] T04 Miqrasiya mühərriki
- [ ] T05 İş rejimləri: demo və prod
- [ ] T06 Handler qapısı və çox proses
- [ ] T07 Proses-lokal vəziyyəti bazaya köçür
- [ ] T08 Backup və bərpa
- [ ] T09 Yerləşdirmə: Docker, Caddy, sağlamlıq yoxlaması

### Checkpoint A · saat 10
- [ ] Bütün testlər yaşıl; `docker compose up` ilə HTTPS açılır; yenidən başlatma məlumatı saxlayır
- [ ] 300 paralel müştəridə 0 xəta; bərpa sınağı keçir

### Phase 1 — Kimlik və reyestr · saat 10–22

- [ ] T10 Hesablar və parol
- [ ] T11 Sessiya sərtləşdirməsi
- [ ] T12 İşçi rolları üçün TOTP
- [ ] T13 Rol və icazə modeli
- [ ] T14 SSO: ümumi OIDC müştərisi
- [ ] T15 Struktur və reyestr idarəsi
- [ ] T16 Kütləvi idxal
- [ ] T17 Tenant ayarları

### Checkpoint B · saat 22
- [ ] Prod rejimində parolsuz yol yoxdur; rol × marşrut matrisi yaşıl
- [ ] 10 000 tələbə idxal olunur və öz hesabı ilə girir

### Phase 2 — Akademik nüvə · saat 22–36

- [ ] T18 Korpus, otaq və otaq QR-i
- [ ] T19 Cədvəl idarəsi və iCal
- [ ] T20 Davamiyyət jurnalı
- [ ] T21 Qiymət jurnalı
- [ ] T22 Tapşırıqlar

### Checkpoint C · saat 36
- [ ] Müəllim dərsdə davamiyyət və bal yazır; tələbə dərhal görür
- [ ] 25% həddi və imtahana buraxılış avtomatik hesablanır

### Phase 3 — Sillabus və imtahan · saat 36–52

- [ ] T23 Struktur sillabus
- [ ] T24 Çərçivə xəritəsi və NICE idxalı
- [ ] T25 Təsdiq axını və fənnin konfiqurasiyası
- [ ] T26 İmtahan nüvəsi
- [ ] T27 İmtahan əhatəli sessiya və imtahan səhifəsi
- [ ] T28 SEB inteqrasiyası
- [ ] T29 Nəzarətçi paneli
- [ ] T30 Hash zəncirli protokol və nəticənin jurnala keçməsi

### Checkpoint D · saat 52
- [ ] 300 simulyasiya olunmuş tələbə ilə sınaq imtahanı: 0 itki, p95 < 500 ms
- [ ] Windows kompüterində SEB ilə əl sınağı (sahib)

### Phase 4 — Köməkçi, sual-cavab, icma, inteqrasiya · saat 52–62

- [ ] T31 Kampus köməkçisi: otaq tapma və marşrut
- [ ] T32 Kampus köməkçisi: bilik bazası idarəsi və insana ötürmə
- [ ] T33 Müəllimə sual və fənn forumu
- [ ] T34 Qəbul saatları
- [ ] T35 Klublar və kanallar
- [ ] T36 E-poçt bildirişləri
- [ ] T37 İnteqrasiya mərkəzi

### Checkpoint E · saat 62
- [ ] 50 suallıq dəstdə mənbə düzgünlüyü ≥ 90%
- [ ] Hər yeni modul təhlükəsizlik matrisindədir

### Phase 5 — Miqrasiya, sərtləşdirmə, buraxılış · saat 62–72

- [ ] T38 ETL və uzlaşdırma
- [ ] T39 Ölçülmüş göstəricilər və akkreditasiya sübutu
- [ ] T40 Məxfilik: razılıq, saxlama, ixrac, silmə
- [ ] T41 Təhlükəsizlik baxışı və NIST nəzarət matrisi
- [ ] T42 E2E, əlçatanlıq və yük testi
- [ ] T43 Runbook-lar
- [ ] T44 Buraxılış

### Checkpoint F · saat 72 — buraxılış qapısı
- [ ] SPEC-dəki bütün Success Criteria təsdiqlənib və ya istisna yazılı qeyd olunub
- [ ] Hədəf serverdə bərpa sınağı keçib; ilk fakültənin uzlaşdırma fərqi 0

## Paralel zolaqlar

Kritik yol ardıcıl gedir. Qalan iş ayrı iş qovluqlarında (worktree) paralel aparılır və növbə ilə birləşdirilir.

| Saat | Zolaq 1 (kritik yol) | Zolaq 2 | Zolaq 3 | Sahib |
|---|---|---|---|---|
| 0–10 | T01–T07 | T08, T09 | T38 kəşf: köhnə ixrac formatları | Hostinq, server girişi, PR birləşdirməyə icazə |
| 10–22 | T10–T13, T15 | T16, T17 | T14 | Köhnə sistemlərdən ilk ixraclar; fakültə seçimi |
| 22–36 | T19–T21 | T18, T22 | T36 | Otaq siyahısı, korpus girişləri; SMTP məlumatı |
| 36–52 | T26–T30 | T23–T25 | T33, T34 | SEB qurulmuş 2 kompüter; bir `.seb` faylı və açarı |
| 52–62 | T31, T32 | T35, T37 | T39, T40 | Bilik bazası mətnləri: qaydalar, əsasnamələr |
| 62–72 | T41, T42 | T38 idxal, T43 | T44 | Sınaq istifadəçiləri; buraxılış qərarı |

## Miqrasiya və kəsid

Prinsip: heç bir dalğa imtahan sessiyasının ortasında bağlanmır. Hər dalğada köhnə sistem oxunaqlı qalır.

| Dalğa | Vaxt | Zəka-ya keçən | Köhnə sistem | Bağlanma şərti |
|---|---|---|---|---|
| 0 | 72 saat | Bir fakültə: giriş, cədvəl, otaq, davamiyyət, cari ballar, sillabus, köməkçi, sual-cavab, klub | Əsas mənbə qalır | Uzlaşdırma fərqi 0; 300 nəfərlik sınaq imtahanı |
| 1 | 2–4 həftə | Bütün fakültələr: jurnal, cədvəl, tapşırıq; SSO | Yalnız oxunur, gecəlik müqayisə | İki ardıcıl həftə fərq 0; dəstək sorğuları sabitləşib |
| 2 | Qış sessiyası | İmtahanlar SEB ilə; protokollar; apellyasiya; e-xidmətlər | İmtahan nəticələrinin ehtiyat nüsxəsi | Hər imtahanın protokolu və zəncir kökü var |
| 3 | Yaz semestrinin əvvəli | Zəka əsas sistemdir; tarixi məlumat köçürülür; dövlət sistemlərinə ixrac | Arxiv | Rektorluğun yazılı qəbulu; arxivin bərpa sınağı |

Hər dalğanın addımları:

1. **İnventar.** Köhnə sistemin cədvəlləri, sahələri, həcmi, sahibi.
2. **Xəritə.** Mənbə sahəsi → Zəka sahəsi; itən və ya çevrilən hər sahə yazılır.
3. **Quru sınaq.** `import --dry-run`: heç nə yazılmır, xəta hesabatı çıxır.
4. **İdxal.** İdempotent: təkrar işlətmə dəyişiklik yaratmır.
5. **Uzlaşdırma.** Sətir sayı, yoxlama cəmi, 50 təsadüfi qeydin dekanlıqla əl yoxlaması.
6. **Paralel iş.** Müəyyən müddət iki sistem yan-yana; fərqlər gündəlik hesabatda.
7. **Kəsid.** Köhnə sistem yalnız oxunur. Geri qayıtma: son backup və köhnə sistemin yazma rejiminə qaytarılması.

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
| PR birləşdirməsi gözləniləndən çətin çıxır | Yüksək | Sınaq birləşdirməsi indi fonda aparılır; nəticə T01-in girişidir. |
| Köhnə sistemlərdən ixrac gecikir və ya natamamdır | Yüksək | İdxal OneRoster CSV şablonu ilə də işləyir: dekanlıq Excel-dən doldura bilər. Kəşf birinci saatdan başlayır. |
| SEB real cihazda fərqli davranır | Yüksək | Config Key alqoritmi SEB mənbə kodundan götürülüb; sahibin verdiyi `.seb` və açarla müqayisə testi; saat 52-də əl sınağı. İmtahanın qoruması SEB-dən asılı deyil (A10). |
| SQLite bir fakültədən artıq yükü çəkmir | Orta | A5 ilə ölçülmüş ehtiyat; SQL yalnız `repo.py`-dədir; Postgres keçidi ayrıca tapşırıqdır. |
| İmtahan zamanı server düşür | Yüksək | Hər cavab ayrıca yazılır; proses öldürmə testi; nəzarətçi vaxt əlavə edə bilir; kağız ehtiyat planı runbook-dadır. |
| Maddə 8: ekran razılığı hüquqi baxımdan yetərsiz sayılır | Orta | Əsas funksiyalar üçün qanuni əsas universitetin öhdəliyidir; razılıq yalnız əlavə AI emalı üçün; hüquqşünas rəyi (Open Questions 10). |
| Xarici LLM şəxsi məlumat alır | Yüksək | Susmaya görə bağlıdır; açılanda maskalama və ayrıca razılıq (PR #3). |
| 44 tapşırıq 72 saata sığmır | Orta | Kəsmə sırası aşağıdadır; kritik yol kəsilmir. |
| Tək nəfərlik rəy | Orta | Çoxagentli rəy və təkzib; hər düzəliş testlə; sahib yoxlama nöqtələrində baxır. |
| Bulud sessiyası bağlanır, commit olunmamış iş itir | Yüksək | Hər yoxlama nöqtəsində commit və push (icazə ilə). |

### Kəsmə sırası

Vaxt çatmasa bu sıra ilə növbəti versiyaya keçir. Kritik yol və təhlükəsizlik kəsilmir.

1. T34 Qəbul saatları
2. T35 Klublar və kanallar
3. T22 Tapşırıqlar
4. T37 İnteqrasiya mərkəzinin webhook hissəsi
5. T39-un akkreditasiya hesabatı
6. T14 SSO (yerli hesab və MFA qalır)

## Sahibin addımları

| Nə vaxt | Nə | Niyə |
|---|---|---|
| Saat 0 | Bu spesifikasiya və planın təsdiqi; commit və push qaydası | Qurmağa başlamaq üçün |
| Saat 0 | Beş PR-ı birləşdirməyə icazə | T01 |
| Saat 0 | Hostinq qərarı və server girişi | T09, T44 |
| Saat 6 | Köhnə sistemlərin siyahısı və ilk ixraclar | T16, T38 |
| Saat 10 | İlk fakültə, fənlər, müəllimlər | T15–T17 |
| Saat 22 | Otaq siyahısı, korpus girişləri, mərtəbə planları | T18, T31 |
| Saat 22 | SMTP məlumatı | T36 |
| Saat 36 | SEB qurulmuş 2 Windows kompüteri; SEB Config Tool-da yaradılmış bir `.seb` faylı və onun Config Key-i | T28 |
| Saat 52 | Qaydalar, əsasnamələr, tələbə bələdçisi mətnləri | T32 |
| Saat 62 | Sınaq istifadəçiləri; buraxılış qərarı | T44 |

## Open Questions

`SPEC.md`-dəki 10 sual. Plana ən çox təsir edənlər: 2 (ixrac formatı), 3 (hostinq), 4 (SSO protokolu), 5 (auditoriyalar), 9 (ilk fakültə).
