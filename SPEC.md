# Spec: Zəka — AzTU vahid universitet portalı — V1

Vəziyyət: **təsdiq gözləyir** · Tarix: 2026-11-16 · Baza: `main @ a59ef1f` + beş açıq PR
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
| KOICA Academic, kabinetlər | `directory`, `journal` | Müəllim jurnalı dərsdə telefonla doldurur; 25% həddi və imtahana buraxılış avtomatik hesablanır |
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
10. Semestr tarixləri `content/seed.json`-dakı kimidir (15.09.2026 – 31.01.2027). Rəsmi təqvimlə yoxlanmayıb.

## Capability Map

Modul id-ləri sabitdir. Asılılıq bir istiqamətlidir, dövr yoxdur.

| Modul id | Məsuliyyət | Asılıdır | Kodda bu gün |
|---|---|---|---|
| `platform` | HTTP, konfiqurasiya, baza, miqrasiya, backup, log, i18n, tenant ayarları, fon işləri | — | Qismən: HTTP, i18n var; miqrasiya, backup, iş növbəsi yoxdur |
| `identity` | Hesab, parol, MFA, sessiya, rol və icazə, SSO, audit | `platform` | Yoxdur (yalnız demo rol girişi) |
| `directory` | Fakültə, kafedra, ixtisas, qrup, istifadəçi, fənn, qeydiyyat; idarəetmə və idxal | `identity` | Yalnız seed; yazma yolu yoxdur |
| `facilities` | Korpus, mərtəbə, otaq, marşrut qrafı, otaq QR-i | `platform` | Yoxdur (otaq cədvəldə mətn sahəsidir) |
| `timetable` | Cədvəl, dərs, otaq bölgüsü, toqquşma yoxlaması, iCal | `directory`, `facilities` | Yalnız göstərmə; yazma yolu yoxdur |
| `journal` | Davamiyyət və qiymət jurnalı, qiymət sxemi, imtahana buraxılış, yekun qiymət | `timetable` | Yalnız göstərmə; müəllim yaza bilmir |
| `syllabus` | Struktur sillabus, çərçivə xəritəsi, təsdiq, versiya, fənnin konfiqurasiyası | `directory` | Qismən: generasiya, saxlama, çap var |
| `learning` | Material, tapşırıq, AI tutor, test studiyası, məşq testi | `directory`, `syllabus` | Var; tapşırıq axını yoxdur |
| `exam` | İmtahan, variant, taymer, SEB, nəzarətçi paneli, protokol | `learning`, `identity`, `facilities` | Yoxdur (məşq testi var) |
| `assistant` | Kampus köməkçisi: bilik bazası, otaq tapma, əməliyyat, insana ötürmə | `facilities`, `timetable`, `services` | Qismən: bilik bazası və əməliyyat var |
| `qa` | Müəllimə sual, fənn forumu, qəbul saatları | `directory`, `learning` | Qismən: müəllimə yönləndirmə var |
| `services` | E-xidmət, sənəd, QR doğrulama, apellyasiya | `identity`, `journal` | Var; sənədlər sintetik qiymətə əsaslanır |
| `community` | Klublar, kanallar, mesaj, moderasiya | `identity` | Yoxdur |
| `comms` | Bildiriş (tətbiqdaxili, e-poçt), xəbər, tədbir | `identity` | Qismən: e-poçt yoxdur |
| `radar` | Erkən xəbərdarlıq, dəstək planı | `journal`, `learning` | PR #4-də |
| `insight` | Hadisə jurnalı, ölçülmüş göstəricilər, akkreditasiya sübut paketi, sorğu | hamısı | Qismən: bəzi rəqəmlər sabit yazılıb |
| `integration` | İdxal və ixrac, iCal, SSO bağlantıları, API açarı, webhook, tətbiq paneli | `directory` | Yoxdur |
| `migration` | Köhnə sistemlərdən ETL, uzlaşdırma, kəsid | `directory`, `journal` | Yoxdur |
| `support` | Dəstək masası, rəy | `identity` | Var |

Qurulma sırası:
`platform` → `identity` → `directory` → `facilities`, `timetable` → `journal` → `syllabus`, `learning` → `exam`
→ `assistant`, `qa`, `services` → `community`, `comms` → `radar`, `insight` → `integration`.
`migration` kəşf mərhələsi ilə birinci gündən paralel gedir.

Modullararası müqavilə təminatçı modulun `service.py` faylındadır. Başqa modul onun `repo.py`-sinə və cədvəllərinə birbaşa toxunmur.

## Tech Stack

| Qat | Seçim | Əsas |
|---|---|---|
| Backend | Python 3.12+, yalnız standart kitabxana | 5 500 sətir işləyən kod; sıfır asılılıq universitet serverində quraşdırmanı sadələşdirir |
| HTTP | Mövcud `http.server` qatı (PR #3 və #5 düzəlişləri ilə), qabağında Caddy 2 | Caddy TLS-i, HTTP normallaşdırmanı və ölçü həddini götürür |
| Paralellik | Proses başına eyni anda ən çox 2 handler, nüvə başına bir proses | Ölçülüb: 47 → 226 sorğu/san, 300 müştəridə 0 xəta |
| Baza | SQLite WAL, nömrələnmiş SQL miqrasiyalar | Bir fakültə üçün kifayətdir; Postgres-ə keçid `repo.py` sərhədi ilə hazırlanır |
| Frontend | Sadə ES modulları, mövcud dizayn sistemi | Sahibin tələbi: mövcud interfeys qalır |
| İmtahan müştərisi | Safe Exam Browser 3.x (MPL-2.0) | Öz brauzerimizi yazmırıq |
| AI | Oflayn BM25 mühərriki; istəyə görə LLM | Maddə 14: məlumat susmaya görə ölkədə qalır |
| Yerləşdirmə | Docker, Compose | Bir əmrlə quraşdırma və bərpa |
| İnkişaf alətləri | pytest, ruff, mypy, Playwright | PR #5-dən gəlir |

Dillər: Python, JavaScript, CSS, HTML, SQL, shell, YAML. Hər dil öz kök qovluğundadır.
Java V1-də yoxdur: ikinci backend dili ikinci iş mühiti və ikinci təhlükəsizlik səthi deməkdir, V1-də onu tələb edən komponent yoxdur.

İcazə tələb edən mümkün asılılıqlar: `cryptography` (SAML və ya RS256 imza yoxlaması lazım olsa), `psycopg` (Postgres mərhələsində).

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
python backend/manage.py import --kind students --file students.csv --dry-run
python backend/manage.py reconcile --wave 1            # mənbə və hədəf uzlaşdırması
infra/backup.sh && infra/restore.sh backups/latest.enc # backup və bərpa
python tools/loadtest.py --scenario exam --users 500   # yük testi
```

## Project Structure

```
backend/                        Python
  zeka/
    core/                       platforma: web, router, config, db, migrate, security, i18n, audit, events, jobs
    modules/
      <modul-id>/
        domain.py               qaydalar və hesablamalar; I/O yoxdur
        service.py              istifadə halları; modulun xarici müqaviləsi
        repo.py                 SQL yalnız burada
        routes.py               giriş-çıxış: sorğunu oxu, service çağır, cavabı formalaşdır
    legacy/                     köçürülmüş r_*.py; davranış dəyişmir, modul-modul boşaldılır
  migrations/                   0001_baseline.sql, 0002_identity.sql, ...
  run.py  manage.py
frontend/                       JavaScript, CSS, HTML
  index.html  exam.html
  js/  css/  locales/  img/  fonts/
exam/                           SEB konfiqurasiya şablonu (XML plist)
infra/                          Dockerfile, compose.yml, Caddyfile, backup.sh, restore.sh
content/  i18n/                 məzmun və tərcümə mənbələri
tools/                          i18n, loadtest, miqrasiya ETL
tests/                          unit/  integration/  security/  e2e/  load/  migration/
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
| Miqrasiya | Sxem miqrasiyaları v3 demo bazasından; ETL nümunə ixraclarla; uzlaşdırma | `tests/migration/` | Sətir sayı və yoxlama cəmi bərabər |
| E2E | Playwright: 5 rol × 3 dil × masaüstü və mobil; imtahan axını | `tests/e2e/` | Hər rol üçün tüstü testi |
| Yük | İmtahan 500 paralel, gündəlik 1 000 paralel; proses öldürmə | `tests/load/`, `tools/loadtest.py` | p95 < 500 ms, 0 itki |
| AI | 50 suallıq Azərbaycanca dəst: mənbə düzgünlüyü, bilmədikdə imtina | `tests/eval/` | Mənbə düzgünlüyü ≥ 90% |

Qapılar: yaşıl test olmadan birləşdirmə yoxdur. Test yaşıl olsun deyə zəiflədilmir, keçilmir, silinmir.
Hər tapşırığın `Verification` bəndi var (`tasks/todo.md`).

Kod rəyi: hər mərhələdən sonra altı rəyçi (kod, təhlükəsizlik, səssiz xəta, test, Python, təhlükəsizlik auditi).
Hər tapıntını ayrı agent təkzib etməyə çalışır. Yalnız təkzib olunmayan düzəldilir.

## Boundaries

**Həmişə**

- Commit-dən əvvəl testlər, lint, tip yoxlaması.
- Sxem dəyişikliyi yalnız irəli gedən nömrəli miqrasiya ilə; miqrasiyadan əvvəl avtomatik backup.
- Hər yeni marşrut rol və obyekt səviyyəli giriş yoxlaması ilə, təhlükəsizlik matrisində.
- Təhlükəsizlik hadisələri audit jurnalına: giriş, uğursuz giriş, rol dəyişməsi, qiymət dəyişməsi, ixrac, admin əməliyyatı.
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
- Cavab açarının imtahan bağlanmadan müştəriyə göndərilməsi.

## Success Criteria

V1 o zaman hazırdır ki, aşağıdakıların hamısı testlə və ya ölçmə ilə təsdiqlənsin.

| Modul | Meyar |
|---|---|
| `platform` | Sxem miqrasiyası məlumat itirmir (sətir sayı bərabər). Gecəlik şifrəli backup; bərpa sınağı CI-da keçir. 300 paralel müştəridə 0 xəta; tək prosesdə ≥ 200 sorğu/san. |
| `identity` | Prod rejimində `/api/auth/demo` və `/api/admin/reset` 404 verir. Parol yaddaş-ağır hash ilə; uzunluq tək amildə ≥ 15, MFA ilə ≥ 8; tərkib qaydası yoxdur. İşçi rolları TOTP-suz girə bilmir. İşçi sessiyası: 1 saat boş, 24 saat mütləq. Rol × marşrut matrisində icazəsiz hər xana 403. |
| `directory` | 10 000 tələbəlik idxal 60 saniyədən tez; təkrar işlədikdə 0 dəyişiklik; səhv sətirlər sətir nömrəsi ilə hesabatda. |
| `facilities`, `timetable` | Otaq, müəllim və qrup toqquşması saxlanmır. Hər otağın QR səhifəsi indiki və növbəti dərsi göstərir. iCal lenti Outlook və Google Calendar-da açılır. |
| `journal` | Müəllim 30 nəfərlik dərsin davamiyyətini bir ekranda qeyd edir. 25% həddi tenant ayarındandır; keçən tələbə "imtahana buraxılmır" statusu alır. Komponent cəmi 100 deyilsə sxem saxlanmır. Hər qiymət dəyişikliyi səbəb və müəlliflə jurnaldadır. |
| `syllabus` | Təsdiq zənciri: müəllim → kafedra müdiri → tədris şöbəsi. Dərc fənnin qiymət komponentlərini, davamiyyət həddini və tutor rejimini dəyişir. NICE Components v2.2.0 idxal olunur; nəticə üzrə əhatə hesabatı çıxır. |
| `learning` | Tapşırıq: müəllim dərc edir, tələbə fayl göndərir, müəllim qiymətləndirir, bal jurnala düşür. |
| `exam` | İmtahan sessiyası ilə imtahandan kənar hər marşrut 403 (bütün marşrut cədvəli üzrə avtomatik test). Son vaxtdan sonra cavab qəbul olunmur. Eyni tələbənin ikinci sessiyası birincini bağlayır. Şəbəkə kəsiləndən sonra cavablar yerində qalır. Config Key hesablaması SEB Config Tool-un göstərdiyi açarla üst-üstə düşür. 500 paralel imtahan verəndə p95 < 500 ms, itki 0. |
| `assistant` | 50 sualdan ≥ 45-də düzgün mənbə. Otaq sorğusuna cavab 2 saniyədən tez. Mənbə tapılmayanda insana ötürür. |
| `qa` | Sual yalnız fənnə yazılanlara görünür. Anonim sualın müəllifini müəllim və moderator görür, tələbələr görmür. |
| `community` | Mesaj yalnız üzvlərə görünür. Şikayət olunan mesaj moderator növbəsinə düşür. Hər moderasiya addımı auditdədir. |
| `comms` | E-poçt növbəsi: uğursuz göndəriş təkrar cəhd edir; istifadəçi kanalı bağlaya bilir. |
| `insight` | Paneldə kodda sabit yazılmış göstərici qalmır; hər rəqəm hadisə jurnalından hesablanır. |
| `migration` | İdxal olunan hər cədvəl üçün mənbə sayı = hədəf sayı; fərq 0 və ya sətir-sətir izahlıdır. |

## Out of Scope (Deferred)

- SİMA və ya ASAN İmza ilə imzalanan sənəd: təminatçı ilə müqavilə tələb edir.
- mygov ID ilə giriş: İRİA ilə razılaşma tələb edir.
- TMİS və "Tələbə-məzun" sistemi ilə birbaşa inteqrasiya: açıq API tapılmayıb; V1-də fayl ixracı.
- Postgres: bir fakültədən sonrakı dalğada, ölçmə tələb edəndə.
- LTI 1.3 və SAML: RS256 imza yoxlaması üçün asılılıq icazəsi lazımdır.
- Mobil tətbiq və oflayn PWA.
- Təhsil haqqı ödənişi, yataqxana idarəsi, kitabxana fondu: V1-də yalnız müraciət forması səviyyəsində.
- Qəbul kampaniyası və kadr sistemi.
- AI ilə qiymətləndirmə: yüksək riskli istifadə; müəllim qərarı olmadan heç vaxt.
- Öz lockdown brauzerimiz; Android, ChromeOS, Linux-da SEB (rəsmi versiya yoxdur).

## Open Questions

1. AMAS və DrSys nə edir, əvəz olunurmu? Köhnə sistemlərin tam siyahısı və sahibləri.
2. Köhnə sistemlərdən ixrac: format, sahələr, tarixi məlumatın həcmi, kim verir.
3. Hostinq: AzTU data mərkəzi, AzInTelecom, yoxsa başqası. Server ölçüsü.
4. `sso.aztu.edu.az` hansı protokolla işləyir: OIDC, SAML, CAS.
5. İmtahan auditoriyaları: kompüter sayı, əməliyyat sistemi, şəbəkə aralığı.
6. LLM: oflayn mühərrik kifayətdir, yoxsa xarici və ya yerli model qoşulur.
7. Qiymət sxemi bütün fənlər üçün eynidir, yoxsa fənn üzrə dəyişir.
8. "Sillabus üçün NIST": NICE Framework xəritəsi və platformanın NIST nəzarətləri kimi başa düşmüşəm. Düzdür?
9. İlk dalğanın fakültəsi, fənləri və başlama tarixi.
10. Maddə 8 üzrə razılıq forması və maddə 15 üzrə qeydiyyat: AzTU hüquqşünasının rəyi.
