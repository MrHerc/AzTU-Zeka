# Zəka Radar — 3 dəqiqəlik demo

**Zəka Radar** universitetin artıq topladığı məlumatlardan (davamiyyət, cari ballar, testlər, AI tutorla iş) dərsdən
yayınan və geri qalan tələbəni **həftələr əvvəl** tapır, riskin **səbəbini izah edir** və müəllimə bir kliklə
**mühazirəyə istinad edən dəstək planı** hazırlamağa imkan verir. Tələbə risk balını yox, yalnız dəstək addımlarını görür.
Addımlar onun tutordakı real fəaliyyətindən avtomatik qeyd olunur, rəhbərlik isə planların nəticəsini ölçür.

Niyə bu funksiya: tələbə itkisi universitet üçün həm maliyyə, həm də reputasiya itkisidir. Mövcud həllər adətən
qara qutu bal göstərir. Zəka hər balı sübutla izah edir, qərarı insana saxlayır və müdaxiləni elə həmin platformada
(AI tutor, materiallar, e-xidmətlər) icra edir. Bu, demoda üç dəqiqədə görünən tam dövrədir: **aşkarla → izah et → kömək et → ölç**.

---

## 1. İşə salmaq (bir əmr)

İnternet və əlavə paket lazım deyil. Hər başlanğıcda demo məlumatları bugünkü tarixə görə sıfırdan yaradılır.

| Mühit | Əmr | Sonra açın |
|---|---|---|
| Docker | `docker compose up --build` | http://localhost:5070/?demo=1 |
| macOS / Linux (Python 3.10+) | `./demo.sh` | brauzer özü açılır |
| Windows (Python 3.10+) | `demo.bat` (iki dəfə klikləyin) | brauzer özü açılır |
| İstənilən OS, əl ilə | `python run.py --reset --port 5070` | http://127.0.0.1:5070/?demo=1 |

- Başqa port: `PORT=8080 ./demo.sh` və ya `docker-compose.yml`-də `"8080:5070"`.
- Dayandırmaq: `Ctrl+C` (Docker-də `docker compose down`).
- `?demo=1` ünvanı təqdimat panelini avtomatik başladır; ingiliscə təqdimat üçün `?lang=en&demo=1`, rusca üçün `?lang=ru&demo=1`. Giriş səhifəsində **“3 dəqiqəlik demo ssenarisi”** düyməsi
  və profil menyusunda eyni adlı bənd də var.

## 2. Təqdimat paneli necə işləyir

Sol aşağı küncdə (mobil ekranda aşağıda) panel açılır. Hər addımda: rol, ekran, **nə deyəcəyiniz** və **nəyə
klikləyəcəyiniz**. **“Növbəti”** düyməsi lazım olan rola keçir, səhifəni açır və göstəriləcək hissəni vurğulayır.
Taymer keçən vaxtı göstərir. Panel dil seçiminə uyğun azərbaycan, ingilis və ya rus dilindədir.

## 3. Ssenari (≈ 2:45)

| # | Rol | Ekran | Deyin | Edin | Vaxt |
|---|---|---|---|---|---|
| 1 | Rəhbərlik | Pilot paneli → **Zəka Radar** kartı | Universitet tələbəni adətən imtahandan sonra itirir. Zəka mövcud məlumatları birləşdirib riski həftələr əvvəl göstərir. | Kartdakı rəqəmləri göstərin: yüksək risk, diqqət siyahısı, planlardan sonra riski azalanlar (2/2, orta −27 bal). | 0:20 |
| 2 | Müəllim (Dos. Rauf Əliyev) | **Zəka Radar** | 120 tələbə risk balına görə sıralanır. Rəngli zolaq balın səbəbləri, “Niyə?” sütunu faktlardır. | Siyahının başındakı **Murad Hüseynovu** göstərin. | 0:20 |
| 3 | Müəllim | Murad-ın profili | Son 4 dərsə gəlməyib, test 67% → 25%, Kirxhof qanunu üzrə dəfələrlə sual verib. Söhbətlərin mətni göstərilmir — yalnız mövzu və say. | “Riskin dinamikası” qrafiki: bir həftə əvvəl hər şey normal görünürdü. | 0:25 |
| 4 | Müəllim | Dəstək planı pəncərəsi | AI planı müəllimin öz mühazirələrindən qurur: mövzunu təkrar, məşq, dərsə qayıdış, konsultasiya. Qərarı insan verir. | Mənbə işarəsinə klikləyib mühazirə hissəsini göstərin, sonra **“Tələbəyə göndər”**. Panel özü növbəti addıma keçir. | 0:30 |
| 5 | Tələbə (Murad) | **Dəstək planım** | Murad risk balını görmür — müəlliminin addımlarını görür; hər addım mühazirəyə istinad edir. | “Növbəti”. | 0:15 |
| 6 | Tələbə | AI tutor (İzah rejimi) | Tutor cavabı mühazirəyə istinadla verir; bu fəaliyyət planda avtomatik qeyd olunur. | Cavabdakı **[1]** işarəsinə klikləyin, sağda mənbə açılır. | 0:20 |
| 7 | Tələbə | Dəstək planım | Birinci addım özü tamamlandı — müəllim heç nəyi əl ilə yoxlamır. | İstəsəniz “Məşqə başla” → cavab **B** (yükün saxlanması) → ikinci addım da qeyd olunur. | 0:15 |
| 8 | Rəhbərlik | Zəka Radar (bütün fənlər) → **Planların təsiri** | Rəhbərlik bütün fənlər üzrə riski, planları və nəticəni görür. Təklif: bir fakültədə bir semestrlik pilot. | Murad-ın yeni planı “Ölçülür” kimi görünür (nəticə 7 gündən sonra ölçülür). **“Bitir”.** | 0:20 |

**Əlavə (sual gələrsə, 30 san.):** “Model necə işləyir” kartı — çəkilər (davamiyyət 30, qiymətləndirmə 30, anlayış
boşluğu 25, aktivlik 15), hədlər (yüksək ≥ 50, diqqət ≥ 30) və prinsiplər. **Lalə Kərimova**nın profilində 4 üzrlü
qayıb var, amma riski 0-dır: üzrlü qayıblar heç vaxt sayılmır.

## 4. Demo hekayələri (sintetik məlumat)

| Tələbə | Səviyyə | Hekayə |
|---|---|---|
| Murad Hüseynov | Yüksək | Son 4 dərsə gəlməyib (daha 2 fəndə də qayıb), testlər düşür, Kirxhof qanunu üzrə boşluq. |
| Elnur Səfərov | Diqqət | Bütün dərslərdədir, tutordan çox soruşur, amma testlərdən kəsilir (dəyişən cərəyan). |
| Nərmin Abbasova | Diqqət | Semestrin əvvəlində fəal idi, həftələrdir tutora yazmır, test cəhdi yoxdur. |
| Fidan Musayeva | Plan açıqdır | 2 həftə əvvəl plan göndərilib; 4 addımdan 3-ü real fəaliyyətdən qeyd olunub; risk 49 → 17. |
| Kamran Babayev | Plan tamamlanıb | Semestrin əvvəlində plan, indi normal həddə; risk 34 → 12. |
| Lalə Kərimova | Normal | 4 qayıb həkim arayışı ilə üzrlüdür — riskə təsir etmir. |

Qalan 114 tələbə təsadüfi, lakin realist paylanma ilə yaradılır (bütün fənlər üzrə ≈ 6 yüksək risk, ≈ 30 diqqət).

## 5. Təkrar demo və problemlərin həlli

- **Təkrar göstərmək:** serveri yenidən başladın (`./demo.sh`, `demo.bat` və Docker hər dəfə sıfırlayır) və ya
  `python run.py --reset`. Admin rolunda “Demo məlumatlarını sıfırla” düyməsi də var.
- **Panel “Demo hekayəsi tapılmadı” deyir:** baza köhnədir — yuxarıdakı sıfırlamanı edin.
- **Murad üçün plan pəncərəsi açılmır:** plan artıq göndərilib (demo ikinci dəfə keçirilir) — sıfırlayın.
- **Port məşğuldur:** `PORT=5080 ./demo.sh` və ya `python run.py --reset --port 5080`.
- **Brauzer köhnə versiyanı göstərir:** səhifəni `Ctrl+Shift+R` ilə yeniləyin.
- Panel yalnız brauzer sessiyasında saxlanılır; bağlamaq üçün paneldəki ✕.

## 6. Dürüstlük qeydləri

- Bütün tələbə məlumatları sintetikdir; ekranda “Pilot · sintetik məlumat” nişanı var.
- Model şəffaf qayda əsaslı baldır, öyrədilmiş qara qutu deyil. Çəkilər və hədlər pilotda real məlumatla
  kalibrlənməlidir (məsələn, əvvəlki semestrlərdə akademik borcla nəticələnən halların proqnozlaşdırılması ilə).
- “Planların təsiri” bu demoda iki planın sintetik nəticəsidir; real effekt nəzarət qrupu ilə ölçülməlidir.
- AI mühərriki oflayn işləyir. `config.json` və ya `AZTU_LLM_*` mühit dəyişənləri ilə real LLM qoşulsa, tutor
  cavabları LLM-dən gəlir; Radar balı LLM-dən asılı deyil.

## 7. Texniki xülasə

| Hissə | Fayl |
|---|---|
| Risk modeli, izah, plan, avtomatik irəliləyiş, təsir | `app/radar.py` |
| API | `app/r_radar.py`: `GET /api/radar`, `GET /api/radar/student/{id}`, `POST /api/radar/student/{id}/plan` (`preview: true` ilə önizləmə), `POST /api/interventions/{id}/status`, `GET /api/student/plans`, `POST /api/student/plans/{id}/steps` |
| Demo hekayələri | `app/radar_seed.py` |
| UI | `static/js/radar.js`, `static/css/m-radar.css` |
| Təqdimat paneli | `static/js/demo.js` |
| Testlər | `python tests/selftest.py` (26 Radar yoxlaması daxil olmaqla) |

Rollar: müəllim yalnız öz fənlərini görür; dekanlıq və rəhbərlik hamısını; rəhbərlik yalnız oxuyur. Tələbə
`/api/radar`-a giriş ala bilmir və öz planında risk balını görmür. Plan göndərilməsi audit jurnalına yazılır.

---

## English quick start

1. Run one of: `docker compose up --build` · `./demo.sh` (macOS/Linux) · `demo.bat` (Windows) · `python run.py --reset --port 5070`.
2. Open http://localhost:5070/?lang=en&demo=1 to present in English (`?lang=ru&demo=1` for Russian). The scripts open the Azerbaijani version, http://localhost:5070/?demo=1.
3. Follow the presenter panel (bottom-left). **Next** switches role, opens the right screen and highlights what to show; the panel tells you what to say.
4. The 8 steps take about 2:45: leadership sees risk → teacher sees who and why → one-click support plan grounded in the
   teacher's lectures → the student sees support (never a score) → tutor activity ticks plan steps automatically → leadership sees measured impact.
5. To run it again, restart (all launchers reset the demo data) or run `python run.py --reset`.

Requirements: Python 3.10+ (standard library only) or Docker. No internet connection or API keys are needed.
