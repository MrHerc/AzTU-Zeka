# Checkpoint C baxışı (2026-11-19)

Faza 3 diff-i (`3a71a83..19e3ff8`, Tapşırıq 18–22 və 45) yeddi rəyçi ilə yoxlandı: `ecc:code-reviewer`,
`ecc:security-reviewer`, `ecc:silent-failure-hunter`, `agent-skills:code-reviewer`, `agent-skills:security-auditor`,
`agent-skills:test-engineer`, `ecc:python-reviewer`. Dublikatlar birləşdirildi, iddialar altı qrupa bölündü (D, R, L, J,
P, T; cəmi 57). Hər qrupu ayrıca agent 19e3ff8-in nüsxəsində işə salıb təkzib etməyə çalışdı. Yalnız təsdiqlənən hissələr
düzəldildi.

Hər düzəliş üçün reqressiya testi var: `tests/integration/test_checkpoint_c.py`. Köhnə kodda (19e3ff8) bu faylın 35 testi
yıxılır, 6-sı xəta verir, 4-ü keçir. Keçənlər test boşluqlarıdır: davranışı ilk dəfə yoxlayırlar. Əlavə testlər:
`tests/migration/test_schema_migrations.py` (0450 doldurması), `tests/integration/test_multiworker_state.py` (iki işçi
prosesdən HTTP ilə 50 paralel sənəd), `tests/unit/test_layers.py` (SQL yalnız `repo.py`-də).

## D. Sənədlər (Tapşırıq 45)

- **D1** (aşağı) — Təsdiqləndi. `/verify` universitetin adını canlı ayarlardan götürürdü. Düzəliş: saxlanmış yükün
  `ctx`-i (`r_services.verify_page`).
- **D2** — Niyyət olunub. Sütunlar yükdən fərqlənəndə də "etibarlıdır" çıxır. Bu, Tapşırıq 45-in yazılı həddinin
  içindədir: bazaya yaza bilən şəxs yükü də, hash-i də dəyişə bilər. Proqramda bu sütunları dəyişən yol yoxdur.
- **D3** (aşağı) — Təsdiqləndi. Hash-də ASCII olmayan simvol 400 verirdi. Düzəliş: `compare_digest` baytlarla işləyir.
- **D4** — Qismən. Davranış düzgündür, test boşluğu var idi. Testlər əlavə edildi: 0450 doldurması və iki işçidən HTTP
  ilə 50 paralel verilmə (5xx 0, nömrələr boşluqsuz).
- **D5** (aşağı) — Təsdiqləndi. Saxtalaşdırma testi bəzi tarixlərdə heç nə dəyişmirdi. Düzəliş: dəyişiklik həmişə baş
  verir və test bunu yoxlayır.

## R. Cədvəl, otaqlar, təqvim (Tapşırıq 18–19)

- **R1** (orta) — Təsdiqləndi. Otaq səhifəsi həftəlik sətirlərdən qurulurdu. Ona görə ləğv edilmiş, köçürülmüş,
  deaktiv edilmiş və başqa semestrin dərsləri qapıda görünürdü. Düzəliş: səhifə otağın keçirilən dərslərindən
  qurulur (`lessons`, `0191_room_lessons.sql` indeksi).
- **R2** (orta) — Təsdiqləndi. Sətrin redaktəsi köçürülmüş və əvəzlənmiş dərsləri silib ilkin vaxtda yenidən
  yaradırdı. Yalnız saat dəyişəndə də tələbələrə xəbər gedirdi. Düzəliş:
  - köçürülmüş dərs öz vaxtını saxlayır;
  - əvəzedici müəllim həmin həftənin dərsində qalır;
  - saat dəyişikliyi yerində yazılır və elan olunmur.
- **R3** (aşağı) — Qismən. Vahidsiz sətir 400 verirdi. İnterfeys bu sorğunu göndərmir. Düzəliş: `row_clashes`-də
  boş vahid nəzərə alınmır.
- **R4** (aşağı) — Təsdiqləndi. Siyahı 1000 sətirdə səssizcə kəsilirdi. Düzəliş: `more` bayrağı və ekranda xəbərdarlıq.
- **R5** (aşağı) — Təsdiqləndi. Otaqları yenidən bağlama deaktiv sətirləri də sayırdı.
- **R6** — Niyyət olunub. Yay vaxtı olan qurşaqlar planın A19 qərarına görə əhatədən kənardır.
- **R7** (orta) — Təsdiqləndi. Təqvim lentinin gizli açarı giriş jurnalına açıq yazılırdı. Düzəliş: `/ical/…`.
- **R8** (aşağı) — Təsdiqləndi. Limit IP üzrə idi: kampus və təqvim xidmətləri bir ünvanı bölüşür. Düzəliş: hər lent
  üçün 30/dəq, hər müştəri üçün 600/dəq.
- **R9** (aşağı) — Təsdiqləndi. Semestrin dərslərini yaratmaq böyük universitetdə yazma kilidini 200 ms-dən çox tutur.
  Düzəliş: marşrut `TX_GUARD_EXEMPT`-dədir. Bu, semestrdə bir neçə dəfə edilən əməliyyatdır.
- **R10** (aşağı) — Təsdiqləndi. SQL `service.py`-də idi, `routes.py` gizli funksiyanı çağırırdı, seed `repo`-nu birbaşa
  idxal edirdi. Düzəliş edildi. Qayda indi testdədir. Eyni qayda `identity/routes.py`-dəki bir SQL-i də repoya köçürdü.
- **R11** (aşağı) — Təsdiqləndi. 2^63-dən böyük id 500 verirdi. Düzəliş: `web.an_id` və dispetçerdə `OverflowError`.

## L. Materiallar və tapşırıqlar (Tapşırıq 22)

- **L1** (orta) — Təsdiqləndi:
  - cari versiyanın silinməsi əvvəlkini bölməsiz geri qaytarırdı;
  - eyni versiyanı iki paralel yükləmə əvəz edə bilirdi.
  Düzəliş: əvvəlki versiya bölmələri ilə qayıdır, `replaces` yoxlaması yazma kilidində aparılır.
- **L2** (orta) — Təsdiqləndi. Yeni versiya köhnə bölmələrin id-lərini alırdı. Ona görə köhnə tutor cavabları və suallar
  yeni mətnə istinad edirdi. Düzəliş: `0222_chunk_ids.sql`, `chunks.id AUTOINCREMENT`.
- **L3** (aşağı) — Təsdiqləndi. Sillabus generatoru və test studiyası əvəzlənmiş versiyaları da oxuyurdu. Yanaşı tapıntı:
  təsviri olmayan fənndə sillabus 400 verirdi.
- **L4** (aşağı) — Təsdiqləndi. Sxemdən çıxan komponent 500 verirdi; indi tərcümə olunmuş 400 verir.
- **L5** (aşağı–orta) — Təsdiqləndi. Tədris vahidinin müəllimi dərs yaranmayınca qiymət yaza bilmirdi. Düzəliş:
  `journal.repo.teaches` tədris vahidini sayır. Əvəzedici müəllim isə yalnız dərsini görür (J12).
- **L6** (aşağı) — Təsdiqləndi. Son tarixdə ASCII olmayan rəqəmlər və mövcud olmayan tarixlər qəbul edilirdi.
- **L7** (aşağı) — Təsdiqləndi. Qiymətləndirilmiş göndəriş dar yarışda əvəz oluna bilirdi.
- **L8** (aşağı) — Təsdiqləndi. Yüklənmiş fayl olmayanda 500 verirdi; indi 404 verir.
- **L9** (aşağı) — Təsdiqləndi. "Yeni versiya" və yükləmə düymələri baxışı da açırdı.

## J. Jurnal, yekun qiymət, idxal (Tapşırıq 20–21)

- **J1** (yüksək) — Təsdiqləndi. Kafedra müdirinin fakültə və ya fənlə məhdudlaşdırılmış rolu bütün universitetdə
  düzəliş edə bilirdi. Rolu olub qrantı olmayan şəxs də elə. Düzəliş: `journal.repo.dept_head_covers`. Qrant kafedra,
  fakültə, fənn üzrə və ya əhatəsiz ola bilər. Qrantı olmayan kafedra müdiri öz kafedrasının fənlərində işləyir.
- **J2** (orta) — Təsdiqləndi. Davamiyyət hesablanmayan fənndə yekun qiymət davamiyyəti 0 bal sayırdı. Düzəliş: belə
  halda yekun qiymət yazılmır, çünki "yoxdur" sıfır demək deyil. Sahib başqa siyasət seçə bilər: tam bal və ya idxal.
- **J3** (orta) — Təsdiqləndi. Davamiyyət dəyişəndə yekun qiymət yenilənmirdi. Düzəliş: `refresh_finals` hər
  dəyişiklikdən sonra işləyir: qeyd, açılış qalığı, üzrlü sorğu, idxal, universitetin qaydaları.
- **J4** (aşağı) — Qismən. Transkriptin hazırlığı verilmə anında da yoxlanır. Birinci semestr tələbəsinin boş
  transkripti Tapşırıq 21-ə görə niyyət olunub.
- **J5** (aşağı; c hissəsi orta) — Təsdiqləndi. Ballar idxalında üç problem var idi:
  - dərc olunmuş balın dəyişməsi jurnala yazılmırdı;
  - müəllimin qaralaması dərc olunurdu;
  - fənnə yazılmamış tələbəyə bal və yekun qiymət yazılırdı.
  Yanaşı tapıntı: `max` REAL ilə int fərqi eyni faylın təkrar idxalını konflikt edirdi.
- **J6** (aşağı) — Təsdiqləndi. Eyni xana iki dəfə göndəriləndə köhnə dəyərlə müqayisə olunurdu. Düzəliş: sonuncu dəyər
  qalır.
- **J7** (aşağı) — Təsdiqləndi. Kəsiddən əvvəlki dərsə yazılan yeni sətir heç nəyi dəyişmirdi. Düzəliş: belə
  sətir rədd olunur, susmaya görə "iştirak" yazılmır.
- **J8** (orta) — Təsdiqləndi. Gələcək tarixli açılış qalığı jurnalın qeydlərini gizlədirdi; indi rədd olunur.
- **J9** (orta) — Təsdiqləndi. Üzrlü tələbəsi olan dərs ekrandan saxlanmırdı (400).
- **J10** — Niyyət olunub. Üzrlü qayıb qeydlə əvəz olunmur. Ekran bunu nişanla göstərir.
- **J11** — Sahibin qərarı. Tələbə tapşırığın balını jurnalda dərc olunmamış görür. Tapşırıq 21 ilə Checkpoint C-nin
  "tələbə dərhal görür" mətni bir-birinə ziddir. Dəyişiklik edilmədi.
- **J12** — Müəllim hissəsi niyyət olunub, əvəzedici hissəsi qismən. Bir dərsi əvəz edən müəllim bütün fənnin
  qaralamalarını görürdü. Düzəliş L5 ilə birdir.
- **J13** (orta) — Təsdiqləndi. İdxal xəbərdarlıqları göstərilmirdi. Ekranın siyahısında `grades` növü də yox idi.

## P. Sürət və interfeysdən əlçatanlıq

- **P1** (yüksək) — Təsdiqləndi. Fənn siyahısı hər fənn üçün jurnalı oxuyurdu. Ölçmə (`loadtest --scenario read --users
  100 --seconds 15 --dataset demo`) saniyədə sorğu sayını verir:

  | Kod | Saniyədə sorğu |
  |---|---|
  | 3a71a83 (Faza 3-dən əvvəl) | 267–284 |
  | 19e3ff8 | 144–184 |
  | Düzəlişdən sonra | 305 (p95 656 ms, səhv 0) |

  Düzəliş: siyahı yalnız sayları verir. Jurnal mövqeyi davamiyyət səhifəsində və fənnin səhifəsindədir.
- **P2** (orta) — Təsdiqləndi. Yekun qiymətlər hər tələbə üçün jurnalı yenidən oxuyurdu. Düzəliş: `refresh_finals`
  jurnalı bir dəfə oxuyur. Tapşırığın balı cədvəli cavab üçün yenidən qurmur.
- **P3** (orta) — Təsdiqləndi. `grades` fənn üzrə tam skan olunurdu. Düzəliş: `0211_grades_course_index.sql`. Eyni
  faylda borclar üçün qismən indeks var.
- **P4** (orta) — Təsdiqləndi. İdxal açarları hər sətir üçün yenidən qururdu. Düzəliş: `Context.keyed` onları bir
  dəfə qurur.
- **P5** — Qismən. `serves()` ucuzdur. Borclar siyahısı isə həddsiz idi. Düzəliş: süzgəc SQL-də işləyir
  (`scope_sql`), siyahı 200-lük səhifələrlə gəlir, CSV tamdır.
- **P6** (orta) — Təsdiqləndi. Tədris vahidinin müəllimi öz fənnini siyahıda görmürdü. Düzəliş: `my_courses` və
  `course_access`; `0152_unit_teacher_index.sql`.
- **P7** (orta) — Təsdiqləndi. Kafedra müdiri başqa müəllimin dərsini aça bilmirdi. Düzəliş: fənnin vəziyyət səhifəsində
  dərslər siyahısı var. API indi 14 gün irəli verir.
- **P8** (orta) — Təsdiqləndi. Seçim siyahıları yalnız ilk 50 elementi oxuyurdu. Düzəliş: `api.all`. Əvəzedici siyahısına
  kafedra müdirləri də daxildir.
- **P9** (aşağı) — Təsdiqləndi. Xəta zamanı boş cədvəl göstərilirdi; indi `failed()` xətanı göstərir.

## T. Test dəsti

- **T1** (yüksək) — Təsdiqləndi. Demo semestr "bu gün"ə görə qurulur, test saatı isə sabit deyildi. Ona görə dəst ildə
  təxminən 14 həftə yaşıl idi: 3 noyabr – 21 dekabr və 6 aprel – 24 may. İlk qırmızı gün 22 dekabrdır.
  `test_radar::test_storyline_levels` köhnə kodda da 26 noyabrdan yıxılırdı. Düzəliş: `tests/conftest.py` testlərin
  "bu gün"ünü 2026-11-19 10:00 (Bakı) tarixinə bağlayır; saat test boyu irəliləyir. Üç köhnə test real tarixi oxuyurdu,
  indi `store.now()` oxuyur. `test_t1_…` yoxlayır ki, sabit gün semestrin içindədir. Təkzib agenti dəsti real tarixdən
  7 ay geri olan sabit günlə də işlətdi: hamısı keçdi.
- **T2** (orta) — Təsdiqləndi. Dekanlığın fakültə süzgəci testsiz idi. Test əlavə edildi: başqa fakültənin tələbəsi
  vəziyyətdə, qiymətlərdə, borclarda və CSV-də görünmür.
- **T3** (orta) — Təsdiqləndi. Əvəzetmə testi müəllimi özü ilə əvəz edirdi. Test əlavə edildi: əvəzetmədən sonra
  dərsin ilk müəllimi qeyd yaza bilmir.
- **T4** (orta) — Təsdiqləndi. Kafedra müdirinin uğurlu yolu testsiz idi. J1 testi bunu əhatə edir: öz fənninə qrantı
  olan müdir düzəliş edir.
- **T5** (aşağı) — Təsdiqləndi. İdxal olunmuş sətrin qoruyucusu testsiz idi. Test əlavə edildi: pəncərənin içində də
  müəllim idxal olunmuş sətri dəyişə bilmir.
- **T6** (aşağı) — Təsdiqləndi. Tələbənin mövqeyi yalnız açar adlarına görə yoxlanırdı. Test əlavə edildi: dəyərlər
  müəllimin gördüyü ilə eynidir.
- **T7** — Qismən. Test əlavə edildi: 3 saatlıq dərs 3 saat sayılır.
- **T8** (aşağı) — Təsdiqləndi. Test əlavə edildi: gələcək dərs keçirilmiş sayılmır və universitetin düzəliş pəncərəsi
  tətbiq olunur. Qeydiyyatın bitmə tarixi və `excused_counts` yalnız vahid testlərdədir.
- **T9** (aşağı–orta) — Təsdiqləndi. Test əlavə edildi: tələbə başqasının göndərişini oxuya bilmir. Təqvim lentinin qrup
  və yarımqrup süzgəcinin mənfi testi qalır.
- **T10** (aşağı) — Təsdiqləndi:
  - üzrlü dərs testində `UPDATE` 0 sətrə toxuna bilirdi, indi sətri özü yaradır;
  - QR vərəqi testi kodun içindəki ünvanı yoxlamırdı, indi yoxlayır.
  10 testin fayl daxilində sıradan asılılığı qalır: pytest faylı yazıldığı sırada işlədir. Ayrıca işlədilən testlər üçün
  modul fixture-ları sonraya saxlanılır.

## Yoxlanmayanlar

- P8–P9 və L9 brauzerdə yalnız qismən yoxlanıb. JS test mühiti yoxdur.
- R1 üçün otaq səhifəsi demo məlumatda yoxlanıb. Real cədvəldə yox.
- J2-nin siyasəti (davamiyyəti olmayan fənndə yekun qiymət yoxdur) sahiblə təsdiqlənməlidir.
- J11 sahibin qərarıdır.
- Alt prosesdə işə salınan serverlər (`test_run`, `test_concurrency`, `test_multiworker_state`) real tarixi işlədir.
  Onların heç biri tarixə bağlı fakt yoxlamır.
- İmtahan sessiyası, yay və semestrin dəyişməsi kimi sərhəd tarixlər artıq təsadüfən sınanmır. Onlara ayrıca test
  lazımdır.
- `test_import::test_a_new_batch_revokes_the_old_codes` yüklü maşında bir dəfə 500 verdi (ehtimal ki, 200 ms
  qoruyucusu). CI-da qeyri-sabit ola bilər.
