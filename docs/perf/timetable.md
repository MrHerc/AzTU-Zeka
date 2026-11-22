# Task 48: cədvəl həlledicisinin ölçmələri (dilim 1)

Ölçmə tarixi: 2026-11-22. Maşın: inkişaf konteyneri, 4 vCPU, Python 3.13.18; maşın başqa işlərlə bölünür, ona görə
rəqəmlər yuxarı həddir. Dəstlər `tools/ttbench.py`-dəndir: real Forma №3 fayllarının paylanmasına (saat növü, vahidə
düşən qrup, qrupun tələbə sayı, müəllim yükü) uyğun sintetik semestr, yalnız id-lər (ad, kod və ya faylın xanası yoxdur).

```bash
python tools/ttbench.py --units 1250                                                   # kafedra
python tools/ttbench.py --units 16700 --groups 4000 --teachers 1200 --rooms 800         # universitet
python -m pytest tests/load/test_tt_perf.py -q                                         # kafedra sütunu, hədlərlə
```

## Nəticələr (tam model, 50 000 təkmilləşdirmə iterasiyası, toxum 1)

| Ölçü | Kafedra hədəfi | Kafedra (1 250 vahid, 300 qrup, 90 müəllim, 60 otaq) | Universitet hədəfi | Universitet (16 700 vahid, 4 000 qrup, 1 200 müəllim, 800 otaq) |
|---|---|---|---|---|
| İclas | — | 1 303 | — | 17 407 |
| `prepare` + ilkin yoxlamalar | ≤ 1 s | 0,20 s | ≤ 15 s | 6,8 s |
| İlkin quruluş (ilk tam layihə) | ≤ 3 s | 0,15 s | ≤ 90 s | 11,8 s |
| Təkmilləşdirmə, 50 000 iterasiya | ≤ 30 s | 5,9 s | ≤ 10 dəq | 150 s (100 000 iterasiya: 272–332 s) |
| Tam yoxlama + skor kartı | ≤ 1 s | 0,07 s | ≤ 15 s | 1,5 s |
| Layihənin yazılması (bir tranzaksiya) | ≤ 20 ms (testdə ≤ 50 ms) | testdə keçir | ≤ 150 ms | ölçülməyib (dilim 2) |
| Yaddaş | ≤ 80 MB | ≤ 80 MB (`tracemalloc`, testdə) | ≤ 500 MB | pik RSS problemin üstündən 199 MB |
| Sərt pozuntu | 0 | 0 | 0 | 0 |
| Yerləşdirilməyən | 0 | 0 | — | 165 (0,95 %) |
| Həlledicinin xərci = skor kartı | bəli | bəli (3 038) | bəli | bəli (114 196) |

Universitetin 165 yerləşdirilməyən iclası sintetik otaq fondunun çatışmazlığıdır, həllediciyə aid deyil: ilkin
yoxlama 12 tutum həddində `room_supply` göstərir (böyük axınların həftəlik cüt tələbi o tutumda və ondan böyük
otaqların həftəlik cütlərindən çoxdur), bir `no_room_capacity` və bir `teacher_overload`. Ona görə fakültələrə bölmə
ehtiyat yolu ölçülməyib: vaxt hədəflərinin heç biri aşılmayıb.

Real RT + MR payız vahidləri (888 vahid, 956 iclas, sintetik otaqlar: 11 mühazirə zalı, 30 auditoriya, 8 laboratoriya,
tam model, 50 000 iterasiyalıq büdcə): `prepare` 0,25 s, ilkin quruluş 0,07 s, təkmilləşdirmə 2,3 s (durğunluqla
dayanır), 0 sərt pozuntu, 0 yerləşdirilməyən. Ölçmə skripti repozitoriyadan kənardadır; faylların adları və xanaları
oxunmur və yazılmır.

## Qeydlər

- Bütün rəqəmlər bir prosesdədir. İşdə (`timetable.work`, dilim 2) model hesablamalar arasında yaddaşda qalır,
  vəziyyət hər mərhələdən sonra bazaya yazılır; yenidən başlayan işçi eyni nəticəyə gəlir (`test_tt_props.py`).
- Eyni toxum eyni baytları verir: qızıl imza Python 3.11, 3.12 və 3.13-də eynidir (3.10 CI-da yoxlanır).
- Ölçülməyib: universitet ölçüsündə layihənin yazılması, "hara qoymaq olar" və köçürmə sorğuları (dilim 2,
  `tests/load/`).
