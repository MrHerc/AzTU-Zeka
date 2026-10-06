# Mövzu 1. Dəyişənlər, verilənlər tipləri və şərt operatoru

## Əsas anlayışlar
- **Dəyişən** — proqramda məlumatı saxlamaq üçün ad verilmiş yaddaş sahəsidir.
- **Verilənlər tipi** — dəyişənin hansı növ məlumat saxladığını və onun üzərində hansı əməliyyatların aparıla biləcəyini müəyyən edir.
- **Mənimsətmə operatoru** — dəyişənə qiymət verən = işarəsidir.
- **Şərt operatoru** — şərtin doğru və ya yanlış olmasından asılı olaraq müxtəlif kod hissələrini icra edən konstruksiyadır.
- **Məntiqi ifadə** — nəticəsi True (doğru) və ya False (yanlış) olan ifadədir.

## Dəyişənlər və tiplər
Python-da dəyişən yaratmaq üçün ona sadəcə qiymət mənimsədilir. Tip avtomatik müəyyən olunur. Əsas tiplər bunlardır: int (tam ədəd), float (kəsr ədəd), str (sətir) və bool (məntiqi qiymət).

```python
yas = 19
orta_bal = 87.5
ad = "Aysel"
telebedir = True
print(type(orta_bal))
```

Dəyişən adları hərf və ya alt xətt ilə başlamalıdır. Python böyük və kiçik hərfləri fərqləndirir: ad və Ad iki fərqli dəyişəndir.

## Şərt operatoru
Şərt operatoru if, elif və else açar sözləri ilə yazılır. Python-da kod blokları girinti (adətən 4 boşluq) ilə ayrılır.

```python
bal = 76
if bal >= 91:
    print("Əla")
elif bal >= 51:
    print("Keçdi")
else:
    print("Kəsr")
```

Müqayisə üçün ==, !=, <, >, <= və >= operatorlarından, şərtləri birləşdirmək üçün isə and, or və not operatorlarından istifadə olunur.

## Tipik səhvlər
Ən çox rast gəlinən səhvlər girintinin pozulması və müqayisə üçün == əvəzinə = yazılmasıdır. Həmçinin input() funksiyası həmişə sətir qaytarır, ona görə ədədlə işləmək üçün nəticəni int() və ya float() ilə çevirmək lazımdır.
