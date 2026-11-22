# Forma №3 — kafedranın akademik yükü: oxunma qaydaları

Bu sənəd Zəka-nın Forma №3 faylını necə oxuduğunu müəyyən edir (Task 47). Qaydalar iki kafedranın 2026/2027-ci tədris
ili üçün təqdim etdiyi faylların tam təhlilinə əsaslanır. Həmin fayllar repoya daxil edilmir: onlarda əməkdaşların adı,
elmi dərəcəsi və ştat bölgüsü var. Bu sənəddə heç bir şəxsin adı və heç bir xananın mətni yoxdur; yerlər yalnız ünvanla
göstərilir: `rt#0!A21` (fayl, vərəqin sıra nömrəsi, xana), `mr#12` (vərəq). Testlər eyni quruluşlu uydurma nümunələrlə
işləyir (`tests/fixtures/make_fixtures.py` → `tests/fixtures/forma3_blocks.xlsx`, `forma3_sheets.xlsx`).

Kod: `backend/zeka/modules/integration/forma3.py` (oxuyucu, giriş-çıxışsız), `forma3_text.py` (qrammatikalar),
`tables.py` (XLSX), `importer.py` (idxal). Qaydaların nömrələri (G1, H3, J1 …) kodda və testlərdə eynidir
(`tests/unit/test_forma3.py`).

İstifadə yeri: `teaching-load` idxalı (tədris vahidləri), sillabusun saat bölgüsü (Task 23) və semestr cədvəlinin
qurulması.

## 1. Faylı yükləməzdən əvvəl yoxlama

```bash
python backend/manage.py forma3-check FAYL.xlsx          # yoxlamalar, saylar, konfliktlər (xana ünvanı ilə)
python backend/manage.py forma3-check FAYL.xlsx --json   # tam hesabat (fayldakı adlarla birlikdə)
```

Əmr bazaya toxunmur. Adi çıxışda ad və xana mətni olmur, yalnız ünvanlar və saylar verilir. Çıxış kodu: `0` — bütün
ştatlar və bölmələr tətbiq oluna bilər; `1` — ən azı biri bloklanıb; `2` — fayl Forma №3 kimi oxunmur.

Eyni hesabat idxal səhifəsində (`/admin/import`, «Yoxla») göstərilir: hər ştat və ya bölmə üzrə vəziyyət (tətbiq oluna
bilər, bloklanıb, gizli vərəq), T1–T3 yoxlamaları, konfliktlər və qeydlər (xana ünvanı ilə), dərs olmayan yükün növlər
üzrə cəmi. Bloklanmış ştatın və ya bölmənin heç bir dərsi tətbiq olunmur; fayl düzəldilib yenidən yoxlanır.

## 2. İki quruluş

| | A: bir vərəqdə müəllim blokları | B: hər müəllimə bir vərəq |
|---|---|---|
| Müəllim | Blokun ştat sətri (A–AI üzrə birləşdirilmiş) | `E4` xanası |
| Başlıq | Bir sətir: `Sıra sayı`, `Qruplar`, `Fənlər`, `Tələbələrin sayı`, sonra saat sütunları | İki sətir (7–8): `FƏNNİN ADI`, `QRUP №-si`, `Tələbələrin sayı`, `Birləşmənin işarəsi`, sonra saat sütunları |
| Hissələr | Blok: üç başlıq sətri, ştat sətri, semestr yazıları, başlıq, nömrə sətri, məlumat sətirləri, `Cəmi` | Bölmə: birləşdirilmiş başlıq (`1 ŞTAT`, `Saat hesabı` …), məlumat sətirləri, `CƏMİ`, `Aktiv` sətri |
| Saat hesabı | Ştat sətri `saat hesabı` ilə başlayan ayrıca blok | `Saat hesabı` başlıqlı bölmə və ya bütöv vərəq |
| Digər müəllim | Sütun yoxdur | `Digər dərs yüklərini aparan müəllimlər` (AT) |
| Əlavə vərəqlər | Arayış cədvəli, müəllimlərin siyahısı, boş şablonlar | Yoxdur |

Quruluş başlığın məzmununa görə təyin olunur, vərəqin adına görə yox (G3).

## 3. Oxunan məlumat

Oxuyucu `read(sheets) -> Form` qaytarır. Formanın gördüyü hər şey aşağıdakı siyahılardan birindədir.

- **Vərəq**: sıra nömrəsi, ad, vəziyyət (görünən, gizli), sinif (`form-A`, `form-B`, `summary`, `list`, `empty`, `unknown`),
  idxal olunub-olunmadığı və səbəbi.
- **Ştat (post)**: A quruluşunda blok, B quruluşunda bölmə. Ünvan (ştat sətrinin və ya bölmə başlığının xanası), məlumat
  sətirləri, `Cəmi` sətri, müəllimin adı (fayldakı kimi və adlıq halda), elmi dərəcə, vəzifə, ştat vahidi (`1`, `0,5`),
  iş növü (`main` — əsas iş yeri, `internal` — daxili əvəzçi, `external` — kənar əvəzçi, `substitute-unspecified` —
  yalnız «əvəzçi»; yazılmayıbsa boş qalır, ehtimal edilmir), ödəniş (`staff` — ştat, `hourly` — saat hesabı), vakansiya və
  onun sahəsi, məsləhətçi professor, tədris ili və onun fərqli olması, ikinci ştat (B), vərəqin adında olub xanalarda
  olmayan sözlər.
- **Dərs (unit)**: bir semestrin bir mühazirəsi, məşğələsi və ya laboratoriyası. Ştat, müəllim (vakansiyada boş), saat
  hesabı işarəsi, fənn (fayldakı mətn və müqayisə açarı), semestr (`payiz`, `yaz`), növ, saat (xanadakı kimi: `7.5`, `14`,
  `20` yuvarlaqlaşdırılmır), qruplar (`kod`, tələbə sayı, sətir), tələbələrin cəmi, birləşmiş olması, lövbər xana (saatın
  yazıldığı sol yuxarı xana), birləşdirmə aralığı, digər müəllimlər (yalnız qeyd kimi), işarələr (`group_missing`,
  `students_missing`, `subject_missing`, `hours_not_multiple_of_15`, `fractional_week`, `year_conflict`, `hidden_row`,
  `code_looks_wrong`).
- **Yük sətri (load)**: həftəlik dərs olmayan saat: məsləhət, məqbul, imtahan, imtahan suallarının hazırlanması, kurs
  layihəsi, referat, magistr işi, dissertasiyaya rəhbərlik və məsləhət, tədqiqat, layihələrin idarə olunması, təcrübə,
  aspirantlara dərs, doktorantura, dövlət attestasiyası, buraxılış işi, dərslərdə iştirak, digər yük, digər kafedranın
  yükü. Semestr, saat, xana, qruplar və tələbələrin cəmi ilə.
- **Əlaqə (link)**: təklifdir, oxuyucu onu tətbiq etmir: eyni fənnin mühazirəsi ilə başqa ştatdakı məşğələsi, boş
  birləşdirmənin başqa ştatdakı qarşılığı, AT sütunundakı ad, bir neçə fənni əhatə edən yük xanası.
- **Qeyd (note)**: formadan kənar və ya izah tələb edən dəyər: xana və səbəb.
- **Konflikt (conflict)**: xana və ya aralıq, kod, Azərbaycan dilində səbəb, bloklayıb-bloklamadığı. Bloklayan konflikt
  olan ştatın dərsləri oxunur və göstərilir, lakin şəxs faylı düzəltməyincə tətbiq olunmur.
- **Yoxlama (control)**: T1–T6 hesab yoxlamalarının hər biri: gözlənilən, tapılan, nəticə.

## 4. Ümumi qaydalar

- **G1. Yalnız saxlanmış dəyər.** Xananın faylda saxlanmış dəyəri oxunur; düstur hesablanmır. Məlumat sətrinin saat
  xanasında ədəd olmayan mətn bloklayan konfliktdir. Xəta dəyəri (`#REF!`, `#NAME?`) yalnız `Cəmi` sətrində və formadan
  kənarda yol veriləndir (K1).
- **G2. Birləşdirilmiş xana.** Dəyər sol yuxarı xanadadır və bir dəfə sayılır. Örtülən xanada dəyər varsa, bloklayan
  konfliktdir.
- **G3. Vərəq məzmununa görə təsnif olunur.** `form-A`, `form-B`, arayış cədvəli (`summary`), müəllimlərin siyahısı
  (`list`), boş vərəq (`empty`), qalanı `unknown` (hesabatda göstərilir). Vərəqin adı heç nəyi həll etmir.
- **G4. Gizli vərəq və sətir.** Gizli vərəq oxunur, dərsləri və saatları ilə siyahıda göstərilir, lakin idxal olunmur.
  Dəyəri olan gizli sətir qeyd alır.
- **G5. Tədris ili.** Hər ştatın tədris ili oxunur (A: ştat sətrinin üstündəki üç başlıq sətrindən il yazılanı; B:
  `AE4`). Faylın ili çoxluğun ilidir. Başqa ili olan ştat oxunur, `year_conflict` alır və bloklanır; səssiz atılmır.
- **G6. Müqayisə açarları.** Fənn adı müqayisə üçün kiçik hərfə çevrilir (Latın `I` = `İ`), boşluqlar yığılır, tire
  növləri birləşdirilir, tirenin ətrafındakı boşluq silinir (` - 2` = `-2`). Fayldakı mətn həmişə saxlanılır. Əlaqə
  təklifləri üçün əlavə olaraq `İFS:` ön şəkilçisi, kurs kodu və sondakı ingiliscə mötərizə atılır; dərslər bu açarla
  heç vaxt birləşdirilmir.
- **G7. Qrup kodu.** Kod bütün boşluqlar silinmiş mətndir. Yarımqrup yazılışı yoxdur: sondakı rəqəm və ya ` 1`, ` 2`,
  ` 3` kodun hissəsidir. Kod `M` + 3 rəqəm və ya 4 rəqəm, sonra 1–3 hərf və ən çoxu 2 rəqəm quruluşuna uyğun gəlmirsə və
  ya qəbul ili (3–4-cü rəqəmlər) faylın ilindən əvvəlki altı ilə düşmürsə, «kod düzgün görünmür» xəbərdarlığı verilir
  (bloklamır, düzəldilmir). Reyestrdə olan kod heç vaxt belə işarələnmir.
- **G8. Tələbə sayı.** D sütunu qrupun ümumi sayını yox, həmin dərsdəki tələbələrin sayını göstərir; sətir üzrə
  saxlanılır. Dərs sətrində boşdursa, `students_missing`; tam ədəd deyilsə, bloklayan konflikt. Eyni qrupun müxtəlif
  sətirlərdə fərqli sayı qeyd olunur, ortalama götürülmür.
- **G9. Səssiz heç nə.** Forma vərəqinin hər dolu xanası bunlardan yalnız birinə düşür: dərs, yük, ştat məlumatı,
  başlıq, cəm, əmsal sətri, imza sətri, quruluş, qeyd, konflikt. Heç birinə düşməyən xana ayrıca sayılır və bu say sıfır
  olmalıdır. Məlumat sətirləri olub dərsi oxunmayan forma vərəqi özü konfliktdir.

## 5. Başlıq və semestr

- **H1. Başlıq zolağı.** Fənn və qrup başlıqlarının olduğu sətir və fənn başlığının şaquli birləşdirməsinin örtdüyü
  sətirlər. Sütunun adı zolaqdakı ən aşağı dolu başlıqdır. Zolaq formanın sütunları ilə məhdudlaşır (A: A–AI; B: A–AT);
  ondan sağdakı dəyər qeyddir.
- **H2. Nömrə sətri.** Zolaqdan sonrakı sətrin bütün dolu xanaları tam ədəddirsə, o keçilir və sütunları
  uyğunlaşdırmaq üçün istifadə olunmur.
- **H3. Semestr `Cəmi` sütunları arasındakı mövqedir.** Tələbə sayından sonra soldan sağa: birinci `Cəmi` sütunu payız
  qrupunu, ikincisi yaz qrupunu bağlayır, `İl ərzində cəmi` ilin cəmidir. Ondan sonrakı sütunlar semestrdən kənardır.
  Qruplar arasındakı başlıqsız sütunun (B: Y) dəyəri heç vaxt yük deyil.
- **H4. Semestr yazıları yalnız təsdiqləyir.** `payız semestri` və `yaz semestri` yazıları öz qrupunun sütunlarının
  əksəriyyətini örtməli, payız yazdan solda olmalıdır. Yazı sütun-sütun oxunmur: A quruluşunda payız yazısı yaz
  mühazirəsinin sütununu da örtür. H3-ə zidd yazı ştatı bloklayır.
- **H5. Sütun başlıqları.** Hər semestr qrupunda dəqiq bir `Mühazirə`, bir `Məşğələ` və bir `Laboratoriya` olmalıdır;
  qalan sütunlar adına görə oxunur (bölmə 9). Başlığı pozulmuş sütun (yerində başqa mətn) atılmır: A quruluşunda vərəqin
  digər bloklarının, B quruluşunda faylın digər vərəqlərinin yekdil başlığı götürülür və bloklamayan konflikt yazılır;
  yekdillik yoxdursa, ştat bloklanır. A quruluşunda blok başlıqlarında `Buraxılış işi` adlanan AF sütunu doktorantura
  yükü kimi oxunur və bu bir dəfə qeyd olunur. Sətrin öz adı (TD, MD rəhbərlik, təcrübə) sütunun başlığına zidd olduqda
  yükün növünü sətrin adı müəyyən edir və xana qeyd alır.
- **H6. Semestrin hesabla sübutu.** Hər ştatın `Cəmi` sətrində: birinci `Cəmi` = payız sütunlarının cəmi, ikinci `Cəmi` =
  yaz sütunlarının cəmi, il = ikisinin cəmi (fərq ən çoxu 0,02). Uyğun gəlməyən ştat bloklanır.
- **H7. Digər müəllim sütunu (B).** Başlığı «digər dərs yü…» ilə başlayan və «müəllim» sözü olan sütundur (yazılış
  səhvləri ilə birlikdə). `Digər dərs yükü` başlıqlı sütunlar saat sütunlarıdır.

## 6. A quruluşu

- **A1–A3. Blokun başlanğıcı quruluşa görədir.** Ştat sətri A–AI üzrə birləşdirilmiş, birbaşa semestr yazıları sətrinin
  üstündə duran sətirdir; semestr yazıları isə birbaşa başlığın üstündədir. Mətn nümunəsi axtarılmır: «ştat» sözü
  olmayan ştat sətri də öz blokunu açır. Ştat sətrinin üstündəki üç sətir başlıq sətirləridir, nə yazılmasından asılı
  olmayaraq; gözlənilməyən mətn qeyddir.
- **A4. Vərəqin öz başlığı.** Vərəqin əvvəlindəki başlıq, yazı və kafedranın cəm sətri blok deyil; cəm sətri yalnız
  yoxlamadır (T6).
- **A5. Blokun sonu.** Başlıqdan sonra A–D xanalarında mətni `Cəm` ilə başlayan ilk sətir. Bloklar arasındakı dəyər
  qeyddir.
- **A6. Ştat sətrinin qrammatikası** (böyük-kiçik hərf və boşluqlar sərbəstdir):
  `ştat vahidi «ştat» [iş növü] [-] şəxs` | `«saat hesabı» və ya «saathesabı» [-] şəxs` | `«vakansiya» [sahə]`.
  Ştat vahidi: `1`, `0,5`, `0.5`. İş növü: `əvəzçi`, `kənar`, `daxili`. Şəxs: elmi dərəcə (nöqtəli kiçik hərfli
  qısaltma), vəzifə (`professor`, `məsləhətçi professor`, `dosent`, `dos`, `baş müəllim`, `müəllim`, `assistent`,
  `doktorant`, `kənar doktorant`), sonra 2–4 sözdən ibarət ad. «oğlu» və ya «qızı» olmayan ata adı və ya ata adının
  olmaması yol veriləndir və yalnız qeyd olunur. Oxunmayan ştat sətri bloku bloklayır; dərsləri müəllimsiz qaytarılır.
- **A7. İş növü və arayış cədvəli.** Ştat sətrinin mətni iş növünü etibarlı göstərmir. Arayış cədvəli varsa, iş növü
  onun bölməsindən götürülür (ştatda olanlar, daxili əvəzçilik, kənar əvəzçilik, saat hesabı, məsləhətçi professorlar,
  vakant yük). Sətir blokla düsturun göstərdiyi xanaya görə, düstur yoxdursa, illik cəmə və ada görə əlaqələndirilir.
  Fərq olduqda iş növündə arayış cədvəli əsas götürülür və qeyd yazılır; elmi dərəcə və vəzifə fərqləri yalnız qeyd
  olunur, reyestr dəyişdirilmir. Arayış cədvəlində olmayan forma vərəqinin bloku bloklanır («kafedranın cəminə daxil
  deyil»).
- **A8–A10.** Eyni şəxsin bir neçə bloku ayrı ştatlardır. Saat hesabı bloku adi dərslərdir, `hourly` işarəsi ilə (P2).
  Vakansiya blokunun müəllimi yoxdur (P3). Rəhbərlik sətrində başqa şəxsin adı varsa, qeyd yazılır; saat yazıldığı
  blokda qalır.
- **A12–A13.** AI sütunundan sağdakı köməkçi cəmlər və əl qeydləri heç vaxt məlumat deyil. A sütunundakı sıra nömrəsi
  heç vaxt açar deyil.

## 7. B quruluşu

- **B1–B2. Müəllim `E4` xanasındandır.** Elmi dərəcə və vəzifə sözləri atılır; yiyəlik hal adlıq hala gətirilir
  (`oğlunun` → `oğlu`, `qızının` → `qızı`); bitişik yazılmış ad və ata adı ayrılır; ata adı olmayan ad yol veriləndir və
  qeyd olunur. Mətn `vakansiya` ilə başlayırsa, müəllim yoxdur; mötərizədəki və ya sondakı mətn vakansiyanın sahəsidir.
  Şəxsin adından sonrakı mötərizə ştatın qeydidir. Vərəqin adı ilə `E4` sözlərin çoxluğu kimi müqayisə olunur;
  uyğunsuzluq qeyddir.
- **B3–B4. Bölmələr.** Bölmə başlığı B xanasından AS və ya AT-yə qədər birləşdirilmiş, qrupu və saatı olmayan sətirdir.
  Boşluqsuz yazılışı `saathesab` ilə başlayan başlıq saat hesabıdır; `ştat` sözü olan başlıq ştatdır
  (`[əsas iş yeri üzrə] ştat vahidi ştat [iş növü]`). Hər ikisi olmayan başlıq yalnız vakansiya vərəqində sahə adıdır;
  başqa halda bloklayan konfliktdir. Eyni vərəqdəki ikinci ştat bölməsi ayrıca ştatdır və birincidən heç nə götürmür.
  Heç bir başlıq oxumanı dayandırmır: saat hesabı bölməsi də eyni başlıqla oxunur.
- **B5. Bölmənin sonu.** Əvvəlcə yazılı cəm sətri (`CƏMİ`, `Cəmi`) axtarılır. Yoxdursa, yazısız cəm sətri: məlumat
  sətirlərindən sonra fənni və qrupu olmayan, saat xanaları sütun cəmlərinə bərabər olan və ya bütün saat xanaları dolu
  olan, ya da birbaşa əmsal sətrinin üstündə duran ilk sətir. Yalnız sıfır cəmləri olan sətir nə cəm, nə məlumatdır.
  Cəmdən sonra əmsal sətri (`Aktiv`) ola bilər. Cəmdən sonra, növbəti başlıqdan əvvəl fənni, qrupu və ya saatı olan sətir
  bloklayan konfliktdir.
- **B6–B7.** Vərəq «kafedrasının müdiri» sətri ilə bitir. `Birləşmənin işarəsi` sütunundakı dəyər göstərilir və heç
  vaxt şərh olunmur; birləşmə yalnız birləşdirilmiş xana ilə bildirilir.
- **B8–B9.** Vərəqdəki hər saat vərəqin müəlliminə (və ya vakansiyaya) aiddir. Məlumat sətri olmayan vərəq sıfır yüklü
  müəllimdir və hesabatda göstərilir.

## 8. Sətirlər, dərslər və birləşmiş dərslər

- **R1. Sətrin sinfi** (ilk uyğun gələn): dərs sətri (qrup və auditoriya saatı); axının üzvü (öz saatı yoxdur, dəyərli
  birləşdirmə örtür); qrupu olan yük sətri (yalnız dərs olmayan saat); xüsusi yük sətri (qrupsuz: TD, MD, təcrübə);
  qrupu göstərilməyən dərs sətri (R5); fənni olmayan sətir (R2); saatsız qrup sətri; fənn başlığı sətri; yalnız sıra
  nömrəsi olan sətir; sıfır sətri; saat sütununda yalnız mətn olan sətir.
- **R2. Sətrin fənni** öz xanasındakı və ya onu örtən şaquli birləşdirmənin sol yuxarı xanasındakı mətndir. Yuxarıdakı
  sətirdən heç vaxt götürülmür. Fənni boş, birləşdirmədən kənar məlumat sətri bloklayan konfliktdir (yuxarıdakı sətrin
  fənni təklif kimi göstərilir).
- **R3. Dərs.** Məlumat sətrinin hər sıfırdan fərqli sol yuxarı auditoriya xanası (mühazirə, məşğələ, laboratoriya)
  dəqiq bir dərsdir.
- **R4. Təkrarlanan fənn ayrı dərsdir.** Ardıcıl sətirlərdə eyni fənnin hər birinin öz birləşdirilməmiş saatı varsa,
  bunlar ayrı dərslərdir və saatları toplanıb bir dərsə çevrilmir.
- **R5. Qrupu göstərilməyən dərs** saxlanılır, `group_missing` alır və ştatı bloklayır.
- **R6. Saatsız qrup sətri** dərs yaratmır, lakin onu örtən dəyərli birləşdirmənin üzvü qalır. «Qrupun nə dərsi, nə
  yükü var» qeydi yalnız heç bir dərsi və yükü olmayan qrup sətrinə verilir.
- **J1. Mühazirə axını.** Dəyəri olan şaquli birləşdirilmiş mühazirə xanası örtdüyü bütün sətirlərin qrupları üçün bir
  mühazirədir; tələbə sayı sətirlərin cəmidir; `Cəmi` sətrində bir dəfə sayılır.
- **J2. Birləşmiş məşğələ və laboratoriya.** Eyni qayda: birləşdirilmiş xana bütün örtülən qruplar üçün bir dərsdir.
- **J3. Boş birləşdirmə** dərs yaratmır. Şaquli boş birləşdirmə başqa ştatda keçilən birləşmiş dərsi göstərir: oxuyucu
  eyni qrupların, növün və semestrin dəyərli dərsini faylda axtarır və əlaqə təklif edir; tapılmırsa, «dərs bu faylda
  yoxdur» qeydi yazılır. Bir neçə saat sütununu örtən birləşdirmə boşdursa qeyd, dəyərlidirsə bloklayan konfliktdir
  (dərsin növü bilinmir).
- **J4. Dərs birləşdirməsi bir fənnin daxilində qalır.** Müxtəlif fənlərin sətirlərini örtən dəyərli dərs
  birləşdirməsi bloklayan konfliktdir (fənn mətni eynidirsə, yol veriləndir). Yük xanalarının birləşdirməsi bu qaydaya
  tabe deyil; bir neçə fənni örtəni qeyd olunur.
- **J5. Axın üzvünün öz məşğələsi və ya laboratoriyası** bir qruplu ayrıca dərsdir.
- **J6. Mövqeyə görə ehtimal yoxdur.** Qrupun dərsə aidliyi yalnız birləşdirmədən bilinir. «Öz mühazirəsi olmayan
  sətir əvvəlki mühazirəyə qoşulur» qaydası ləğv edilib.
- **J7. Ştatlararası əlaqələr yalnız təklifdir.** Mühazirənin məşğələsi və ya laboratoriyası çox vaxt başqa blokda və
  ya vərəqdədir. Oxuyucu fənn, qrup və semestr üzrə əlaqə təklif edir; dərslər birləşdirilmir. Faylda mühazirəsi
  olmayan məşğələ və ya əksinə məlumat xarakterli qeyddir, konflikt deyil.

## 9. Digər müəllim, ödəniş, vakansiya, yük

- **O1. AT sütunu (B) digər müəllimi göstərir, sahibi yox.** Vergüllə ayrılan adlar bölünür; birləşdirilmiş AT xanası
  örtdüyü bütün sətirlərə aid edilir. Adlar yalnız yoxlama üçündür: həmkarın vərəqində uyğun dərs tapılmırsa və ya
  faylda belə müəllim yoxdursa, qeyd yazılır. Saat heç vaxt başqa müəllimə keçirilmir.
- **O2. AI sütunu (A)** digər kafedranın saatla yüküdür: semestrsiz yük sətri.
- **P1–P2. Saat hesabı real dərslərdir.** Saat hesabı bloku və bölməsi adi qaydada oxunur, dərsləri `hourly` işarəsi
  alır.
- **P3. Vakansiya.** Müəllim boşdur, `vacancy` işarəsi və sahə mətni saxlanılır. İdxalda bu, «müəllim tapılmadı»
  konflikti deyil, təyin olunmamış yükdür.
- **P4. Bir şəxsin bir neçə ştatı.** Cədvəldə bir müəllimdir; hər dərs öz ştatını saxlayır.
- **L1. Dərs olmayan sütunlar yük sətirləridir** (başlığa görə, semestr və xana ilə). Birləşdirilmiş yük xanası örtdüyü
  bütün qruplar üçün bir yük sətridir və bir dəfə sayılır.
- **L2. Xüsusi sətirlər** (doktorantura rəhbərliyi, magistr dissertasiyası, təcrübə) mətninə və sütununa görə tanınır;
  yalnız yük sətri verir.
- **L3. `Aspirantlara dərs`** sütunundakı saat yük sətridir və kafedra cavab verənədək bloklayan sualdır (sual 15).
- **L4. İmtahan və məsləhət saatları** yükdür. İmtahan saatı tələbə sayının üçdə birindən (birləşdirilmiş xanada
  tələbələrin cəmindən) 0,05-dən çox fərqlənirsə, məlumatın keyfiyyəti barədə qeyd yazılır.
- **K7. Qarışıq semestrli sətir.** Sətrin dərsi olmayan semestrdə yükü varsa, yük sütunun semestrinə yazılır və «sütun
  səhv seçilmiş ola bilər» qeydi verilir.

Sütun başlıqları (semestr qrupu daxilində, G6 açarı ilə, ön hissəyə görə):

| Başlıq | Nəticə |
|---|---|
| Mühazirə · Məşğələ (Məşğələ, seminar) · Laboratoriya | Dərs: `lecture` · `seminar` · `lab` |
| Məsləhət · Məqbul · İmtahan · İmtahan suallarının hazırlanması | Yük: `consultation` · `credit` · `exam` · `exam_prep` |
| Kurs layihəsi (işi) · Referat · Magistrların işi | Yük: `course_project` · `essay` · `master_work` |
| Magistr dissertasiyasına rəhbərlik · məsləhət | Yük: `master_supervision` · `master_consulting` |
| Tədqiqat işinin aparılması · Layihələrin idarə olunması | Yük: `research` · `project_management` |
| Təcrübə · Təcrübəyə rəhbərlik | Yük: `practice` (sətrin adı üstündür, H5) |
| Aspirantlara dərs · Doktorantura | Yük: `phd_teaching` (L3) · `doctoral` |
| DAK, İEŞ · Buraxılış işi (B) · Müəllimlərin dərslərdə iştirakı | Yük: `state_exam` · `graduation` · `class_visits` |
| Digər dərs yükü (B) · Digər kafedranın dərs yükü (A) | Yük: `other_load` · `other_department` (semestrsiz) |
| Cəmi · İl ərzində cəmi | Yalnız yoxlama |
| Digər dərs yü…lərini aparan müəllimlər (B) | Digər müəllimlər (qeyd) |
| Başlıqsız sütun (B, Y) | Heç vaxt yük deyil (qeyd) |

## 10. Hesab yoxlamaları

Ştat yalnız T1–T3 yoxlamalarının hamısı keçdikdə qəbul olunur; əks halda dərsləri uyğun gəlməyən sütunu göstərən
bloklayan konfliktlə qaytarılır və idxal həmin ştatdan heç nə tətbiq etmir.

- **T1. Sütunlar.** Hər saat sütununda məlumat sətirlərinin sol yuxarı xanalarının cəmi (birləşdirilmiş dəyər bir dəfə)
  `Cəmi` sətrindəki xanaya bərabərdir (fərq ən çoxu 0,011). `Cəmi` sətrindəki boş xana sıfır sayılır; sıfırdan fərqli
  sütun cəminin üstündə boş xana konfliktdir.
- **T2. Semestrlər.** H6 bərabərlikləri.
- **T3. Dərslər və yük cəmi örtür.** Semestr və növ üzrə dərs saatlarının cəmi `Cəmi` sətrinin auditoriya xanasına,
  dərslərlə yükün cəmi isə semestrin yenidən hesablanmış cəminə bərabərdir. Bu, birləşdirmə qaydasını da sübut edir.
- **T4. Sətirlər (yalnız xəbərdarlıq).** Sətrin semestr və il cəmləri saat xanalarından yenidən hesablanır; fərq
  bloklamayan qeyddir. Boş sətir cəmi sıfır sayılır; birləşdirilmiş sətir cəmi örtdüyü sətirlərin cəmi ilə tutuşdurulur.
- **T5. Faylın sayları.** Dərslərin sayı = məlumat sətirlərindəki sıfırdan fərqli sol yuxarı auditoriya xanalarının
  sayı; onların saatlarının cəmi.
- **T6. Arayış yoxlamaları (fayl səviyyəsində, xəbərdarlıq).** A: blokların illik cəmlərinin cəmi vərəqin cəm sətrinə,
  arayış cədvəlinin hər sətri öz blokunun illik cəminə və auditoriya saatına (doktorantura rəhbərliyi daxil), vakant yük
  bölməsinin cəmi vakansiya blokuna bərabərdir (fərq ən çoxu 0,02).
- **K1. `Cəmi` sətrində xəta dəyəri.** T1 və T2 oxuna bilən xanalar üzrə aparılır, xəta xanası sətirlərdən yenidən
  hesablanır və bloklamayan konflikt yazılır.
- **K2–K5.** Köhnəlmiş və ya səhv diapazonlu düsturlar dəyər oxunuşuna təsir etmir (həqiqət sətirlərdən hesablanan
  cəmdir); düstur mətni olduqda qeyd yazılır. Auditoriya saatı başqa saat xanalarından düsturla hesablanıbsa, saxlanmış
  dəyər oxunur və qeyd yazılır.

Qəbul nəticəsi (iki real fayl, yalnız lokal yoxlama, 2026-11-22): A quruluşlu faylda əsas vərəqdə 348 dərs və 7 942
auditoriya saatı; B quruluşlu faylda 1 245 dərs və 29 783,5 saat, onlardan 12-si gizli vərəqdədir və idxal olunmur
(1 233). Bütün ştatlar və bölmələr T1–T3-dən keçir; heç bir qaydaya düşməyən xana yoxdur.

## 11. İdxal (`teaching-load`)

- Yalnız görünən vərəqlərin bloklanmamış ştatlarının dərsləri planlaşdırılır. Bloklanmış ştat (bloklayan konflikt,
  fərqli tədris ili, keçməyən T1–T3) və gizli vərəq hesabatda siyahı ilə göstərilir.
- Müəllim, fənn və qruplar reyestrdə axtarılır; tapılmayan dərs konflikt kimi lövbər xanası ilə siyahıya düşür. Forma
  heç vaxt istifadəçi, fənn və ya qrup yaratmır. Reyestrdə eyni adlı iki şəxs varsa və fayldakı ad onları ayırmırsa,
  dərs «müəllim tapılmadı» kimi göstərilir; seçim ehtimalla edilmir.
- Vakansiya dərsi müəllimsiz yazılır (`teacher_id` boş, `vacancy = 1`). Hər tədris vahidi ödənişi (`pay`: `staff`,
  `hourly`), ştatın ünvanını (`post_ref`) və lövbər xanasını (`anchor`) saxlayır (`0470_forma3_units.sql`).
- Qrup kodunun sonluğundan yarımqrup düzəldilmir (`subgroup` boşdur).
- Eyni açarlı (müəllim, fənn, semestr, növ, qruplar, ödəniş) iki dərs iki ayrı tədris vahididir: saatlar toplanmır,
  ikincisi fayldakı sırası ilə fərqləndirilir. Eyni faylın təkrar idxalı heç nəyi dəyişmir.

## 12. Kafedranın cavablandıracağı suallar

Bu suallara yalnız kafedra cavab verə bilər. Cavab gələnədək oxuyucu yuxarıdakı qaydalarla işləyir və hər halı qeyd və
ya konflikt kimi göstərir.

1. Sonu boşluq və rəqəmlə bitən qrup kodları (`mr#1!C11:C13`, `mr#39!C11:C13`, `mr#49!C25:C27`) üç ayrı qrupdur
   (tələbə sayları və imtahanlar belə göstərir), yoxsa bir qrupun yarımqrupları?
2. Qrup kodlarının sonluqları nə deməkdir? Bəzi qruplar qiyabidirmi və həftə sayı fərqlidirmi? Vərəq adında mötərizədə
   yazılan, xanalarda təkrarlanmayan söz (`mr#73`–`mr#77`, `mr#79`–`mr#82`) səhər növbəsini bildirirmi? Düzgün görünməyən kodlar (`rt#0!B33`, `rt#0!B405`,
   `rt#0!B510`, `mr#95!C19`, `mr#73!C11`, `mr#74!C12`) yazılış səhvidirmi? Üçrəqəmli kodlar ailəsi (`rt#0`, 8 sətir, məs.
   `B89`, `B121`, `B137`, `B311`) realdırmı və `B137` ilə `B311` eyni qrupdurmu? `mr#88!C15` ilə `mr#30!C42`,
   `mr#45!C17:C19` eyni qrupdurmu; `mr#59!C26` nədir?
3. Həftəlik saat üçün semestrdə neçə həftə götürülür (15?) və 15-ə bölünməyən saatlar (məs. `rt#0!S12`, `T32`, `T33`,
   `S143`, `U143`, `E152`, `E213`, `E427`; `mr#45!F17`, `H18`, `Z24`, `mr#88!F15`, `H15`, `mr#61!F14`), o cümlədən 7,5
   saat (iki həftədən bir?) cədvələ necə salınır?
4. Eyni qrupun fərqli tələbə sayları olan yerlərdə (G8) hansı say düzgündür və otaq tutumu reyestrdən götürülməlidirmi?
5. Vakant yükü (`rt#0!A223`, `mr#94`–`mr#96`) kim aparır? Vakansiya blokunda rəhbərin adı yazılmış dörd doktorantura
   sətri (`rt#0!C247:C250`, `C13` və `C14`-dəki eyni rəhbər) kimin yüküdür?
6. `rt#1` vərəqi (başqa tədris ili, 3 sətir, heç bir cəmə daxil deyil) cari yükdür, yoxsa qalıq?
7. `mr#83` (gizli, əvvəlki tədris ili) köhnəlibmi? `mr#51` (görünən, `AE4`-də əvvəlki tədris ili, digər vərəqlərin AT
   sütununda adı çəkilir) başlığı köhnəlmiş cari yükdürmü? `rt#0!A221` (vakansiya blokunun üstündə başqa il, cari
   cəmlərə daxildir) də eynidirmi?
8. İş növləri: `rt#0` ştat sətirləri ilə `rt#4` və `rt#5` arasındakı fərqlər (`A7`; `A21`, `A488`, `A504`, `A518`-də
   yalnız «əvəzçi»; `A420`-nin vəzifəsi; A7 qaydasında sadalanan dərəcə və vəzifə fərqləri); `mr#40` vərəqinin adı ilə
   `B10` başlığı; B quruluşunda ikinci bölmələrin (`mr#6`, `mr#12`, `mr#13`, `mr#18`, `mr#43`, `mr#44`) və iş növü
   yazılmamış başlıqların daxili və ya kənar əvəzçilik olması.
9. Faylda mühazirəsi olmayan məşğələlər (məs. `mr#85!AA13:AA17`) və məşğələsi olmayan mühazirə (`mr#73!Z18:Z20`): digər
   hissə başqa kafedranın faylındadırmı? Vərəqi olmayan AT adları (`mr#43!AT13:AT16`, `AT21:AT25`, `mr#58!AT20`) kimdir?
10. AT sütunu adı çəkilən həmkarın öz vərəqinə zidd olduqda (O1) dərsi əslində kim aparır?
11. Fənnin eyniliyi: `İFS:` ön şəkilçili ad şəkilçisiz adla (`rt#0!C204` və `C306`), alət siyahısı olan və olmayan ad
    (`mr#72!B11` və `mr#82!B11`), ingiliscə mötərizəli variantlar, ingiliscə və azərbaycanca paralel magistr adları
    (`rt#0!C493` və `C522`) bir fəndirmi?
12. Təsdiqlənməli məlumat səhvləri: `rt#0!D199`, `D262`, `D181` (tələbə sayı imtahan saatına uyğun gəlmir), `D411`,
    `D412` (boş), 69 və 70-ci sətirlər (təkrar), 571-ci sətir (fənn), `AA239`, `Z240`, `Z244`, `Z245`, `Z246`; `mr#50!B32`
    (fənn), `mr#34!B20` (qrup), `mr#71!R15`, `mr#69` 13-cü sətir, `mr#13!AL20`, `mr#30!B40`, `mr#73!D20`, `mr#82` 12-ci
    sətir, `mr#16` (saylar yerini dəyişib), `mr#11!C34`.
13. `rt#0!F92:F99` həqiqətən 8 qrup və 12 tələbə üçün bir 60 saatlıq dərsdirmi?
14. Kafedralar `Birləşmənin işarəsi` sütununu (B, E) nə vaxtsa dolduracaqmı? Dolduracaqsa, hansı yazılışla?
15. `Aspirantlara dərs` saatları cədvəldə yer tələb edən həftəlik dərslərdirmi?
16. Eyni qruplar üçün eyni fənnin məsləhət və imtahan saatları həm `mr#45`, həm `mr#47` vərəqindədir: ikiqat sayılıbmı?
17. `rt#0` vərəqində AJ sütunundakı adlar (təcrübə sətirlərində, başlıq sətrində `AJ9`, gizli sətirdə `AJ263`):
    təcrübələrə əslində kim rəhbərlik edir?
18. `rt#4!M1:M36` və `N4:N10` aralığındakı 35 addan 11-nin `rt#0`-da bloku yoxdur: yükü olmayan əməkdaşlardır, yoxsa
    yük formaya düşməyib?
19. A quruluşunda AF sütunu bütün bloklarda `Buraxılış işi` adlanır, lakin doktorantura rəhbərliyini saxlayır:
    kafedranın «Doktorantura» nəzərdə tutduğunu təsdiqləyin.
