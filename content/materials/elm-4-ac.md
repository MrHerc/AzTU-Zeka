# Mühazirə 4. Sinusoidal cərəyan dövrələri

## Əsas anlayışlar
- **Sinusoidal cərəyan** — qiyməti və istiqaməti zamana görə sinus qanunu ilə dövri dəyişən elektrik cərəyanıdır.
- **Amplituda** — sinusoidal kəmiyyətin bir dövr ərzində aldığı ən böyük qiymətdir.
- **Tezlik** — bir saniyədə baş verən tam rəqslərin sayıdır. Tezlik f hərfi ilə işarə olunur və herslə (Hs) ölçülür.
- **Effektiv qiymət** — eyni müqavimətdə eyni miqdarda istilik ayıran sabit cərəyanın qiymətinə bərabər olan kəmiyyətdir.
- **Reaktiv müqavimət** — induktivlik və tutumun dəyişən cərəyana göstərdiyi, enerji itkisi yaratmayan müqavimətdir.
- **Tam müqavimət** — dəyişən cərəyan dövrəsində aktiv və reaktiv müqavimətlərin birgə təsirini ifadə edən kəmiyyətdir. Tam müqavimət Z hərfi ilə işarə olunur.

## Sinusoidal kəmiyyətlər
Sinusoidal cərəyanın ani qiyməti amplituda, bucaq tezliyi və başlanğıc faza ilə təyin olunur. Bucaq tezliyi adi tezliklə ω = 2πf düsturu ilə əlaqəlidir. Azərbaycanın elektrik şəbəkəsində tezlik 50 Hs-dir.

> i(t) = Iₘ · sin(ωt + ψ)

## Effektiv qiymət
Ölçü cihazları və şəbəkənin nominal gərginliyi effektiv qiymətlə göstərilir. Sinusoidal kəmiyyətin effektiv qiyməti amplitudanın √2-yə nisbətinə bərabərdir.

> I = Iₘ / √2 ≈ 0,707 · Iₘ

Məsələn, məişət şəbəkəsinin 220 V gərginliyi effektiv qiymətdir, onun amplitudası isə təxminən 311 V-dur.

## Reaktiv müqavimətlər
İnduktiv müqavimət tezlik və induktivlik artdıqca artır, tutum müqaviməti isə tezlik və tutum artdıqca azalır. İnduktivlikdə cərəyan gərginlikdən 90° geri qalır, kondensatorda isə gərginliyi 90° qabaqlayır.

> X_L = 2πf · L,   X_C = 1 / (2πf · C)

## Tam müqavimət və rezonans
Ardıcıl RLC dövrəsində tam müqavimət aktiv müqavimətlə reaktiv müqavimətlərin fərqinin həndəsi cəminə bərabərdir. İnduktiv və tutum müqavimətləri bərabər olduqda gərginliklər rezonansı yaranır və dövrədə cərəyan maksimal olur.

> Z = √(R² + (X_L − X_C)²)

## Nümunə: tam müqavimətin hesablanması
Müqaviməti 40 Ω olan rezistor və induktivliyi 0,1 H olan sarğac ardıcıl birləşdirilərək 220 V, 50 Hs şəbəkəyə qoşulub. İnduktiv müqavimət X_L = 2π · 50 · 0,1 ≈ 31,4 Ω olur. Tam müqavimət Z = √(40² + 31,4²) ≈ 50,9 Ω, cərəyan isə I = 220 / 50,9 ≈ 4,3 A alınır.

## Tipik səhvlər
Ən çox rast gəlinən səhv amplituda ilə effektiv qiyməti qarışdırmaqdır. İkinci tipik səhv bucaq tezliyi ω ilə adi tezlik f arasındakı fərqi unutmaqdır. Kalkulyatorda triqonometrik funksiyaları hesablayarkən dərəcə və radian rejiminə də diqqət etmək lazımdır.
