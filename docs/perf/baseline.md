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
cavab PUT `BEGIN IMMEDIATE` ilə yazılır və tam `fsync` ilə commit olunur (`synchronous=FULL`).

| Rejim | İşçi | p50 | p95 | p99 | İtən cavab | 5xx |
|---|---|---|---|---|---|---|
| 300 saniyəyə yayılmış (girişlər ilk onda birdə, cavablar boyunca) | 1 | 4 ms | 8 ms | 24 ms | 0 / 3 000 | 0 |
| Hamısı birdən, fasiləsiz (`--burst`) | 1 | 642 ms | 871 ms | 934 ms | 0 / 3 000 | 0 |
| Hamısı birdən, fasiləsiz (`--burst`) | 4 | 254 ms | 621 ms | 754 ms | 0 / 3 000 | 0 |
| Bir tələbə | 1 | 3 ms | 6 ms | 6 ms | 0 | 0 |

Meyar (p95 < 500 ms, itən cavab 0) yayılmış rejimdə ödənir. `--burst` ən pis haldır: 300 müştəri fasiləsiz sorğu
göndərir və gecikmə növbədir (Little qanunu: 300 / 435 sorğu/s ≈ 0,7 s). Real imtahanda cavablar dəqiqələrə yayılır.

Tapıntı: əvvəl bir tələbənin hər sorğusu 44–48 ms çəkirdi, serverin öz işi isə 3–7 ms idi (giriş jurnalının `ms`
sahəsi). Səbəb: cavabın başlıqları və gövdəsi iki ayrı yazı ilə gedirdi və Nagle alqoritmi ikinci yazını müştərinin
gecikdirilmiş ACK-ını gözləməyə məcbur edirdi (~40 ms). `web.py`-də `disable_nagle_algorithm = True` (TCP_NODELAY)
bunu aradan qaldırdı: bir tələbə 48 → 3 ms, yayılmış 300 tələbə p95 47 → 8 ms. Oxu ssenarisi eyni maşında yan-yana: Nagle ilə 204–210 sorğu/s, p95
2,8 s; Nagle-siz 215–219 sorğu/s, p95 2,5 s (həmin gün maşın əvvəlki ölçmələrdən yavaş idi).

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
python -m pytest tests/integration/test_multiworker_state.py tests/load/test_query_plans.py -q
```

Başlanğıc, PSS və axtarış gecikməsi birdəfəlik skriptlə ölçülüb. Skript `tests/integration/test_multiworker_state.py`-nin
köməkçilərini işlədir: server `--workers N` ilə başladılır, işçilərin `/proc/<pid>/smaps_rollup` Pss dəyəri oxunur, bir
işçidə material yüklənir və digər işçidə axtarış edilir.
