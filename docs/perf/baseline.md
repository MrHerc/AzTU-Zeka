# Performans bazası (Task 6–7)

Ölçmə tarixi: 2026-11-18. Maşın: 4 vCPU (Intel Xeon 2,10 GHz), 16 GB RAM, Linux, Python 3.13.18, SQLite 3.53.1.
Yük generatoru (`tools/loadtest.py`, 4 müştəri prosesi) server ilə eyni maşındadır: 4 işçili nəticə CPU-nu onunla bölür.
Hədəf serverdə ölçmə Task 44-dədir (`docs/perf/target.md`).

## Dəstlər

`tools/loadtest.py` demo bazasının üstünə sintetik sətirlər əlavə edir (`synthetic=1`, real şəxs yoxdur).

| Dəst | İstifadəçi | Yazılış | Cədvəl sətri | Test cəhdi | Material hissəsi | Fənn | Baza |
|---|---|---|---|---|---|---|---|
| demo | 147 | 720 | 15 | 768 | 94 | 6 | 2 MB |
| faculty | 2 147 | 12 720 | 1 215 | 20 768 | 20 094 | 206 | 24 MB |
| university | 10 147 | 60 720 | 6 015 | 100 768 | 100 094 | 1 006 | 110 MB |

## Oxu ssenarisi: 300 paralel müştəri, 30 saniyə

`GET /api/student/home` 60 %, `GET /api/schedule` 20 %, `GET /api/courses` 20 %; 25 tələbə sessiyası, gözləmə yoxdur.

| Dəst | Proses | İndekslərdən əvvəl (`95a348c`) | İndekslərdən sonra | p50 / p95 / p99, ms | 5xx | Bağlantı xətası |
|---|---|---|---|---|---|---|
| demo | 1 | — | 273 sorğu/san | 1 136 / 1 256 / 2 256 | 0 | 0 |
| faculty | 1 | 121 sorğu/san (demonun 44 %-i) | 276 sorğu/san (101 %) | 1 116 / 1 212 / 2 260 | 0 | 0 |
| university | 1 | 39 sorğu/san, 157 × 503, p95 10 136 ms | 264 sorğu/san | 1 172 / 1 276 / 2 376 | 0 | 0 |
| university | 4 | — | 830 sorğu/san | 346 / 800 / 1 013 | 0 | 0 |

Gecikmə yüksəkdir, çünki 300 müştəri gözləmədən sorğu göndərir və qapı (Task 6) eyni anda 2 handler buraxır. Bu növbədir,
xəta deyil. Hədd (SPEC Open Questions 23): `faculty` demonun ≥ 60 %-i. Nəticə: 101 %.

Nə dəyişdi:
- `backend/migrations/0071_hot_path_indexes.sql`: `attempts(user_id, quiz_id)`, `timetable(course_id)`,
  `enrollments(course_id)`, `quizzes(course_id)`, `materials(course_id)`, `lessons(course_id)`.
- `student_home` və `/api/schedule` bütün cədvəli həftənin günü üzrə oxuyub süzürdü. İndi yalnız istifadəçinin fənlərini
  oxuyurlar, hər fənn üçün bir indeksli sorğu ilə (`week_timetable`).
- `tools/queryplan.py`: əvvəl 46 sorğu 1 000 sətirdən böyük cədvəli tam oxuyurdu, indi 0. `tests/load/test_query_plans.py`
  bunu qoruyur.

## Axtarış indeksi

| Dəst | Tam qurma | Prosesin yaddaşına əlavə |
|---|---|---|
| faculty (20 094 hissə) | 4,7 s | 151 MB |
| university (100 094 hissə) | 23,4 s | 737 MB (hissə başına ≈ 7,4 KB) |

Çox prosesli rejim (`--workers N`, `university`):

| | Əvvəl | İndi |
|---|---|---|
| Başlanğıc, 2 işçi | 46,6 s (supervisor qurur, sonra hər işçi yenidən qurur) | 22,4 s |
| Başlanğıc, 4 işçi | — | 23,4 s |
| Yaddaş, 2 işçi (RSS) | supervisor 765 + işçi 2 × 1 105 MB | hər proses PSS 257 MB, cəmi ≈ 770 MB |
| Yaddaş, 4 işçi (PSS) | — | başlanğıcda cəmi ≈ 785 MB, 400 axtarışdan sonra ≈ 945 MB |

İndi indeksi bir dəfə supervisor qurur (`store.init`). Sonra yaddaşı dondurur (`gc.freeze()`) və işçiləri `fork` ilə
başladır. İşçilər indeksin səhifələrini paylaşır. Yenidən başladılan işçi indeksi qurmur: supervisor başlayandan bəri
dəyişənləri (`index_changes`) tətbiq edir. RSS paylaşılan səhifələri hər prosesdə yenidən sayır. Real yaddaş PSS-dir.

Bir işçidə yüklənən materialın digər işçidə axtarışı (`university`, 2 işçi):

| | Gecikmə |
|---|---|
| Adi axtarış (isti), median | 104–112 ms |
| Yükləmədən sonra digər işçinin ilk axtarışı | 85–89 ms |
| 400 axtarış, yeni bağlantılar, 4 işçi | p50 68 ms, p95 93 ms |

Dəyişikliyin tətbiqi gecikmə vermir (hədd ≤ 200 ms). Tam yenidənqurma yoxdur.

## İmtahan ssenarisi (Task 27), 2026-11-19

Ölçmə: `faculty` dəsti, 300 tələbə, hər biri bir dəfə: giriş, başlanğıc, 10 cavab, təslim (3 900 sorğu). Hər
cavab PUT adi (gecikdirilmiş) tranzaksiyada yazılır və tam `fsync` ilə commit olunur (`synchronous=FULL`).

| Rejim | İşçi | p50 | p95 | p99 | İtən cavab | 5xx |
|---|---|---|---|---|---|---|
| 300 saniyəyə yayılmış (girişlər ilk onda birdə, cavablar boyunca) | 1 | 4 ms | 8 ms | 24 ms | 0 / 3 000 | 0 |
| Hamısı birdən, fasiləsiz (`--burst`) | 1 | 642 ms | 871 ms | 934 ms | 0 / 3 000 | 0 |
| Hamısı birdən, fasiləsiz (`--burst`) | 4 | 254 ms | 621 ms | 754 ms | 0 / 3 000 | 0 |
| Bir tələbə | 1 | 3 ms | 6 ms | 6 ms | 0 | 0 |

T30-dan sonra (hash zənciri hər hadisədə, 3 nəzarətçi lövhəni 5 saniyədən bir sorğulayır; `--proctors 3`, standart):
yayılmış 300 saniyə, 1 işçi: p50 4 ms, p95 14 ms, p99 39 ms, 3 000 / 3 000 cavab, itki 0, 5xx 0; lövhə 201 sorğu,
p95 27 ms, xəta 0.

Checkpoint D düzəlişlərindən sonra (hər keçid əvvəl yazı kilidini alır, imtina hadisələri məhdudlaşdırılıb), eyni əmr:
p50 4 ms, p95 11 ms, p99 40 ms, 3 000 / 3 000 cavab, itki 0, 5xx 0, 4xx 0; lövhə 201 sorğu, p95 28 ms, xəta 0.

Meyar (p95 < 500 ms, itən cavab 0) yayılmış rejimdə ödənir. `--burst` ən pis haldır: 300 müştəri fasiləsiz sorğu
göndərir və gecikmə növbədir (Little qanunu: 300 / 435 sorğu/s ≈ 0,7 s). Real imtahanda cavablar dəqiqələrə yayılır.

Tapıntı: əvvəl bir tələbənin hər sorğusu 44–48 ms çəkirdi, serverin öz işi isə 3–7 ms idi (giriş jurnalının `ms`
sahəsi). Səbəb: cavabın başlıqları və gövdəsi iki ayrı yazı ilə gedirdi və Nagle alqoritmi ikinci yazını müştərinin
gecikdirilmiş ACK-ını gözləməyə məcbur edirdi (~40 ms). `web.py`-də `disable_nagle_algorithm = True` (TCP_NODELAY)
bunu aradan qaldırdı: bir tələbə 48 → 3 ms, yayılmış 300 tələbə p95 47 → 8 ms. Oxu ssenarisi eyni maşında yan-yana: Nagle ilə 204–210 sorğu/s, p95
2,8 s; Nagle-siz 215–219 sorğu/s, p95 2,5 s (həmin gün maşın əvvəlki ölçmələrdən yavaş idi).

## 2026-11-23/24-də əlavə olunan ekranlar, 2026-11-24

Dəst: `university` (10 147 istifadəçi) və `tools/queryplan.py`-nin əlavələri: 2 507 fənn, 2 400 sillabus versiyası,
3 000 tədris vahidli semestr versiyası, NIST-in NICE 2.2.0 faylı, 150 qrupu və 300 fənni olan ixtisas (hər dərc olunmuş
versiyada 6 nəticə × 5 NICE bəyanatı), müəllimin 60 köhnə fənni. İcmalın semestrində 306 fənn var. Hədəf: səhifə p95
< 300 ms, CSV p95 < 2 s, 1 000 sətirdən böyük cədvəlin tam oxunması yoxdur.

`python tools/queryplan.py --dataset university --repeat 20`: server eyni prosesdədir, hər SQL izlənir, hər GET 20 dəfə
göndərilir. Bir sətir bir rolun bütün filtrlərindən ən pisidir. ms, p50 / p95:

| Ekran | Rol | Əvvəl (`42f8bcb`) | Sonra | SQL sayı |
|---|---|---|---|---|
| `/api/syllabi/overview` (filtrlər, səhifə 2) | `academic_office` · `office` · `leader` | 5,6 / 8,4 | 5,0 / 13,8 | 5–6 |
| `/api/syllabi/overview` CSV | eyni rollar | 5,6 / 8,7 | 5,0 / 8,6 | 5–6 |
| `/api/syllabi/queue`, səhifə 1 və 2 | `dept_head` · `academic_office` · `admin` | 7,9 / 12,9 | 8,0 / 19,4 | 7–8 |
| `/api/timetable/versions/{id}/hours` (filtrlər, `offset`) | `academic_office` | **495 / 1 244** | 115 / 1 063 | 42 |
| `/api/timetable/versions/{id}/hours` CSV | `academic_office` | **494 / 1 203** | 142 / 854 | 43 |
| `/api/frameworks/coverage` (`role=` ilə də) | `academic_office` · `dept_head` · `leader` · `admin` | 33 / 736 | 42 / 118 | **310 → 11** |
| `/api/frameworks/coverage` CSV (1,4 MB) | `leader` | 76 / 114 | 73 / 119 | **309 → 10** |
| `/api/syllabi/{id}/sources` | `teacher` | 3,3 / 6,0 | 7,6 / 10,1 | 6 |
| Prerekvizit axtarışı | `teacher` | 3,9 / 5,1 (`/api/directory/courses`, **`SCAN courses`**) | 3,9 / 9,8 (`/api/syllabi/{id}/prerequisites`) | 5 |

Bu üsulda p95 dəyişkəndir: 20 nümunədə 1–2 yavaş cavab p95-i təyin edir, izləmə və eyni proses də təsir edir. Ona
görə ağır ekranlar ayrıca, real server prosesində də ölçülüb (`backend/run.py`, 1 işçi, `ZEKA_JOBS=0`, eyni baza, hər
biri 30 dəfə, birdəfəlik skript):

| Ekran | Əvvəl, p50 / p95 | Sonra, p50 / p95 |
|---|---|---|
| Saat hesabatı, səhifə | 479 / **632** | 101 / 205 |
| Saat hesabatı, CSV (550 KB) | 511 / 607 | 140 / 248 |
| Əhatə hesabatı, səhifə | 30 / 45 | 26 / 133 |
| Əhatə hesabatı, CSV | 65 / 106 | 66 / 103 |
| Semestr icmalı, CSV | 4,8 / 6,6 | 5,2 / 7,0 |

Nə dəyişdi:
- Saat hesabatı (`timetable/domain.hours_report`) hər vahid üçün semestrin bütün görüşlərini və çıxarılan vahidləri
  gəzirdi: 3 000 vahiddə 0,37 s, 5 000 vahiddə 1,2 s. İndi görüşlər vahidə görə bir dəfə qruplaşdırılır: 5 000 vahid
  ≈ 0,1 s. Test: `tests/load/test_tt_perf.py::test_the_hours_report_grows_linearly_with_the_units`.
- Əhatə hesabatı ixtisasın hər fənninin dərc olunmuş versiyasını ayrıca sorğu ilə oxuyurdu (300 fənn: 310 sorğu). İndi
  500 fənnə bir sorğu (`syllabus/repo.published_of`). Test: `tests/integration/test_frameworks.py`, sorğu sayı ixtisasın
  ölçüsündən asılı deyil.
- Prerekvizit axtarışı kataloqun siyahısını (`/api/directory/courses`) çağırırdı: hər işçiyə fənnin tam sətri,
  `LIKE '%q%'` ilə bütün `courses` cədvəlinin oxunması. İndi redaktorun öz marşrutu var: yalnız fənnin rəhbər müəllimi,
  yalnız kod və ad, ən çox 10 fənn, fənnin özü yox. Kodun və ya adın əvvəli ilə axtarır, indeks aralıqları ilə
  (`0231` kod, `0232_registry_name_index.sql` ad). Cavab 20 KB → 0,5 KB. Test:
  `tests/integration/test_syllabus_registry.py`; plan `tests/load/test_query_plans.py`-də.
- Semestr icmalı, təsdiq növbəsi və köçürmə mənbələri həddən xeyli aşağıdır: dəyişmədi.

Tam oxunma: əvvəl `screens` ssenarisində 6 sorğu `SCAN courses` idi (prerekvizit axtarışı), indi 0. `leader`
ssenarisinin tam oxunmaları əvvəlki kimi qəsdəndir (`docs/perf/task42.md`).

Qalan risk: icmal bir semestrin bütün fənlərini oxuyub Python-da süzür. 306 fənndə 5 ms-dir; 3 000 fənlik semestr
ölçülməyib. Saat hesabatı səhifəsi hər dəfə versiyanın bütün vahidlərini hesablayır; 3 000 vahiddə p95 205 ms-dir.

## Riskin həddi (plan A6)

İndeks prosesin yaddaşındadır və hissə başına təxminən 7,4 KB tutur. Ölçmə yalnız sintetik mətnlə aparılıb, real AzTU
korpusunun ölçüsü bilinmir. Real korpus 300 000 hissəni keçərsə (indeks təxminən 2,2 GB, tam qurma təxminən 70 s), plan
A6-nın ehtiyat yolu açılır: SQLite FTS5.

## Necə təkrarlamaq

```bash
python tools/loadtest.py --scenario read --users 300 --seconds 30 --dataset demo
python tools/loadtest.py --scenario read --users 300 --seconds 30 --dataset faculty
python tools/loadtest.py --scenario read --users 300 --seconds 30 --dataset university
python tools/loadtest.py --scenario read --users 300 --seconds 30 --dataset university --workers 4
python tools/loadtest.py --scenario exam --users 300 --seconds 300 --dataset faculty
python tools/loadtest.py --scenario exam --users 300 --seconds 60 --dataset faculty --burst --workers 4
python tools/queryplan.py --dataset university
python tools/queryplan.py --dataset university --repeat 20     # 2026-11-23/24 ekranlarının p50/p95-i (`screens`)
python -m pytest tests/integration/test_multiworker_state.py tests/load/test_query_plans.py -q
```

Başlanğıc, PSS və axtarış gecikməsi birdəfəlik skriptlə ölçülüb. Skript `tests/integration/test_multiworker_state.py`-nin
köməkçilərini işlədir: server `--workers N` ilə başladılır, işçilərin `/proc/<pid>/smaps_rollup` Pss dəyəri oxunur, bir
işçidə material yüklənir və digər işçidə axtarış edilir.
