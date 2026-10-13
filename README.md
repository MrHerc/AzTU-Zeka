# AzTU Rəqəmsal Kampus — Zəka platforması (demo v0.3)

by **Safarov Industries**. Lokal demo: AI tutor, kampus köməkçisi, Test studiyası, 13 e-xidmət (QR doğrulamalı sənədlər),
davamiyyət və qiymətlər, xəbərlər və tədbirlər, müəllimlər üçün AI Akademiya, dəstək xidməti və rəylər, AzTU-nun real nailiyyətləri
və rəhbərlik paneli. Xarici paket tələb etmir — yalnız Python 3.10+ (stdlib) və müasir brauzer.

## İşə salmaq
```
start_demo.bat                 # server + brauzer
python run.py --port 5070      # və ya terminaldan
python run.py --reset          # demo məlumatlarını sıfırdan yarat
python run.py --public-url https://zeka.example.az   # serverdə: sənəd QR kodları bu ünvana yönəlir, sessiya kukisi Secure olur
```
Ünvan: http://127.0.0.1:5070 (server yalnız bu kompüterdə dinləyir; serverdə onu HTTPS və parol verən reverse proxy arxasında işlədin). Fonda: `scripts\start_demo.ps1`, dayandırmaq: `scripts\stop_demo.ps1`.
Verilənlər bazası sxemi dəyişdikdə köhnə demo bazası avtomatik yenidən yaradılır.

## v0.3-də yeni
- **Üç dil** — Azərbaycan, ingilis, rus (yuxarı paneldəki dil düyməsi; seçim profildə saxlanılır). Server cavabları, xəta mesajları,
  bildirişlər, e-xidmət formaları və AI tutorun cavab mətni seçilmiş dildədir. Fənn materialları və sitatlar tədris dilində qalır.
- **İnteraktiv bələdçi** — hər səhifədə “Səhifə bələdçisi” düyməsi; Bələdçi mərkəzində bütün bələdçilər və irəliləyiş; ilk girişdə tanışlıq turu.
- **Dəstək və rəy** — dəstək sorğuları (kateqoriya, prioritet, icra müddəti, yazışma, daxili qeydlər, qiymətləndirmə), hər səhifədə rəy düyməsi,
  rəhbərlik üçün məmnuniyyət paneli (orta qiymət, NPS, bölmələr, şərhlər, CSV).
- **AzTU-nun nailiyyətləri** — 18 real fakt, hər biri aztu.edu.az və ya edu.gov.az mənbəsinə keçidlə (`content/achievements.json`).
- **Tövsiyə olunan mənbələr** — fənn səhifələrində, mühazirə baxışında və AI Akademiya modullarında açıq dərsliklər (OpenStax, MIT OCW),
  rəsmi sənədləşmə və beynəlxalq rəhbər sənədlər (UNESCO, Avropa Komissiyası, QAA). Hər keçid açılıb yoxlanılıb; adlar mənbənin
  dilində verilir və tərcümə olunmur (`content/references.json`, yoxlama tarixi faylın `checked` sahəsində).
- **Əlaqə** — universitetin rəsmi ünvanı, telefonu, e-poçtu, xəritə keçidləri, rəsmi sistemlər və sosial şəbəkələr (`content/contacts.json`).
- **Portal daxilində sənəd baxışı** — sənəd, sillabus və əlavələr modal pəncərədə açılır (çap/PDF, yükləmə, yeni pəncərə); PDF üçün mətn önizləməsi.
- **Hamar keçidlər və animasiyalar**, skelet yükləmə, sayğaclar, qrafik animasiyaları (`prefers-reduced-motion` nəzərə alınır).
- **Mobil versiya** — alt naviqasiya zolağı, açılan menyu, alt pəncərə kimi dialoqlar; **yığılan sol panel** (düymə və ya `[`).

## Demo ssenarisi (≈12 dəq)
1. **Tələbə** → razılıq → tanışlıq turu → AI tutor (İzah, Sokratik, Məşq; [1] mənbəyə klik) → dili EN/RU-ya dəyişin.
2. **Tələbə** → E-xidmətlər → arayış sifarişi → Müraciətlərim; Davamiyyət → qayıbı həkim arayışı ilə üzrlü edin.
3. **Dekanlıq** → müraciəti təsdiqləyin → sənədə portal daxilində baxın → verin; Dəstək sorğuları → cavab, status.
4. **Müəllim** → material yükləyin → Test studiyası → AI ilə sual → təsdiq → test dərc edin; AI Akademiya → sertifikat.
5. **Rəhbərlik** → pilot göstəriciləri, rəylər və məmnuniyyət paneli; hər kəs üçün: Nailiyyətlər və Əlaqə.

Rollar arasında profil menyusundan keçmək olar.

## Tərcümə (i18n)
Mənbə dil Azərbaycan dilidir: mətn özü açardır. JS-də `t("… {x} …", { x })`, Python-da `S/T3/E/S_` (app/i18n.py).
```
python tools/i18n.py lint           # t()-siz qalan mətnləri tapır
python tools/i18n.py extract        # i18n/source/* və tərcümə olunmamış hissələr: i18n/todo/*.json
python tools/i18n.py build          # i18n/en|ru/*.json -> static/locales/*.json + app/locales/*.json
```
Tərcümə qaydaları və terminologiya: `i18n/BRIEF.md`.

## AI mühərriki
Susmaya görə **oflayn demo mühərrik**: Azərbaycan dilinə uyğun axtarış (BM25 + kök ayırma), hər cavabda mənbə, Sokratik rejimdə hazır cavab yoxdur;
ingilis/rus dilində verilən kampus sualları Azərbaycan dilindəki qaydalarla əlaqələndirilir. Real LLM üçün `config.example.json` → `config.json`
(OpenAI-uyğun API, Azure OpenAI və ya Anthropic); LLM əlçatan olmasa, demo mühərrikə avtomatik qayıdır.

## Yoxlama
`python tests\selftest.py` (backend + API, o cümlədən dil, dəstək, rəy, nailiyyətlər, tövsiyə olunan mənbələr) — bazanı sıfırlayır, sonra serveri yenidən başladın.
İnkişaf alətləri `.dev/tools/`: `jscheck.ps1`, `imports.py`, `dom.py` (bütün səhifələr, 3 dil, mobil), `shot.py`, `m390.py`.

## Məhdudiyyətlər (demo)
Parolsuz demo girişi (SSO pilotda), demo məlumatları sintetikdir (nailiyyətlər və əlaqə məlumatları istisna — onlar realdır),
sənədlərdə “DEMO” nişanı var və hüquqi qüvvəsi yoxdur.
