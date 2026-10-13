# Mövzu 2. Dövrlər, funksiyalar və siyahılar

## Əsas anlayışlar
- **Dövr** — müəyyən kod hissəsinin təkrar-təkrar icra olunmasını təmin edən konstruksiyadır.
- **Funksiya** — müəyyən işi yerinə yetirən, adı olan və təkrar istifadə edilə bilən kod blokudur.
- **Siyahı** — elementləri ardıcıl saxlayan və dəyişdirilə bilən verilənlər strukturudur.
- **İndeks** — siyahıda elementin sıra nömrəsidir və Python-da sıfırdan başlayır.

## for və while dövrləri
for dövrü ardıcıllığın elementləri üzrə keçid edir. range(a, b) funksiyası a-dan başlayaraq b-yə qədər (b daxil deyil) ədədlər ardıcıllığı yaradır.

```python
cem = 0
for i in range(1, 6):
    cem += i
print(cem)  # 15
```

while dövrü şərt doğru olduğu müddətcə davam edir. Dövrün sonsuz olmaması üçün şərtə təsir edən dəyişən dövrün içində dəyişməlidir.

## Funksiyalar
Funksiya def açar sözü ilə elan olunur. Funksiya arqumentlər qəbul edə və return ilə nəticə qaytara bilər.

```python
def orta(qiymetler):
    return sum(qiymetler) / len(qiymetler)

print(orta([80, 90, 70]))  # 80.0
```

## Siyahılar
Siyahı kvadrat mötərizələrdə yazılır. len() funksiyası siyahının uzunluğunu qaytarır, mənfi indeks isə elementləri sondan saymağa imkan verir: a[-1] siyahının son elementidir. append() metodu siyahının sonuna element əlavə edir.

```python
ballar = [72, 85, 91]
ballar.append(64)
print(len(ballar), ballar[-1])  # 4 64
```

## Tipik səhvlər
range(1, 5) ifadəsinin 5-i daxil etmədiyini unutmaq ən çox rast gəlinən səhvdir. Siyahının uzunluğundan böyük indeksə müraciət IndexError xətasına səbəb olur.
