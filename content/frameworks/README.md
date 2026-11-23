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
  dəyəri fərqlənən nüsxəni rədd edir. Naməlum versiya öz hesablanmış heşi ilə idxal olunur və `frameworks.sha256`-da qalır.
- Yeni versiya **yeni fayldır** (`nice-components-<versiya>.json`): köhnə versiya, onun bəndləri və nəticə
  xəritələri bazada qalır və oxunur. Yeni versiyanın heşi və mənbə ünvanı `KNOWN`-a əlavə olunur.
- Testlər üçün kiçik nümunə bu fayldan `tests/fixtures/make_nice_sample.py` ilə kəsilir; əl ilə yazılmır.

## Daxili çərçivələr

Bloom taksonomiyası (yenilənmiş, 2001) və Avropa Kvalifikasiyalar Çərçivəsinin (EQF, 2017) səviyyə
təsvirləri fayl deyil: mətnləri `backend/zeka/modules/syllabus/frameworks.py`-dadır (`BUILTIN`) və hər işə
salınmada bazaya yazılır (prod daxil). Azərbaycanca və rusca mətnlər işçi tərcümədir; EQF-in rəsmi mətni
ingiliscədir (Şuranın 22 may 2017-ci il tövsiyəsi, 2017/C 189/03, II əlavə).
