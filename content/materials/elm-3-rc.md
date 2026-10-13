# Mühazirə 3. RC dövrələri və keçid prosesləri

## Əsas anlayışlar
- **Kondensator** — elektrik yükünü və elektrik sahəsinin enerjisini toplaya bilən dövrə elementidir.
- **Elektrik tutumu** — kondensatorun yük toplama qabiliyyətini xarakterizə edən kəmiyyətdir. Tutum C hərfi ilə işarə olunur və faradla (F) ölçülür.
- **Keçid prosesi** — dövrənin bir qərarlaşmış rejimdən digərinə keçdiyi müddətdə baş verən prosesdir.
- **Zaman sabiti** — RC dövrəsində keçid prosesinin sürətini xarakterizə edən kəmiyyətdir. Zaman sabiti τ hərfi ilə işarə olunur və saniyə ilə ölçülür.

## Kondensatorun dolması
Sabit gərginlik mənbəyinə rezistor vasitəsilə qoşulan kondensator dərhal deyil, tədricən dolur. Kondensatordakı gərginlik eksponensial qanunla artır.

> u_C(t) = U · (1 − e^(−t/τ))

Dolma prosesinin əvvəlində cərəyan maksimal olur və zaman keçdikcə azalır. Kondensator tam dolduqdan sonra sabit cərəyan dövrəsində ondan cərəyan keçmir.

## Zaman sabiti
RC dövrəsinin zaman sabiti müqavimətlə tutumun hasilinə bərabərdir.

> τ = R · C

Bir zaman sabiti ərzində kondensator mənbə gərginliyinin təxminən 63%-nə qədər dolur. Praktikada 5τ müddətindən sonra keçid prosesi başa çatmış hesab olunur, çünki bu zaman kondensator gərginliyin 99%-dən çoxuna qədər dolmuş olur.

## Nümunə: zaman sabitinin hesablanması
R = 10 kΩ və C = 100 µF olan dövrə üçün zaman sabiti τ = 10·10³ Ω · 100·10⁻⁶ F = 1 s olur. Deməli, kondensator təxminən 1 saniyədə gərginliyin 63%-nə, 5 saniyədə isə demək olar ki, tam dolur. Tutumu iki dəfə artırsaq, zaman sabiti də iki dəfə artar.

## Tətbiq sahələri
RC dövrələri zaman gecikməsi yaratmaq, siqnalları süzgəcdən keçirmək və gərginlik dalğalanmalarını hamarlamaq üçün istifadə olunur. Məsələn, sadə alçaq tezlik süzgəci bir rezistor və bir kondensatordan ibarətdir.
