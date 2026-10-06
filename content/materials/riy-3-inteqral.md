# Mühazirə 3. Qeyri-müəyyən və müəyyən inteqral

## Əsas anlayışlar
- **İbtidai funksiya** — törəməsi verilmiş funksiyaya bərabər olan funksiyadır.
- **Qeyri-müəyyən inteqral** — verilmiş funksiyanın bütün ibtidai funksiyalarının çoxluğudur.
- **İnteqrallama sabiti** — ibtidai funksiyaların bir-birindən fərqləndiyi ixtiyari sabit ədəddir və C hərfi ilə işarə olunur.
- **Müəyyən inteqral** — funksiyanın verilmiş parça üzrə inteqral cəmlərinin limitidir və əyrixətli trapesiyanın sahəsini ifadə edir.

## Əsas inteqrallar cədvəli
Qüvvət funksiyasının inteqralı aşağıdakı düsturla tapılır. Bu düstur n = −1 halında tətbiq olunmur.

> ∫ xⁿ dx = xⁿ⁺¹ / (n + 1) + C

Digər əsas inteqrallar: ∫ 1/x dx = ln|x| + C, ∫ eˣ dx = eˣ + C, ∫ sin x dx = −cos x + C və ∫ cos x dx = sin x + C. Cəmin inteqralı inteqralların cəminə bərabərdir, sabit vuruğu isə inteqral işarəsi xaricinə çıxarmaq olar.

## Nyuton–Leybnis düsturu
Müəyyən inteqral ibtidai funksiyanın parçanın son nöqtələrindəki qiymətlərinin fərqinə bərabərdir. Bu düstur törəmə ilə inteqral arasındakı əlaqəni ifadə edir.

> ∫ₐᵇ f(x) dx = F(b) − F(a)

## Müəyyən inteqralın həndəsi mənası
Funksiya parçada mənfi deyilsə, müəyyən inteqral qrafik, absis oxu və x = a, x = b düz xətləri ilə hüdudlanmış fiqurun sahəsinə bərabərdir. Absis oxundan aşağıda yerləşən hissələrin sahəsi inteqrala mənfi işarə ilə daxil olur.

## Nümunə: müəyyən inteqralın hesablanması
∫₀² (3x² + 2x) dx inteqralını hesablayaq. İbtidai funksiya F(x) = x³ + x² olur. Nyuton–Leybnis düsturuna görə F(2) − F(0) = (8 + 4) − 0 = 12 alınır.

## Mühəndislikdə tətbiqlər
Müəyyən inteqral vasitəsilə sahələr, həcmlər, dəyişən qüvvənin gördüyü iş və sürət məlum olduqda gedilən yol hesablanır. Məsələn, sürət v(t) funksiyası ilə verilərsə, t₁ və t₂ anları arasında gedilən yol v(t)-nin bu parça üzrə inteqralına bərabərdir.

## Tipik səhvlər
Ən çox rast gəlinən səhvlər qeyri-müəyyən inteqralda C sabitini yazmamaq, qüvvət düsturunu n = −1 halında tətbiq etmək və absis oxundan aşağıdakı sahələrin işarəsini nəzərə almamaqdır.
