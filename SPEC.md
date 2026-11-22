# Spec: Zəka — AzTU vahid universitet portalı — V1

Vəziyyət: **təsdiq gözləyir** · Tarix: 2026-11-16 · Baza: iş budağı `claude/tender-meitner-avsvvh` (`main @ a59ef1f` + birləşdirilmiş beş PR, commit `9d23e99`)
Əlaqəli sənədlər: `tasks/plan.md` (plan), `tasks/todo.md` (tapşırıqlar), `docs/CODEMAP.md` (kodun xəritəsi),
`docs/research/` (araşdırma), `docs/report/zeka-vahid-hesabat.html` (vahid hesabat).

## Objective

AzTU mövcud informasiya sistemlərindən Zəka-ya keçir. Zəka onları **əvəz edir**, üstünə qat kimi oturmur.
Bir giriş, bir məlumat bazası, bir interfeys: tədris, jurnal, sillabus, imtahan, xidmətlər, kampus köməkçisi, icma.

İstifadəçilər: tələbə (10 000+), müəllim (1 000+), kafedra müdiri, dekanlıq, tədris şöbəsi, imtahan nəzarətçisi,
klub rəhbəri, rəhbərlik, İT admin.

V1-in işi: bir fakültənin cari semestrini real məlumatla Zəka-da aparmaq və qalan fakültələrin keçidi üçün
bütün mexanizmi (idxal, uzlaşdırma, kəsid) hazır saxlamaq.

### Əvəzləmə matrisi

Hər sətir: mövcud sistem, onu əvəz edən modul və ölçülə bilən üstünlük.

| Mövcud | Zəka modulu | Nə ilə üstün olmalıdır |
|---|---|---|
| KOICA LMS, e-Learning | `learning` | Mənbəli Azərbaycanca tutor, test studiyası, tapşırıq axını, mobil interfeys, üç dil |
| KOICA Academic, kabinetlər | `directory`, `journal` | Müəllim jurnalı dərsdə telefonla doldurur; 25% həddi və imtahana buraxılış avtomatik hesablanır; tədris planı və fənn qeydiyyatı V1-də əvəz olunmur (Out of Scope) |
| KOICA Portal, elanlar, Groupware | `comms`, `services` | SLA-lı müraciət, QR-doğrulanan sənəd, e-poçt və tətbiqdaxili bildiriş |
| Cədvəl (TKTA: sistemdə yoxdur) | `timetable`, `facilities` | Toqquşma yoxlaması, otağa marşrut, iCal, qapıda QR |
| E-jurnal (TKTA: sistemdə yoxdur) | `journal` | Hər dəyişiklik audit jurnalında; düzəliş pəncərəsi və səbəb məcburidir |
| Apellyasiya portalı | `services` | Eyni pəncərədə, SLA və qərar tarixçəsi ilə |
| İmtahan prosesi | `exam` | SEB, fərdi variant, server taymeri, hash zəncirli QR protokol; biometrika yoxdur |
| Word və PDF sillabuslar | `syllabus` | Sillabus fənni konfiqurasiya edir və akkreditasiya sübutu çıxarır |
| Saytdakı AI köməkçi (xarici API) | `assistant` | Qaydaya istinad, əməliyyat düyməsi, otaq tapma; məlumat ölkədən çıxmır |
| Google Forms sorğuları | `insight` | Rol üzrə hədəfli sorğu, nəticə paneldə, şəxsi məlumat daxildə qalır |
| Telegram və WhatsApp qrupları | `community` | Rəsmi, moderasiyalı, auditli; üzvlük universitet hesabına bağlıdır |
| AMAS, DrSys | açıq sual | Funksiyaları məlum deyil (Open Questions 1) |

## Assumptions

Bunlarla işləyirəm. Səhv olan varsa, indi düzəlt.

1. Keçid dalğalarla gedir. Dalğa bağlanana qədər köhnə sistem oxunaqlı qalır.
2. Backend dili Python qalır. V1-də ikinci backend dili yoxdur.
3. Frontend mövcud SPA üzərində davam edir, build addımı əlavə olunmur.
4. İlk yerləşdirmə tək serverdə, Docker ilə, ölkə daxilində.
5. SEB imtahan auditoriyalarının Windows kompüterlərində qurulur.
6. Köhnə sistemlərdən məlumat fayl ixracı ilə alınır. API-nin olub-olmadığı məlum deyil.
7. Giriş V1-də yerli hesab və MFA ilədir. `sso.aztu.edu.az` qoşulması AzTU İT giriş verəndə açılır.
8. AI susmaya görə oflayn mühərriklə işləyir. Xarici model yalnız açıq razılıqla.
9. Qiymət sxemi AzTU qaydasıdır: seminar 30, davamiyyət 10, sərbəst iş 10, imtahan 50, imtahanda minimum 17.
10. Tədris dövrü və imtahan sessiyası ayrı saxlanır. `content/seed.json`-dakı aralıq (15.09.2026 – 31.01.2027) ikisini birlikdə əhatə edir; aralarındakı sərhəd məlum deyil və rəsmi təqvimlə yoxlanmayıb (Open Questions 15).
11. 25% qaydası belə oxunur; sahib təsdiqləməlidir (Open Questions 15). Məxrəc fənnin tədris dövründəki ləğv olunmamış dərslərinin akademik saatıdır. Buraxılmış hər saat sayılır, üzrlü də: bu, yeganə mənbənin hərfi oxunuşudur (`docs/research/01-azerbaycan-bazar-ve-qanun.md:44`). Davamiyyətin 10 balı jurnaldan tenant qayda cədvəli ilə hesablanır.

### Sahibin 2026-11-18 qərarları

- Plan təsdiq olunub.
- İnteqrasiyalar mərhələlidir; hələlik mövcud sistemlər saxlanır: dalğa 0-da köhnə sistem rəsmi qeyddir (Open Questions 19, A variantı). İnteqrasiya fayl idxalı ilə başlayır; SSO və API bağlantıları sonrakı mərhələdədir.
- Sillabus yaradılarkən kafedranın akademik yük forması (Forma №3) istifadə olunur: `docs/forms/forma-3.md`, Task 16 və Task 23.

## Capability Map

Modul id-ləri sabitdir. Asılılıq bir istiqamətlidir, dövr yoxdur.

| Modul id | Məsuliyyət | Asılıdır | Kodda bu gün |
|---|---|---|---|
| `platform` | HTTP, konfiqurasiya, baza, miqrasiya, backup, log, i18n, tenant ayarları, fon işləri | — | Qismən: HTTP, i18n var; miqrasiya, backup, iş növbəsi yoxdur; heç bir iş öz-özünə (vaxtla) işləmir |
| `identity` | Hesab, parol, MFA, sessiya, rol və icazə, SSO, audit | `platform` | Yoxdur (yalnız demo rol girişi); işçi bütün fakültələrin müraciətini və əlavəsini görür, şəxsi məlumatın oxunması auditə yazılmır |
| `directory` | Fakültə, kafedra, ixtisas, qrup, istifadəçi, fənn, tədris vahidi (fənn × növ × müəllim × qrup), qeydiyyat; idarəetmə və idxal | `identity` | Yalnız seed; yazma yolu yoxdur |
| `facilities` | Korpus, mərtəbə, otaq, marşrut qrafı, otaq QR-i | `platform` | Yoxdur (otaq cədvəldə mətn sahəsidir) |
| `timetable` | Cədvəl, dərs, otaq bölgüsü, toqquşma yoxlaması, iCal | `directory`, `facilities` | Yalnız göstərmə; yazma yolu yoxdur |
| `journal` | Davamiyyət və qiymət jurnalı, qiymət sxemi, imtahana buraxılış, yekun qiymət | `timetable` | Yalnız göstərmə; müəllim yaza bilmir |
| `syllabus` | Struktur sillabus, çərçivə xəritəsi, təsdiq, versiya, fənnin konfiqurasiyası | `directory`, `journal` | Qismən: generasiya, saxlama, çap var |
| `learning` | Material, tapşırıq, AI tutor, test studiyası, məşq testi | `directory`, `syllabus`, `journal` | Var; tapşırıq axını yoxdur; materialın orijinal faylı saxlanmır, yalnız çıxarılan mətn qalır |
| `exam` | İmtahan, variant, taymer, SEB, nəzarətçi paneli, protokol | `learning`, `identity`, `facilities`, `journal`, `services`, `comms` | Yoxdur (məşq testi var) |
| `assistant` | Kampus köməkçisi: bilik bazası, otaq tapma, əməliyyat, insana ötürmə | `facilities`, `timetable`, `services` | Qismən: bilik bazası və əməliyyat var |
| `qa` | Müəllimə sual, fənn forumu, qəbul saatları | `directory`, `learning` | Qismən: müəllimə yönləndirmə var |
| `services` | E-xidmət, sənəd, QR doğrulama, apellyasiya | `identity`, `directory`, `journal` | Var; sənədlər sintetik qiymətə əsaslanır və hər baxışda canlı sətirlərdən qurulur, `/verify` hash-i yenidən hesablamır; təsdiq addımları formaldır; 13 növdən 10-u heç nə dəyişmir; növlər yalnız seed-dədir |
| `community` | Klublar, kanallar, mesaj, moderasiya | `identity` | Yoxdur |
| `comms` | Bildiriş (tətbiqdaxili, e-poçt), xəbər, tədbir | `identity` | Qismən: e-poçt yoxdur |
| `radar` | Erkən xəbərdarlıq, dəstək planı | `journal`, `learning` | Var (PR #4-dən birləşdirilib); nümunə məlumatdan qidalanır |
| `insight` | Hadisə jurnalı, ölçülmüş göstəricilər, akkreditasiya sübut paketi, sorğu | hamısı | Qismən: bəzi rəqəmlər sabit yazılıb |
| `integration` | İdxal və ixrac, iCal, SSO bağlantıları, API açarı, webhook, tətbiq paneli | `directory` | Yoxdur |
| `migration` | Köhnə sistemlərdən ETL, uzlaşdırma, kəsid | `directory`, `journal`, `integration`, `exam` | Yoxdur |
| `support` | Dəstək masası, rəy | `identity` | Var |

Qurulma sırası:
`platform` → `identity` → `directory` → `facilities`, `timetable` → `journal` → `syllabus`, `learning` → `exam`
→ `assistant`, `qa`, `services` → `community`, `comms` → `radar`, `insight` → `integration`.
`migration` kəşf mərhələsi ilə birinci gündən paralel gedir.
İstisna: iş icraçısı və e-poçt növbəsi (T36) və sənədin bütövlüyü (T45) `exam`-dan əvvəl qurulur. `exam` zəncirin kökünü e-poçtla göndərir və protokolu saxlanmış yüklə verir.

Modullararası müqavilə təminatçı modulun `service.py` faylındadır. Başqa modul onun `repo.py`-sinə və cədvəllərinə birbaşa toxunmur.

## Tech Stack

| Qat | Seçim | Əsas |
|---|---|---|
| Backend | Python 3.12+, yalnız standart kitabxana | 5 500 sətir işləyən kod; sıfır asılılıq universitet serverində quraşdırmanı sadələşdirir |
| HTTP | Mövcud `http.server` qatı (PR #3 və #5 düzəlişləri ilə), qabağında Caddy 2 | Caddy TLS-i, HTTP normallaşdırmanı və ölçü həddini götürür |
| Paralellik | Proses başına eyni anda ən çox 2 handler, nüvə başına bir proses; xarici çağırışlar ayrıca həddə | Ölçülüb (demo baza: 147 istifadəçi; yalnız `GET /api/student/home`, bir sessiya; tək proses): 47 → 226 sorğu/san, 300 müştəridə 0 xəta. Qapının müqayisəsidir, tutum ölçüsü deyil. |
| Baza | SQLite WAL, nömrələnmiş SQL miqrasiyalar | Bir fakültə üçün fərziyyədir; `faculty` və `university` dəstlərində yük testi (T07, T42, T44) təsdiqləyir. Postgres-ə keçid `repo.py` sərhədi ilə hazırlanır |
| Frontend | Sadə ES modulları, mövcud dizayn sistemi | Sahibin tələbi: mövcud interfeys qalır |
| İmtahan müştərisi | Safe Exam Browser 3.x (MPL-2.0) | Öz brauzerimizi yazmırıq |
| AI | Oflayn BM25 mühərriki; istəyə görə LLM | Maddə 14: məlumat susmaya görə ölkədə qalır |
| Yerləşdirmə | Docker, Compose | Bir əmrlə quraşdırma və bərpa |
| İnkişaf alətləri | pytest, ruff, mypy, Playwright | PR #5-dən gəlir |

Dillər: Python, JavaScript, CSS, HTML, SQL, shell, YAML. Hər dil öz kök qovluğundadır.
Java V1-də yoxdur: ikinci backend dili ikinci iş mühiti və ikinci təhlükəsizlik səthi deməkdir, V1-də onu tələb edən komponent yoxdur.

İcazə tələb edən mümkün asılılıqlar: `cryptography` (SAML XML imzası və ya RS256 ilə imzalama lazım olsa; RS256 imzasının yoxlanması stdlib ilə mümkündür), `psycopg` (Postgres mərhələsində).

## Commands

Restrukturdan (T03) sonra qüvvədədir.

```bash
python backend/run.py --port 5070                      # lokal, demo rejimi
ZEKA_MODE=prod python backend/run.py --host 127.0.0.1  # prod rejimi: demo giriş, seed və reset bağlıdır
docker compose -f infra/compose.yml up -d              # server: Caddy + tətbiq

python -m pytest -q                                    # bütün testlər
python -m pytest tests/unit/test_exam_rules.py::test_deadline_caps_at_window -q
ruff check . && mypy                                   # lint və tip yoxlaması
for f in frontend/js/*.js; do node --check "$f"; done  # JS sintaksisi

python tools/i18n.py extract && python tools/i18n.py build && python tools/i18n.py stats

python backend/manage.py migrate                       # sxem miqrasiyaları
python backend/manage.py import --kind users --source koica --file users.csv --dry-run
python backend/manage.py reconcile --wave 1 --source koica   # mənbə və hədəf uzlaşdırması
python backend/manage.py export --kind attendance --since 2026-12-01T00:00:00+04:00   # geri qayıtma ixracı
infra/backup.sh && infra/restore.sh backups/latest.enc # backup (ikinci hosta göndərilir) və bərpa
python tools/loadtest.py --scenario exam --users 500 --dataset university   # yük testi
```

## Project Structure

```
backend/                        Python
  zeka/
    core/                       platforma: web, router, config, clock, db, migrate, security, perms, tenant, i18n, audit, events, jobs
    modules/
      <modul-id>/
        domain.py               qaydalar və hesablamalar; I/O yoxdur
        service.py              istifadə halları; modulun xarici müqaviləsi
        repo.py                 SQL yalnız burada
        routes.py               giriş-çıxış: sorğunu oxu, service çağır, cavabı formalaşdır
    legacy/                     köçürülmüş r_*.py; davranış dəyişmir, modul-modul boşaldılır
  migrations/                   0001_baseline.sql, 0070_shared_state.sql, 0100_identity.sql, ... (NNNN = tapşırıq nömrəsi × 10)
  run.py  manage.py
frontend/                       JavaScript, CSS, HTML
  index.html  exam.html
  js/  css/  locales/  img/  fonts/
exam/                           SEB konfiqurasiya şablonu (XML plist)
infra/                          Dockerfile, compose.yml, Caddyfile, backup.sh, restore.sh
content/  i18n/                 məzmun və tərcümə mənbələri
tools/                          i18n, loadtest, miqrasiya ETL
tests/                          unit/  integration/  security/  e2e/  load/  migration/  eval/  fixtures/
docs/                           CODEMAP, hesabat, arxitektura, API, təhlükəsizlik, runbook
tasks/                          plan.md, todo.md
```

Asılılıq istiqaməti: `routes` → `service` → `domain`; `service` → `repo`.
`domain.py` heç nə idxal etmir: nə `core.web`, nə `core.db`. Bu qayda testlə yoxlanır (T03).

## Code Style

Mövcud konvensiyalar saxlanır: `@R(...)` dekoratoru, Azərbaycan dilində `HTTPError` mesajı tərcümə açarı kimi,
parametrli SQL, id qəbul edən hər handler-də giriş yoxlaması.

```python
# backend/zeka/modules/exam/domain.py — qayda; I/O yoxdur, ona görə vahid testlə tam örtülür
def deadline(started_at: datetime, minutes: int, extra_minutes: int, window_end: datetime) -> datetime:
    """Tələbənin fərdi son vaxtı: öz müddəti qədər, amma imtahan pəncərəsindən gec deyil."""
    return min(started_at + timedelta(minutes=minutes + extra_minutes), window_end)


# backend/zeka/modules/exam/service.py — istifadə halı
def save_answer(exams: Exams, user: dict, attempt_id: int, qid: int, value: str, at: datetime) -> dict:
    a = exams.attempt_for(attempt_id, user["id"])            # tapılmasa 404, başqasınındırsa 404
    if at > deadline(a.started_at, a.minutes, a.extra_minutes, a.window_end):
        raise HTTPError(409, "İmtahan vaxtı bitib")
    exams.put_answer(a.id, qid, value, at)                   # tək UPSERT; cavab açarı oxunmur
    return {"saved_at": iso(at)}


# backend/zeka/modules/exam/routes.py — yalnız giriş-çıxış
@R("PUT", "/api/exam/attempts/{id:int}/answers/{qid:int}", roles=("student",), scope="exam")
def put_answer(req):
    return service.save_answer(Exams(req.db), req.user, req.params["id"], req.params["qid"],
                               req.body.str("value", max_len=4000), now())
```

Qaydalar:

- İstifadəçiyə görünən hər sətir `t()` və ya `T3()/E()` ilə bükülür. Sonra `extract`, tərcümə, `build`.
- Şərh yalnız kodun göstərə bilmədiyi səbəbi yazır, bir sətirdə.
- Bilinən həddi olan qısa yol belə işarələnir: `# shortcut: <hədd>, <nə vaxt dəyişməli>`.
- Yeni iş vaxtı asılılığı yalnız icazə ilə.
- Köhnə kod köçürüləndə xəta idarəsi və yoxlamaları onunla gedir.

## Testing Strategy

| Səviyyə | Nə yoxlayır | Harada | Hədəf |
|---|---|---|---|
| Vahid | `domain.py` qaydaları: son vaxt, qiymət, buraxılış, variant, Config Key | `tests/unit/` | Yeni `domain` kodunda 90% sətir |
| İnteqrasiya | Real HTTP serveri, müvəqqəti baza, hər əsas axın | `tests/integration/` | Hər modulun əsas axını |
| Təhlükəsizlik | Rol × marşrut matrisi marşrut cədvəlindən avtomatik; imtahan sessiyasının bütün marşrutlara qarşı fuzzu; CSRF; limit | `tests/security/` | Hər marşrut matrisdədir |
| Miqrasiya | Sxem miqrasiyaları v4 demo bazasından; ETL nümunə ixraclarla; uzlaşdırma | `tests/migration/` | Sətir sayı və yoxlama cəmi bərabər |
| E2E | Playwright: T13-dəki hər rol × 3 dil × masaüstü və mobil; imtahan axını | `tests/e2e/` | Hər rol üçün tüstü testi |
| Yük | İmtahan 500 paralel, gündəlik 1 000 paralel; proses öldürmə | `tests/load/`, `tools/loadtest.py` | p95 < 500 ms, 0 itki (`university` dəsti; buraxılışda hədəf serverdə) |
| AI | 50 suallıq Azərbaycanca dəst: mənbə düzgünlüyü, bilmədikdə imtina | `tests/eval/` | Mənbə düzgünlüyü ≥ 90% |

Qapılar: yaşıl test olmadan birləşdirmə yoxdur. Test yaşıl olsun deyə zəiflədilmir, keçilmir, silinmir.
Hər tapşırığın `Verification` bəndi var (`tasks/todo.md`).

Kod rəyi: hər mərhələdən sonra altı rəyçi (kod, təhlükəsizlik, səssiz xəta, test, Python, təhlükəsizlik auditi).
Hər tapıntını ayrı agent təkzib etməyə çalışır. Yalnız təkzib olunmayan düzəldilir.

## Boundaries

**Həmişə**

- Commit-dən əvvəl testlər, lint, tip yoxlaması.
- Sxem dəyişikliyi yalnız irəli gedən nömrəli miqrasiya ilə; birləşdirilmiş miqrasiya faylı redaktə edilmir; miqrasiyadan əvvəl avtomatik backup.
- Hər yeni marşrut rol və obyekt səviyyəli giriş yoxlaması ilə, təhlükəsizlik matrisində.
- Təhlükəsizlik hadisələri audit jurnalına: giriş, uğursuz giriş, rol dəyişməsi, qiymət dəyişməsi, ixrac, admin əməliyyatı, başqasının şəxsi məlumatının oxunması (sənəd, əlavə fayl, qiymət siyahısı, risk profili).
- Hər sətir üç dildə.

**Əvvəl soruş**

- Commit və push. `main`-ə toxunan hər şey.
- Yeni iş vaxtı asılılığı. Mövcud cədvəllərin sütununu dəyişən və ya silən miqrasiya.
- Real məlumat üzərində geri qaytarılmayan əməliyyat: silmə, kəsid, kütləvi yeniləmə.
- Giriş axınının dəyişdirilməsi. Xarici LLM-in açılması.

**Heç vaxt**

- Repoda sirr. Prod rejimində parolsuz yol.
- Razılıqsız şəxsi məlumatın xarici xidmətə göndərilməsi.
- Kamera, səs və ya üz ilə proktorinq.
- "NIST sertifikatlı", "aldadılması mümkün olmayan" kimi sübutsuz iddia.
- İmtahan hovuzundakı sualın mətninin, açarının və ya izahının imtahan cəhdindən kənar hər hansı marşrutla (tutor, məşq testi, Radar, ixrac) tələbəyə getməsi; balın nəticə açıqlanmadan getməsi.

## Success Criteria

V1 o zaman hazırdır ki, aşağıdakıların hamısı testlə və ya ölçmə ilə təsdiqlənsin.

| Modul | Meyar |
|---|---|
| `platform` | Sxem miqrasiyası məlumat itirmir (sətir sayı bərabər). Gecəlik şifrəli backup yazı yükü altında tamamlanır və ölkə daxilində ikinci hosta göndərilir; RPO 24 saat, imtahan günü imtahan bağlananda əlavə backup; bərpa sınağı CI-da keçir, bərpa müddəti ölçülüb. Demo bazada qapının reqressiya yoxlaması: 300 paralel müştəridə 0 xəta, tək prosesdə ≥ 200 sorğu/san. Tutum: `university` dəstində, hədəf serverdə gündəlik qarışıq 1 000 istifadəçi p95 < 500 ms, 5xx 0. Dövri işlər (saxlama təmizliyi, xatırlatmalar, dərs yaradılması, imtahan cəhdinin avtomatik təslimi, Radar görüntüsü) intervalı keçəndə düz bir dəfə işləyir; son icra `job_runs`-dadır. |
| `identity` | Prod rejimində `/api/auth/demo` və `/api/admin/reset` 404 verir. Parol yaddaş-ağır hash ilə; uzunluq tək amildə ≥ 15, MFA ilə ≥ 8; tərkib qaydası yoxdur. İşçi rolları TOTP-suz girə bilmir. İşçi sessiyası: 1 saat boş, 24 saat mütləq. Rol × marşrut matrisində icazəsiz hər xana 403. `office` yalnız öz fakültəsinin tələbəsinin müraciətini, sənədini və əlavə faylını açır; başqa fakültəninki 404. Başqasının sənədinin, əlavə faylının, qiymət siyahısının və risk profilinin oxunması auditdədir. |
| `directory` | 10 000 tələbəlik idxal 60 saniyədən tez; təkrar işlədikdə 0 dəyişiklik; səhv sətirlər sətir nömrəsi ilə hesabatda. Əmr nömrəsi, əmr tarixi və qüvvəyə minmə tarixi olmadan tələbənin statusu dəyişmir; akademik məzuniyyət və xaric qüvvəyə minmə tarixindən sonrakı dərs siyahılarından tələbəni çıxarır, əvvəlki davamiyyət və ballar qalır; məzuniyyətdəki tələbə hesabına girir və öz sənədlərini görür. |
| `facilities`, `timetable` | Otaq, müəllim və qrup toqquşması saxlanmır. Hər otağın QR səhifəsi indiki və növbəti dərsi göstərir. iCal lenti Outlook və Google Calendar-da açılır. |
| `journal` | Müəllim 30 nəfərlik dərsin davamiyyətini bir ekranda qeyd edir. Effektiv hədd = min(tenant həddi, dərc olunmuş sillabusun həddi); keçən tələbə "imtahana buraxılmır" statusu alır. Komponent cəmi 100 deyilsə sxem saxlanmır. Hər qiymət dəyişikliyi səbəb və müəlliflə jurnaldadır. |
| `syllabus` | Təsdiq zənciri: müəllim → kafedra müdiri → tədris şöbəsi. Dərc fənnin qiymət komponentlərini, davamiyyət həddini və tutor rejimini dəyişir. Sillabus davamiyyət həddini yalnız aşağı sala bilər: tenant həddindən yuxarı dəyər saxlanmır. NICE Components v2.2.0 idxal olunur; nəticə üzrə əhatə hesabatı çıxır. |
| `learning` | Tapşırıq: müəllim dərc edir, tələbə fayl göndərir, müəllim qiymətləndirir, bal jurnala düşür. Müəllimin yüklədiyi materialın orijinal faylını fənnə yazılmış tələbə endirir; əvəzlənən materialın əvvəlki versiyası qalır. |
| `exam` | İmtahan sessiyası ilə imtahandan kənar hər marşrut, adi sessiya və ya başqa imtahanın sessiyası ilə hər imtahan marşrutu 403 (bütün marşrut cədvəli üzrə avtomatik test). Son vaxtdan sonra cavab qəbul olunmur. İmtahana giriş tələbənin başqa sessiyalarını bağlayır; cəhd gedərkən adi giriş imtahan sessiyasını bağlamır. `allowed_cidrs`-dən kənar sorğu cəhd ortasında da rədd olunur. Şəbəkə kəsiləndən sonra cavablar yerində qalır. Config Key hesablaması SEB Config Tool-un göstərdiyi açarla üst-üstə düşür. 500 paralel imtahan verəndə p95 < 500 ms, itki 0 (`university` dəsti; buraxılışda hədəf serverdə). |
| `assistant` | 50 sualdan ≥ 45-də düzgün mənbə. Otaq sorğusuna cavab 2 saniyədən tez. Mənbə tapılmayanda insana ötürür. |
| `qa` | Sual yalnız fənnə yazılanlara görünür. Anonim sualın müəllifini fənnin müəllimi və `qa.moderate` icazəsi olan görür, tələbələr görmür. |
| `services` | Verilmiş sənəd verilmə anında saxlanmış yükdən göstərilir: sonradan dəyişən ad, qrup və ya bal onu dəyişmir. `/verify` hash-i saxlanmış yükdən yenidən hesablayır və uyğunsuzluqda "sənəd dəyişdirilib" göstərir. Reyestr nömrəsi paralel verilmədə təkrarlanmır və boşluqsuzdur. Hər təsdiq addımını yalnız həmin addıma təyin olunmuş rol irəli aparır. Cavab mətni təsir iddia edən növ həmin təsiri icra edir; etməyənin cavabı faktiki şablondur. Prod rejimində yalnız adminin açdığı müraciət növləri təklif olunur. |
| `community` | Mesaj yalnız üzvlərə görünür. Şikayət olunan mesaj `community.moderate` icazəsi olanların növbəsinə düşür. Hər moderasiya addımı auditdədir. |
| `comms` | E-poçt növbəsi: uğursuz göndəriş təkrar cəhd edir; istifadəçi kanalı bağlaya bilir. |
| `insight` | Paneldə kodda sabit yazılmış göstərici qalmır; hər rəqəm hadisə jurnalından hesablanır. |
| `migration` | T0 ixracına qarşı, idxal olunan hər cədvəl üçün mənbə sayı = mənbə ilə bağlı (`import_links`) hədəf sətirlərinin sayı; fərq 0 və ya sətir-sətir izahlıdır. Zəka-da yaradılan sətir fərq sayılmır. Zəka-da dəyişdirilmiş sətir təkrar idxalda üstünə yazılmır, konflikt hesabatına düşür. |

## Out of Scope (Deferred)

- SİMA və ya ASAN İmza ilə imzalanan sənəd: təminatçı ilə müqavilə tələb edir.
- mygov ID ilə giriş: İRİA ilə razılaşma tələb edir.
- TMİS və "Tələbə-məzun" sistemi ilə birbaşa inteqrasiya: açıq API tapılmayıb; V1-də fayl ixracı (T37: reyestr ixracı və "Tələbə-məzun" dəyişiklik siyahısı).
- Postgres: bir fakültədən sonrakı dalğada, `university` yük testi hədəf serverdə p95 < 500 ms-i tutmayanda.
- LTI 1.3 və SAML: XML imzası və RS256 ilə imzalama üçün asılılıq icazəsi lazımdır.
- Mobil tətbiq və oflayn PWA.
- Təhsil haqqı ödənişi, yataqxana idarəsi, kitabxana fondu: V1-də yalnız müraciət forması səviyyəsində.
- Qəbul kampaniyası və kadr sistemi.
- Fənnin təkrar dinlənməsi üçün yenidən qeydiyyat, yay semestri və ödənişli təkrar: V1-də köhnə sistemdə.
- Tədris planı (ixtisas × qəbul ili × semestr × fənn × kredit × məcburi/seçmə × prerekvizit), fərdi tədris planı, seçmə fənn qeydiyyatı (tyutor və ya dekanlıq təsdiqi), kredit yükü həddi: V1-də yoxdur. V1-də qeydiyyat köhnə sistemdən `classes` və `enrollments` idxalı ilə gəlir. Akademik borc V1-də yalnız siyahıdır (T21); təkrar fənnin qeydiyyatı əvvəlki bənddədir. Dalğa 3-ün şərtidir (`tasks/plan.md`).
- Müraciət növlərinin, formalarının və addımlarının admin redaktoru: V1-də yoxdur. V1-də onlar rəydən keçən data miqrasiyası ilə dəyişir (T46); admin yalnız növü açır və bağlayır.
- AI ilə qiymətləndirmə: yüksək riskli istifadə; müəllim qərarı olmadan heç vaxt.
- Öz lockdown brauzerimiz; Android, ChromeOS, Linux-da SEB (rəsmi versiya yoxdur).

## Open Questions

1. AMAS və DrSys nə edir, əvəz olunurmu? Köhnə sistemlərin tam siyahısı və sahibləri.
2. Köhnə sistemlərdən ixrac: format, sahələr, tarixi məlumatın həcmi, kim verir. Köhnə sistem idxal qəbul edirmi, modul-modul yalnız oxunan rejimə keçirilə bilirmi, bunu kim edir; gecəlik ixracı kim verir? Cari semestrin davamiyyəti dərs səviyyəsində, yoxsa yalnız yekun kimi ixrac olunur? Cari ballar köhnə sistemdədir, yoxsa müəllimin kağız və ya Excel jurnalında? Cavab davamiyyət idxalının formasını (`attendance` və ya `attendance-opening`, T38) seçir və cari balların ETL ilə, yoxsa müəllimin yapışdırması ilə (T21) gəldiyini müəyyən edir.
3. Hostinq: AzTU data mərkəzi, AzInTelecom, yoxsa başqası. Server ölçüsü. Sınaq nüsxəsinin DNS adı; sertifikat üsulu (ACME və ya AzTU-nun verdiyi sertifikat).
4. `sso.aztu.edu.az` hansı protokolla işləyir: OIDC, SAML, CAS.
5. İmtahan auditoriyaları: kompüter sayı, əməliyyat sistemi, alt şəbəkə (CIDR) və oradan serverin 443 portuna çıxış.
6. LLM: oflayn mühərrik kifayətdir, yoxsa xarici və ya yerli model qoşulur.
7. Qiymət sxemi bütün fənlər üçün eynidir, yoxsa fənn üzrə dəyişir.
8. "Sillabus üçün NIST": NICE Framework xəritəsi və platformanın NIST nəzarətləri kimi başa düşmüşəm. Düzdür?
9. İlk dalğanın fakültəsi, fənləri, başlama tarixi və kəsid tarixi (`journal.cutover_date` ayarı, T17; idxalda `as_of`). Dalğa 0-da yazı sistemi (müəllim hər iki sistemə, yoxsa yalnız Zəka-ya yazır): sual 19.
10. Maddə 8 üzrə razılıq forması və maddə 15 üzrə qeydiyyat: AzTU hüquqşünasının rəyi. Razılıq forması, saxlama, tələbə bileti nömrəsi və xarici AI üzrə qərarları sahibin tapşırığı ilə 2026-11-21-də verdim (`docs/privacy/data-inventory.md`, "Qərarlar"). Maddə 15 üzrə qeydiyyat açıq qalır.
11. İmtahan sualının açarı və izahı nəticə açıqlanandan sonra tələbəyə göstərilirmi (məsələn, apellyasiyada)? Susmaya görə V1-də yox: baxış müəllimin ekranında aparılır (T26).
12. İmtahan cəhdi gedərkən adi giriş imtahan sessiyasını bağlamır; cəhdi yalnız T28 və T29 yoxlamalarından keçən yeni imtahana giriş götürür (T27). Təsdiqlənirmi? Alternativdə (son giriş qalib gəlir) parolu bilən hər kəs imtahan verəni sessiyadan çıxarır.
13. TOTP toxumu bazada açıq saxlanır; risk T41 təhdid modelində qəbul edilmiş kimi yazılır (T12). Toxumu mühit açarı ilə şifrələmək üçün `cryptography` icazəsi verilirmi?
14. Mühazirə axınla, məşğələ qrupla, laboratoriya yarımqrupla keçilirmi; mühazirə və məşğələ müəllimi fərqlidirmi? Tədris vahidi modeli (T15) cavabdan asılı olmayaraq qəbul olunur: bir müəllimli, bir siyahılı fənn onun xüsusi halıdır.
15. AzTU-nun rəsmi akademik təqvimi: son tədris günü və sessiya tarixləri. Üzrlü qayıb 25%-ə sayılırmı? Ləğv olunmuş dərs məxrəcdə qalırmı? Davamiyyətin 10 balı buraxılmış saatdan hansı qayda ilə çıxarılır? Cavaba qədər Assumptions 10 və 11 qüvvədədir (T15, T17, T20, T21).
16. Təkrar imtahan qaydası: neçə dəfə, nə vaxt, imtahanaqədərki bal saxlanırmı; imtahan-qiymət cədvəlini kim imzalayır (T26, T30).
17. Status əmrlərini (akademik məzuniyyət, xaric, köçürmə, bərpa) Zəka-ya kim daxil edir: öz fakültəsi üzrə `office` (dekanlıq), yoxsa yalnız `academic_office`? Susmaya görə yalnız `academic_office` (T15). "Tələbə-məzun" üçün 10 günlük müddət əmr tarixindən sayılırmı (225 nömrəli Fərmanla yoxlanmalıdır; T37)? Sahib status əmrlərini sprintdən çıxarsa, `tasks/plan.md`-dəki alternativ qüvvəyə minir: kontingent əmrləri dalğa 3-ə qədər köhnə sistemdə yazılır.
18. 2026/27 yaz semestrinin fənn qeydiyyatı harada aparılır: KOICA Academic-də (sonra ixrac), yoxsa Zəka-da? 348 nömrəli qərarın fərdi tədris planı və kredit həddi (40 kredit: mənbə təsdiqlənməyib) AzTU-da necə tətbiq olunur?
19. "Qeydin sahibi" cədvəli (`tasks/plan.md`) təsdiqlənirmi? Dalğa 0-da davamiyyət və cari ballar üçün hansı variant: A (köhnə sistem əsasdır, pilot müəllimlər T1-ə qədər hər iki sistemə yazır, fərqdə köhnə sistemin dəyəri qalır) və ya B (T0-dan Zəka; köhnə sistemə daxiletmə dekan əmri ilə dayanır)? Qərara qədər A qüvvədədir. Dalğa 2-də imtahan nəticəsini köhnə sistemin imtahan moduluna kim yazır? Kəsiddən sonra geri qayıtma pəncərəsi neçə gündür (susmaya görə 14)? (T16, T38, T43)
20. Backup: ölkə daxilində ikinci host hansıdır; şifrələmə açarının serverdən kənar iki nüsxəsi kimdə saxlanır (təklif: sahib və AzTU İT)? İmtahan günü RPO: imtahan bağlananda backup kifayətdir, yoxsa imtahan zamanı dövri backup lazımdır? İkinci halda T42 imtahan yük testi backup işləyərkən p95 < 500 ms verməlidir. RPO qərarı dalğa 2-dən əvvəl verilir; o vaxta qədər RPO 24 saatdır və imtahan bağlananda əlavə backup alınır (T08, T43, T44).
21. Parol hash-inin xərci: susmaya görə scrypt n=2^15, r=8, p=1 (T10). n=2^17 seçilirmi (ölçülüb: hər hash 323 ms və 128 MiB)? Seçilsə, T42-nin 60 saniyədə 500 giriş ssenarisi həmin parametrlə keçməlidir.
22. Vaxtın saxlanması (`tasks/plan.md` A19): yeni cədvəllər anı UTC-də, ofsetlə saxlayır. Ucuz variant: bütün sütunlar eyni saatın (`core/clock.py`) arxasında Asia/Baku lokal qalır, ofseti yalnız dəyişməz qeydlər (`exam_events`, qiymət jurnalı, audit) yazır; sabit +04:00 qurşağı üçün düzgündür. Hansı seçilir? Qərar T10-dan əvvəl verilir və A19-da yazılır; qərara qədər UTC variantı qüvvədədir.
23. Yük həddi: `faculty` dəstində tək prosesin oxu ssenarisi demo nəticəsinin ≥ 60%-ni verməlidir (T07). Hədd ölçmədən götürülüb (yalnız indekslərlə 241-ə qarşı 171 sorğu/san; indekssiz 62). Sahib həddi dəyişə bilər.
24. Rol cədvəli (T13) təsdiqlənirmi? Dekanlığın rol id-si `office` qalır (kodda var, miqrasiya tələb etmir). Susmaya görə `qa.moderate`: `office`, `admin`; `community.moderate`: klubun rəhbəri (öz klubunda), `office`, `admin`. Bu bölgü anonim sualın müəllifini kimin gördüyünü müəyyən edir. Sahib `dean_office` adını istəsə, T13-ə üçüncü dilim əlavə olunur: `legacy/{common,r_services,r_support,r_radar,r_core}.py`, `frontend/js/{shell,services,support,news,radar,demo}.js`, `tests/conftest.py` və `office` fiksturunu işlədən testlər, `content/seed.json`, `content/guide.json` dəyişir (təxminən 23 Python, 25 JS, 100 test sətri) və `UPDATE users SET role='dean_office' WHERE role='office'` miqrasiyası əlavə olunur. Qərar Checkpoint B-də (saat 22) verilir; qərara qədər `office` qüvvədədir.
25. Marşrut qrafını kim hazırlayır? Susmaya görə T31 düyün və til CSV-sini sahibin verdiyi mərtəbə planlarından qaralayır, sahibin təyin etdiyi şəxs 5 marşrutu yerində yoxlayır. Alternativ: CSV-ni AzTU əməkdaşı doldurur; onda T18-ə boş CSV şablonu əlavə olunur. Qərar saat 22-də verilir.
