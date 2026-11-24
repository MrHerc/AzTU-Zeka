# Çərçivə faylları (Task 24)

Bu qovluqda kənar təşkilatların dərc etdiyi çərçivələrin **dəyişdirilməmiş** faylları saxlanılır.
`python backend/manage.py import-framework --file <fayl>` onları `frameworks`, `framework_items` və
`framework_links` cədvəllərinə köçürür.

## nice-components-2.2.0.json

| Sahə | Dəyər |
|---|---|
| Ad | NICE Framework Components v2.2.0 (Workforce Framework for Cybersecurity, NIST SP 800-181 Rev. 1) |
| Mənbə | https://csrc.nist.gov/csrc/media/Projects/cprt/documents/nice/v2-2-0_nf_components.json |
| Nəşr edən | National Institute of Standards and Technology (NIST), ABŞ Ticarət Nazirliyi |
| Serverin verdiyi tarix | `Last-Modified: Mon, 18 May 2026 14:35:22 GMT`, `ETag: "0f1a58ed3e6dc1:0"` |
| Endirilib | 2026-11-23 |
| Ölçü | 2 674 252 bayt |
| SHA-256 | `3ad1d9d7e0d6b32895cb569f86c3bc05af2937a68e96eab4d1c9b3d9fa6e575e` |
| Sənəd | `SP_800_181_2_2_0`, versiya `2.2.0` |
| Elementlər | task 962, knowledge 693, skill 556, work_role 42, competency_area 11, category 5, opm_code 40, sort 47 |
| Əlaqələr | 5 950 (`projection`) |

Fayl ABŞ hökumətinin əsəridir (a work of the United States Government) və NIST tərəfindən dərc olunub;
ABŞ-da müəllif hüququ ilə qorunmur (17 U.S.C. §105). Mənbə kimi NIST göstərilir.

Faylda əlaqələr belədir (məlumatın özündən sayılıb): kateqoriya → iş rolu (42), iş rolu → tapşırıq (1 467),
bilik (2 852), bacarıq (1 091), OPM kodu (40) və sıra (41); səriştə sahəsi → bilik (241) və bacarıq (171);
kateqoriya → sıra (5). 132 tapşırıq, 53 bilik və 52 bacarıq bəyanatı heç bir iş roluna və ya səriştə sahəsinə
bağlı deyil.

## Qaydalar

- Fayl **heç vaxt redaktə olunmur**: nə formatlaşdırma, nə sətir sonu, nə tərcümə. `.gitattributes` onu
  `-text` kimi saxlayır ki, git də baytlarına toxunmasın.
- İdxalçı bu versiyanın SHA-256 dəyərini bilir (`backend/zeka/modules/syllabus/frameworks.py`, `KNOWN`) və
  dəyəri fərqlənən nüsxəni rədd edir. Naməlum versiya öz hesablanmış heşi ilə idxal olunur və `frameworks.sha256`-da qalır,
  amma **yoxlanmamış** sayılır: mənbə ünvanı yazılmır (faylın öz `website` sahəsi mənbə sayılmır), siyahıda yoxlanmış
  versiyalardan sonra gəlir, `verified: false` ilə qaytarılır və heç vaxt susmaya görə çərçivə olmur.
- Yeni versiya **yeni fayldır** (`nice-components-<versiya>.json`): köhnə versiya, onun bəndləri və nəticə
  xəritələri bazada qalır və oxunur. Yeni versiyanın heşi və mənbə ünvanı `KNOWN`-a əlavə olunur.
- Testlər üçün kiçik nümunə bu fayldan `tests/fixtures/make_nice_sample.py` ilə kəsilir; əl ilə yazılmır.

## Daxili çərçivələr

Bloom taksonomiyası (yenilənmiş, 2001) və Avropa Kvalifikasiyalar Çərçivəsinin (EQF, 2017) səviyyə
təsvirləri fayl deyil: mətnləri `backend/zeka/modules/syllabus/frameworks.py`-dadır (`BUILTIN`) və hər işə
salınmada bazaya yazılır (prod daxil). Mətn düzəldiləndə sətir öz kodu ilə yerində yenilənir: bəndin `id`-si,
təlim nəticələrinin xəritələri və təqdim olunmuş versiyaların dondurulmuş teqləri eyni bəndə bağlı qalır və yeni
mətni göstərir. Kod bəndin açarıdır, dəyişdirilmir.

| Çərçivə | Mənbə | Yoxlanılıb |
|---|---|---|
| EQF, 8 səviyyə × bilik, bacarıq, məsuliyyət və müstəqillik | Şuranın 22 may 2017-ci il tövsiyəsi, II əlavə (2017/C 189/03; OJ C 189, 15.6.2017, s. 15); CELEX `32017H0615(01)`; https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32017H0615(01) | 2026-11-24, EUR-Lex-in HTML mətni ilə söz-söz; 24 təsvirin hamısı eynidir |
| Bloom, 6 səviyyə | L. W. Anderson, D. R. Krathwohl (red.), *A Taxonomy for Learning, Teaching, and Assessing: A Revision of Bloom's Taxonomy of Educational Objectives*, Longman, 2001, s. 67–68 | 2026-11-24, kitabdan sitat gətirən nəşrlər üzrə; adlar: Remember, Understand, Apply, Analyze, Evaluate, Create |

- **EQF, ingiliscə** rəsmi mətndir. EUR-Lex xananı kiçik hərflə başlayır ("The learning outcomes relevant to Level n
  are …" cümləsinin davamıdır) və iki bəyanatlı xananı iki abzas yazır. Təsvir ayrıca göstəriləndə böyük hərflə
  başlayır, iki abzas "; " ilə birləşir; Europass-ın "Description of the eight EQF levels" səhifəsi də belə göstərir.
  Söz dəyişmir. `tests/unit/test_framework_texts.py` II əlavənin mətnini saxlayır və kataloqu onunla müqayisə edir.
- **EQF, azərbaycanca** işçi tərcümədir. Azərbaycanın rəsmi sənədi — "Azərbaycan Respublikasının ömürboyu təhsil
  üzrə Milli Kvalifikasiyalar Çərçivəsi" (AzMKÇ, Nazirlər Kabinetinin 18 iyul 2018-ci il tarixli 311 nömrəli qərarı,
  https://e-qanun.az/framework/39622) — 8 səviyyəlidir, amma təsvirləri öz mətnidir ("Bilik və anlama",
  "Bacarıqlar", "Müstəqillik və məsuliyyət"), EQF təsvirlərinin tərcüməsi deyil; 4.6-cı bənd yalnız AKÇ-yə
  uyğunluğun nəzərə alındığını deyir. Ona görə AzMKÇ-nin mətni EQF bəndlərinə yazılmır. AzMKÇ ayrıca daxili
  çərçivə kimi əlavə oluna bilər.
- **EQF, rusca** işçi tərcümədir: rus dili Aİ-nin rəsmi dili deyil, EUR-Lex və Cedefop rusca mətn dərc etmir.
  ETF-in saytında tövsiyənin rusca tərcüməsi var (`openspace.etf.europa.eu/system/files/2019-08/EQF_recommendations_RU.pdf`),
  amma Rəsmi Jurnalın mətni deyil və 2026-11-24-də açılmadı.
- **Bloom, ingiliscə** müəlliflərin tərifləridir, Böyük Britaniya yazılışı ilə (`i18n/BRIEF.md`: Analyse,
  judgements, reorganise). Azərbaycanca və rusca mətnlər işçi tərcümədir.
