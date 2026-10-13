# Mövzu 3. Lüğətlər, sətirlər və fayllarla iş

## Əsas anlayışlar
- **Lüğət** — məlumatları açar və qiymət cütləri şəklində saxlayan dəyişdirilə bilən verilənlər strukturudur.
- **Açar** — lüğətdə qiymətə müraciət etmək üçün istifadə olunan unikal identifikatordur.
- **Sətir metodu** — sətir üzərində müəyyən əməliyyat aparan daxili funksiyadır, məsələn split() və strip().
- **Fayl** — məlumatların diskdə daimi saxlanması üçün ad verilmiş yaddaş sahəsidir.
- **Kontekst meneceri** — with operatoru ilə açılan və işi bitdikdə faylı avtomatik bağlayan konstruksiyadır.

## Lüğətlər
Lüğət fiqurlu mötərizələrdə yazılır. Qiymətə açar vasitəsilə müraciət olunur, yeni açar mənimsətmə ilə əlavə edilir. items() metodu açar-qiymət cütləri üzrə keçid etməyə imkan verir, len() isə cütlərin sayını qaytarır.

```python
telebe = {"ad": "Aysel", "qrup": "İT-25-1", "bal": 87}
telebe["bal"] = 91
telebe["kurs"] = 2
for acar, qiymet in telebe.items():
    print(acar, qiymet)
print(len(telebe))  # 4
```

Olmayan açara kvadrat mötərizə ilə müraciət KeyError xətası yaradır. Bunun qarşısını almaq üçün get() metodundan istifadə olunur: telebe.get("email", "yoxdur").

## Sətirlərlə iş
Sətirlər dəyişdirilə bilməyən ardıcıllıqlardır. strip() sətrin əvvəlindəki və sonundakı boşluqları silir, split() isə sətri sözlərə bölür. f-sətirlər dəyişənlərin qiymətini mətnin içinə yerləşdirməyə imkan verir.

```python
s = "  Azərbaycan Texniki Universiteti  "
sozler = s.strip().split()
print(len(sozler))  # 3
print(f"İlk söz: {sozler[0]}")
```

## Fayllarla iş
Fayl open() funksiyası ilə açılır. "r" rejimi oxumaq, "w" rejimi yazmaq, "a" rejimi isə faylın sonuna əlavə etmək üçündür. Azərbaycan hərfləri düzgün saxlanması üçün encoding="utf-8" parametrini göstərmək vacibdir.

```python
with open("qiymetler.txt", "w", encoding="utf-8") as f:
    f.write("Aysel 91\nMurad 78\n")
with open("qiymetler.txt", encoding="utf-8") as f:
    for setir in f:
        ad, bal = setir.split()
        print(ad, int(bal))
```

## Nümunə: sözlərin tezliyinin hesablanması
Mətndə hər sözün neçə dəfə təkrarlandığını tapmaq üçün lüğətdən istifadə olunur. Hər söz üçün get() metodu ilə cari say götürülür və bir vahid artırılır.

```python
metn = "dövr dövr funksiya siyahı dövr"
say = {}
for soz in metn.split():
    say[soz] = say.get(soz, 0) + 1
print(say)  # {'dövr': 3, 'funksiya': 1, 'siyahı': 1}
```

## Tipik səhvlər
Ən çox rast gəlinən səhvlər olmayan açara birbaşa müraciət, faylı encoding göstərmədən açmaq və "w" rejiminin faylın əvvəlki məzmununu tamamilə sildiyini unutmaqdır.
