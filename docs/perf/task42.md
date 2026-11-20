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
| Rəhbərlik | `GET /api/analytics`, `GET /api/insight/evidence` | var, aşağıda |

Ən yavaş marşrutlar (bir sorğu, keş soyuq):

| Marşrut | Əvvəl | `0420`-dən sonra | Sorğu sayı |
|---|---|---|---|
| `GET /api/analytics` | 13 335 ms | 6 196 ms | 5 191 |
| `GET /api/student/home` | 11 ms | 7 ms | 93 |
| `GET /api/insight/evidence` | 7 ms | 7 ms | 22 |
| `PUT /api/exams/{id}/answers/{qid}` | 5 ms | 5 ms | 11 |

`0420_dashboard_indexes.sql` (`attempts(quiz_id, finished_at)`) hər fənn üçün `attempts` cədvəlinin tam oxunmasını
aradan qaldırdı (1 007 tam oxu, hər biri 100 768 sətir).

**Açıq qalan (PERF-F1, Checkpoint F):** qalan 6 saniyənin təxminən 97 %-i Zəka Radar-ın kampus üzrə hesabıdır
(`r_radar.leader_insight` → `radar.analysis`): 60 720 tələbə × fənn profili, o cümlədən hər səbəbin tərcümə olunan adı.
Nəticə prosesin keşində saxlanır, amma keşin açarı hər yeni söhbət mesajı ilə dəyişir. Canlı universitetdə demək olar
ki, hər açılış yenidən hesablayır və bu müddətdə prosesin iki sürətli slotundan biri məşğuldur. Təklif: kampus sayları
dövri işdə hesablansın, panel onları oxusun. Düzəliş Radar-ın təzəlik qaydasını dəyişdiyi üçün Checkpoint F-də rəy və
təkzibdən keçir.

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

Yük testlərinin nəticəsi buraya yazılacaq.
