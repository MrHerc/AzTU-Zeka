# Forma №3 — kafedranın akademik yükü

Mənbə: sahibin 2026-11-18-də verdiyi iki fayl (2026/27 tədris ili). Faylların özü repoya qoyulmur: içində işçilərin adı,
elmi dərəcəsi və ştat bölgüsü var. Testlər eyni quruluşda uydurma nümunə ilə işləyir (`tests/fixtures/forma3_*.xlsx`).

İstifadə yeri: Task 16 (`--kind teaching-load` idxalı → tədris vahidləri) və Task 23 (sillabusun saat bölgüsünün ilkin doldurulması).

## İki tərtibat

| | A: bir vərəq, müəllim blokları | B: hər müəllimə bir vərəq |
|---|---|---|
| Nümunə | RT kafedrası: 35 blok, 74 fənn, 53 qrup | MR kafedrası: 97 vərəq, 131 fənn, 303 qrup |
| Müəllim | Blokun üstündə sətir: `<ştat> - <dərəcə>, <vəzifə>, <Soyad Ad Ata adı>` | `E4` xanası: `<dərəcə>, <vəzifə> <Soyad Ad Ata adı>`; vərəq adı da addır |
| Başlıq | `Sıra sayı`, `Qruplar`, `Fənlər`, `Tələbələrin sayı`, sonra saat sütunları | `SIRA NÖMRƏSİ`, `FƏNNİN ADI`, `QRUP №-si`, `Tələbələrin sayı`, `Birləşmənin işarəsi`, sonra saat sütunları |
| Semestrlər | Başlığın üstündə `payız semestri` və `yaz semestri` | `PAYIZ SEMESTRİ`, `YAZ SEMESTRİ`, `İL ƏRZİNDƏ CƏMİ` |
| Əlavə | `İl ərzində cəmi`, `Digər kafedranın dərs yükü`; ayrıca `saat hesabı Payız/Yaz` və `Arayış cədvəl` vərəqləri | `Digər dərs yüklərini aparan müəllimlər` sütunu; `SAAT HESABI` alt bölməsi |

## Oxuma qaydaları

- Başlıq sətri mətnə görə tapılır (`Fənlər` və ya `FƏNNİN ADI`). Sütun hərfinə güvənilmir: iki kafedrada fərqlidir.
- Başlıqdan sonrakı sətir sütun nömrələridir (`1, 2, 3 …`): keçilir.
- Semestr bloku başlığın üstündəki birləşdirilmiş xanadan təyin olunur; saat sütunları blok daxilində adla oxunur:
  `Mühazirə`, `Məşğələ` (və ya `Məşğələ, seminar`), `Laboratoriya`, `Məsləhət`, `Məqbul`, `İmtahan`,
  `İmtahan suallarının hazırlanması`, `Kurs layihəsi (işi)`, `Təcrübə(yə rəhbərlik)`, `Magistr…`, `Buraxılış işi`, `Cəmi`.
- Fənn adı boş olan sətir əvvəlki fənnin davamıdır: eyni fənnin başqa qrupu. Mühazirə saatı yalnız ilk sətirdədirsə,
  bu, qrupların birləşmiş mühazirə axınıdır; məşğələ və laboratoriya qrup üzrədir.
- Qrup kodunun sonundakı ` 1`, ` 2` yarımqrupdur (məs. `6526e 1`).
- `Digər dərs yüklərini aparan müəllimlər` doludursa, həmin qrupun məşğələ və ya laboratoriyasını başqa müəllim aparır.
- `Cəmi`, `CƏMİ`, `Cəm`, `Aktiv` sətirləri və `SAAT HESABI` bölməsi tədris vahidi deyil. Saathesabı yük ayrıca işarə ilə saxlanır.
- Tələbə sayı olmayan və saat sütunları boş sətirlər (dissertasiya rəhbərliyi, təcrübə) tədris vahidi yaratmır.
- Kəsr saatlar (`3.333…`) imtahan yükünün tələbə sayına görə bölgüsüdür; yuvarlaqlaşdırılmadan saxlanır.

## Tədris vahidinə çevrilmə

Bir sətir × dərs növü (mühazirə, məşğələ, laboratoriya) × semestr, saatı sıfırdan böyükdürsə, bir tədris vahididir:
fənn, semestr, növ, müəllim, qrup (və yarımqrup), tələbə sayı, kontakt saatı. Birləşmiş axında mühazirə vahidi bütün
qrupları əhatə edir (`teaching_unit_groups`). Sillabusda həftəlik saat = kontakt saatı / semestrin tədris həftələri.
