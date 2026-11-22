# Task 42: yük, sorğu planları və xaos

Maşın: inkişaf konteyneri, 4 nüvə, 15 GB yaddaş, Python 3.13, SQLite WAL. Dəstlər `tools/loadtest.py`-dəndir
(`docs/perf/baseline.md`, "Dəstlər"). Hədəf serverdə təkrarı Task 44-dədir (`docs/perf/target.md`).

## Sorğu planları (`university` dəsti)

`python tools/queryplan.py --dataset university` hər ssenarinin marşrutlarını bir dəfə göndərir və icra olunan hər
sorğunun planını yoxlayır. `tests/load/test_query_plans.py` qarışıq və imtahan ssenarilərində 1 000 sətirdən böyük
cədvəl üzrə `SCAN` olmamasını tələb edir.

| Ssenari | Marşrutlar | Böyük cədvəl üzrə `SCAN` |
|---|---|---|
| Qarışıq | `GET /api/student/home`, `/api/schedule`, `/api/courses`, `PUT /api/me/prefs`, `POST /api/news/{id}/save` | yoxdur |
| İmtahan | `enter`, `start`, hər cavab (`PUT …/answers/{qid}`), `GET /api/exams/{id}`, gözətçi paneli `…/board`, `submit` | yoxdur |
| Rəhbərlik | `GET /api/analytics`, `GET /api/insight/evidence` | `messages`, `courses`, `materials`, `users` (fənlərin və mesajların sayı); `attendance` artıq yoxdur |
| Rəhbərlik, Radar səhifəsi | `GET /api/radar` | `enrollments`, `attendance`, `grades`, `attempts`, `messages`: canlı analiz hər tələbənin qeydlərini oxuyur |

Ən yavaş marşrutlar (bir sorğu, keş soyuq):

| Marşrut | Əvvəl | `0420`-dən sonra | PERF-F1-dən sonra | Sorğu sayı (indi) |
|---|---|---|---|---|
| `GET /api/analytics` | 13 335 ms | 6 196 ms | 94 ms (F1-dən sonra 169 ms) | 5 179 |
| `GET /api/radar` (Radar səhifəsi, rəhbər) | — | — | 6 927 ms | 2 033 |
| `GET /api/courses` | — | — | 9 ms | 60 |
| `GET /api/student/home` | 11 ms | 7 ms | 6 ms | 93 |
| `GET /api/insight/evidence` | 7 ms | 7 ms | 6 ms | 22 |
| `PUT /api/exams/{id}/answers/{qid}` | 5 ms | 5 ms | 5 ms | 12 |

`0420_dashboard_indexes.sql` (`attempts(quiz_id, finished_at)`) hər fənn üçün `attempts` cədvəlinin tam oxunmasını
aradan qaldırdı (1 007 tam oxu, hər biri 100 768 sətir).

**PERF-F1 (Checkpoint F): rəhbərlik paneli 6,2 s-dən 94 ms-ə düşüb.** Qalan 6 saniyənin təxminən 97 %-i Zəka Radar-ın
kampus üzrə hesabı idi (`r_radar.leader_insight` → `radar.analysis`): 60 720 tələbə × fənn profili, o cümlədən hər
səbəbin tərcümə olunan adı. Nəticə prosesin keşində saxlanırdı, amma keşin açarı hər yeni söhbət mesajı ilə dəyişirdi:
canlı universitetdə demək olar ki, hər açılış yenidən hesablayırdı və bu müddətdə prosesin iki sürətli slotundan biri
məşğul olurdu. Rəhbərliyin və dekanlığın menyusundakı Radar nişanı da (`GET /api/badges`, hər 30 saniyədən bir) eyni
hesabı aparırdı.

- Kampus üzrə sayları və dəstək planlarının təsirini dövri iş `radar.summary` hər 15 dəqiqədən bir hesablayır
  (`radar.summarize`, `settings` cədvəlində `radar_summary`). Demo bazasında ilk xülasəni seed yazır. Universitet
  dəstində iş təxminən 6 s çəkir: `--workers` ilə ayrıca prosesdə, tək proses rejimində işlərin axınında.
- Panelin Radar sətri və Radar kartı bu xülasəni oxuyur; sətir hesablandığı vaxtı göstərir: «Zəka Radar, 19.11.2026 10:00 tarixinə: …».
  İş hələ işləməyibsə, sətir bunu açıq yazır. Rəhbərliyin və dekanlığın Radar nişanı da xülasədən oxunur.
- Radar səhifəsi (`/api/radar`), tələbə profili, dəstək planı və müəllimin öz fənləri üzrə nişanı əvvəlki kimi canlı
  hesablanır. Radar-ın modeli, səviyyələri və sayların mənası dəyişməyib.
- Panelin qalan hissəsi: fənlər üzrə test ortalaması SQL-də hesablanır (əvvəl hər cəhd üçün bir lüğət yaradılırdı:
  100 768 cəhd, təxminən 0,8 s); kampus üzrə davamiyyət fənlərin cəmidir, `attendance` cədvəli tam oxunmur.

Təzəlik qaydası dəyişib: panel və nişan ən çox 15 dəqiqə əvvəlki vəziyyəti göstərir (vaxtı yazılır). Bu, Checkpoint F-in
rəy və təkzib mərhələsində yoxlanmalıdır. Yoxlayan testlər: `tests/integration/test_radar.py` (xülasə canlı analizə
bərabərdir; panel, onun kartı və nişan analizi çağırmır; xülasə yoxdursa, sətir bunu deyir), `tests/integration/test_insight.py`
(panelin sorğularında `attendance` üzrə `SCAN` yoxdur; davamiyyət və test ortalamaları sətirlərin birbaşa sayına
bərabərdir).

**Düzəliş (Checkpoint F, F1).** «6,2 s-dən 94 ms-ə» əvvəlcə yalnız `GET /api/analytics` üçün doğru idi, səhifə üçün
yox. Panelin Radar kartı (`frontend/js/radar.js`, `radarLeaderCard`) ayrıca `GET /api/radar` istəyirdi: kampus üzrə
canlı analiz, universitet dəstində soyuq keşlə təxminən 7 s. Kartın rəqəmləri isə üstündəki sətirdən (xülasədən) fərqli
ola bilirdi. İndi `radar.summarize` riskli tələbəsi ən çox olan 4 fənni, planlardan sonrakı orta dəyişməni və həftəlik
dinamikanı da yazır; `/api/analytics` xülasəni `radar` sahəsində qaytarır, kart onu göstərir. Panel yalnız
`/api/analytics` istəyir (brauzerdə yoxlanıb: `/api/radar` sorğusu yoxdur). `tools/queryplan.py` rəhbər ssenarisinə
Radar səhifəsini də əlavə edib: o canlı qalır və 6 927 ms çəkir. Bu, panelin yox, Radar səhifəsinin açılışıdır.

**AR-F11: aktiv istifadəçi göstəriciləri.** `insight/repo.active_weekly` və `active_by_role` 8 həftənin hər hadisə
sətri üzrə `COUNT(DISTINCT user_id)` edirdi. `0421_active_days.sql` `active_days(day, role, user_id)` cədvəlini yaradır
və mövcud hadisələrdən doldurur; `core/events.py` hər hadisənin yanında `INSERT OR IGNORE` ilə bir sətir yazır (şəxs,
rol və gün üzrə ən çoxu bir). Göstəricilər bu cədvəli açarı ilə oxuyur. Həftə indi tam günlərlə sayılır: bu gün və ondan
əvvəlki 6 gün (əvvəl saniyəsinədək son 7 × 24 saat idi); tərif («Son 7 gündə …») dəyişməyib. Sətirlər hadisələrlə
birlikdə 365 gündən sonra silinir; şəxs silinəndə onunla birlikdə silinir (`identity/repo.INVENTORY`,
`docs/privacy/data-inventory.md`).

Ölçmə (yaddaşdakı SQLite, 10 000 tələbə və 1 000 müəllim, 56 gün, günlərin 70 %-ində gündə 4 hadisə: 1 725 308 hadisə,
431 327 gün sətri):

| Sorğu | Hadisələr üzrə | `active_days` üzrə | Plan (indi) |
|---|---|---|---|
| Həftəlik aktiv tələbələr (8 həftə) | 1 027 ms | 185 ms | `SEARCH active_days USING PRIMARY KEY (role=? AND day>? AND day<?)` |
| Həftəlik aktiv müəllimlər (8 həftə) | 243 ms | 9 ms | eyni |
| Son 7 gün, rollar üzrə | 83 ms | 11 ms | `SEARCH active_days USING COVERING INDEX idx_active_days_day (day>? AND day<?)` |

`tests/integration/test_insight.py` planları `EXPLAIN QUERY PLAN` ilə yoxlayır (`SEARCH active_days`, `SCAN` yoxdur,
`events` oxunmur), `tests/migration/test_schema_migrations.py` isə `0421`-in mövcud hadisələrdən doldurulmasını.

## Xaos (`tests/integration/test_chaos.py`)

Hər test `backend/run.py`-ni müvəqqəti bazada açıq imtahanla işə salır (12 tələbə, hər birinin 10 sualı).

| Hal | Nə edilir | Nəticə |
|---|---|---|
| İşçinin `kill -9`-u | 2 işçi; 20-ci təsdiqlənmiş cavabdan sonra bir işçi `SIGKILL` ilə öldürülür, cavablar göndərilməyə davam edir (səhifə kimi təkrar cəhd) | Server 200 qaytardığı hər cavab bazadadır; 5xx yoxdur; hər cəhd `in_progress` qalır və bütün cavabları göstərir |
| Bütün serverin `kill -9`-u | 5 cavabdan sonra server `SIGKILL` ilə dayanır, yenidən başlayır | Hər tələbə eyni cəhdə və eyni variantla qayıdır, 5 cavab yerindədir; qalanları yazılır, hamı təhvil verir |
| Məşğul baza | Başqa proses yazma kilidini (`BEGIN IMMEDIATE`) 2 saniyə saxlayır, bu vaxt 120 cavab göndərilir | Hamısı 200, 5xx 0, itən cavab 0 (SQLite gözləmə həddi 15 s, növbə həddi 10 s) |
| SMTP kəsintisi | `tests/integration/test_email_outbox.py` | Relə işləməyəndə məktub itmir, gecikir; asılı qalan relə digər işləri saxlamır |

Testlər həqiqətən yoxlayır: cavabın yazılması söndürüləndə (`put_answer` çağırılmır) üçü də düşür.

## Yük testləri

### Gündəlik qarışıq yük

`python tools/loadtest.py --scenario mixed --users 1000 --seconds 600 --think 5 --dataset university --workers 2 --fail-on-errors`

Əvvəlki ölçmə: p95 27 ms, 5xx 0, amma 274 bağlantı xətası və 530 4xx; `--fail-on-errors` ilə çıxış kodu 1.

Səbəbləri qısa variant göstərdi (eyni əmr, `--seconds 120`, köhnə davranışla, xətalar marşrutlar üzrə): 112 4xx və 43
bağlantı xətası.

- **4xx alətin öz skriptindən idi.** Hamısı `POST /api/news/{id}/save` üzrə 404 idi. Skript dərc olunmuş 14 xəbərin
  hamısından seçirdi, onlardan biri isə yalnız müəllimlər üçündür: tələbə onu görmür və server düzgün olaraq 404
  qaytarır. Alət indi yalnız tələbənin görə bildiyi xəbərləri seçir (`audience IN ('all','students')`).
- **Bağlantı xətalarının səbəbi boş qalan keep-alive bağlantıları idi.** Server 30 saniyə boş qalan bağlantını bağlayır
  (`core/web.py`, `timeout = 30`). Düşünmə vaxtı eksponensialdır (orta 5 s): fasilələrin e⁻⁶ ≈ 0,25 %-i 30 saniyədən
  uzundur; 600 saniyədə təxminən 120 000 sorğuda bu, təxminən 300 hal deməkdir. Xətalar marşrutlar arasında onların
  payına mütənasib bölünürdü. Brauzer belə halda sorğunu yeni bağlantıda yenidən göndərir; alət də indi belə edir:
  server təkrar istifadə olunan bağlantını cavabsız bağlayıbsa (`RemoteDisconnected`, `BrokenPipeError`,
  `ConnectionResetError`), sorğu bir dəfə yeni bağlantıda göndərilir və `reopened` kimi sayılır. Vaxt aşımı (60 s
  ərzində cavab yoxdur), başqa hər xəta və yeni bağlantıda alınmayan sorğu isə bağlantı xətasıdır və təkrar
  göndərilmir (`POST /api/news/{id}/save` dəyişdirici əməliyyatdır). Bu, serverin qüsuru deyil: boş bağlantının
  bağlanması boş qalan axınları azad edir.

Alət indi hər qeyri-2xx cavabı marşrut üzrə göstərir (`errors_by_route`). `--fail-on-errors` read, write və mixed
ssenarilərində 4xx olduqda da 1 qaytarır: skript gözlənilən 4xx göndərmir.

Nəticə (eyni maşın; ölçmə zamanı maşında başqa iş də gedirdi, yük ortalaması təxminən 3 idi):

| Sorğu sayı | Sorğu/s | p50 | p95 | p99 | 5xx | 4xx | Bağlantı xətası | Yeni bağlantıda təkrar | Çıxış kodu |
|---|---|---|---|---|---|---|---|---|---|
| 120 784 | 201 | 9 ms | 37 ms | 256 ms | 0 | 0 | 0 | 296 | 0 |

Bu ölçmədə alət vaxt aşımından sonra da sorğunu təkrar göndərirdi (Checkpoint F, F2-də düzəldilib); ölçmə yeni qayda
ilə təkrarlanmayıb. p99 256 ms olduğundan 60 saniyəlik vaxt aşımı ehtimalı azdır, amma bu, ölçü ilə sübut olunmayıb.

### İmtahan

500 tələbə, 1 800 s, bütün girişlər 60 saniyə ərzində (`--ramp 60`), 2 işçi: p95 20 ms, p99 58 ms, 5xx 0; 5 000
cavabdan itən 0; gözətçi panelinin p95-i 48 ms; `manage.py exam-verify` keçib. Task 42-nin yoxlama əmri:
`python tools/loadtest.py --scenario exam --users 500 --seconds 1800 --ramp 60 --dataset university --workers 2`.
Bu ölçmə yuxarıdakı düzəlişlərdən əvvəl aparılıb və buraya köçürülüb. Düzəlişlərdən sonra hər yazan sorğuya, o cümlədən
imtahan cavabına, `active_days`-ə bir `INSERT OR IGNORE` əlavə olunub; imtahan testi bundan sonra təkrarlanmayıb.
