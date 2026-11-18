# Checkpoint B baxışı (2026-11-18)

Faza 2 diff-i (`5609033..f425638`, Tapşırıq 10–17) yeddi rəyçi ilə yoxlandı: `ecc:code-reviewer`, `ecc:security-reviewer`,
`ecc:silent-failure-hunter`, `agent-skills:code-reviewer`, `agent-skills:security-auditor`, `agent-skills:test-engineer`,
`ecc:python-reviewer`. Dublikatlar birləşdirildi, tapıntılar altı qrupa bölündü (A–E və T, cəmi 47 iddia). Hər qrupu ayrıca
agent təkzib etməyə çalışdı. O, iddianı HEAD-in nüsxəsində işə salıb yoxladı. Yalnız təsdiqlənən hissələr düzəldildi.

Hər düzəliş üçün köhnə kodda yıxılan reqressiya testi var: `tests/integration/test_checkpoint_b.py`. Köhnə kodda (f425638)
bu faylın 28 testi yıxılır, 2-si xəta verir. Keçən testlər test boşluqlarıdır (A4, A6, C6, D9, T2, T4, T5, T6): mövcud
davranışı ilk dəfə yoxlayırlar.

## A. Aktivləşdirmə kodları və idxal

- **A1** (orta; işçi rolu olan tələbə üçün yüksək) — Təsdiqləndi. Kod parolu olan hesabı da açırdı, müvəqqəti parol koddan
  sonra verilsə belə. TOTP və SSO ilə bağlanmış tələbəyə də kod verilirdi. Aktivləşdirmədən sonra sessiya `full` olurdu.
  Düzəliş: `importer.activate` parol, TOTP və SSO olmayan hesabı tələb edir; `repo.faculty_students` belə hesabları buraxmır;
  sessiyanın əhatəsi `identity.service.scope_after_password`-dan gəlir.
- **A2** (orta) — Rol hissəsi təsdiqləndi, status hissəsi təkzib olundu (`before()` aktiv olmayan hesabı onsuz da rədd edir).
  İdxal rolu dəyişəndə köhnə sessiya yaşayırdı və tələbə müəllim kimi işləyirdi. Düzəliş: rolu və ya statusu dəyişən
  `users` sətri üçün `identity.end_all_sessions`.
- **A3** (aşağı) — Təsdiqləndi. CSV xanası `=HYPERLINK(...)` kimi düstur ola bilirdi. Düzəliş: `integration.domain.csv_cell`
  `= + - @ \t \r` ilə başlayan xanaya `'` qoyur; ekran və `manage.py` eyni köməkçini işlədir.
- **A4** — Qüsur kimi təkzib olundu, test boşluğu təsdiqləndi. Test əlavə edildi: kod verildikdən sonra deaktiv edilən hesab
  401 alır.
- **A5** — İstifadəçi idxalı üçün təkzib olundu. Yoxlama zamanı B1 (500) tapıldı.
- **A6** — Qüsur kimi təkzib olundu, test boşluğu təsdiqləndi. Test əlavə edildi: ilk idxal Zəka-dakı dolu dəyərin üstünə
  yazmır, konflikt verir.

## B. İdxalın dayanıqlığı

- **B1** (yüksək) — Təsdiqləndi. Bir kursun mühazirəsində və laboratoriyasında olan tələbə (adi OneRoster halı) 500 verirdi
  (`enrollments` PK). Düzəliş: faylda eyni (tələbə, kurs) bir qeydiyyat olur, hər iki mənbə sətri ona bağlanır.
- **B2** (orta) — Təsdiqləndi. 790 baytlıq XLSX 345 MB yaddaş tuturdu. Düzəliş: `tables.MAX_CELLS` doldurmadan əvvəl
  yoxlanır, vərəq sayı 200-dür, eyni vərəq iki dəfə oxunmur.
- **B3** (aşağı–orta) — Təsdiqləndi. Pozulmuş XML, şifrəli və ya naməlum sıxılma 500 verirdi. Düzəliş: `tables.BROKEN` hamısını
  tutur və 400 qaytarır.
- **B4** (aşağı) — Təsdiqləndi. Forma №3-də `inf`, `1e30`, `nan` 500 verirdi və ya bazaya düşürdü. Düzəliş: `forma3._number`
  yalnız sonlu və 10 000-dən kiçik ədədi qəbul edir, qalanı səbəbi ilə hesabata yazır.
- **B5** (orta) — Əsasən təsdiqləndi. Oxunmayan saat, semestri tapılmayan sütun, fənn sütunu olmayan başlıq və qrupsuz sətir
  səssizcə atılırdı. Düzəliş: hər biri səbəbi ilə konflikt kimi göstərilir; heç bir sətir verməyən Forma №3 rədd edilir; hər
  başlıq öz sətirlərini növbəti başlığa qədər oxuyur; təkrarlanan vahid barədə xəbərdarlıq var. Təkzib olunan hissə: sətirlər
  dedup-dan sonra sayılır.
- **B6** (aşağı) — Təsdiqləndi. Boş sətirlər nömrələmədən əvvəl atılırdı, xəta səhv sətir nömrəsini göstərirdi. Düzəliş: sətir
  fayldakı nömrəsini saxlayır. Bir neçə dolu vərəqli XLSX CSV növləri üçün rədd edilir.
- **B7** (aşağı) — Əsasən təsdiqləndi. Düzəliş: `manage.py import` `sqlite3.Error`-u kod 2 ilə bitirir; `activation-codes`
  miqrasiya xətasını tutur və CSV-ni `O_CREAT|O_EXCL, 0600` ilə yaradır. Konfliktlərdə kod 0 qalır (sənədləşdirilmiş dizayn).
- **B8** (orta–aşağı) — Təsdiqləndi. Yoxlama ilə yazma arasında Zəka-da edilən dəyişiklik üstündən yazılırdı. Düzəliş: kilid
  altında toxunulan sətirlər yenidən oxunur, dəyişmiş sətir konflikt olur; `IntegrityError` tərcümə olunmuş 400-dür.
- **B9** (aşağı) — Bildiriş hissəsi təsdiqləndi. Düzəliş: `admin-import.js` uğur bildirişini `r.written`-ə görə göstərir.
- **B10** (aşağı) — Qismən. "SEMINAR", "MÜHAZIRƏ", "FƏNNIN ADI" uyğun gəlmirdi. Düzəliş: müqayisə `key(v) = norm(v).replace("ı", "i")`
  ilə aparılır.

## C. Dekanlığın əhatəsi

- **C1** (yüksək) — Təsdiqləndi. Dekanlıq başqa fakültənin sənədini ləğv edə bilirdi. Düzəliş: `revoke` sahibini `serves()` ilə yoxlayır.
- **C2** (orta) — Təsdiqləndi. `academic_office`, `dept_head`, `proctor` (və müəllim) istənilən müraciəti oxuyub yaza bilirdi.
  Düzəliş: `_req_for` yalnız tələbəni və `STAFF` rollarını buraxır.
- **C3** (orta) — Təsdiqləndi. Sənəd siyahısında `LIMIT 200` əhatədən əvvəl tətbiq olunurdu. Düzəliş: `scope_sql()` SQL-də, LIMIT-dən əvvəl.
- **C4** (aşağı) — Təsdiqləndi. Nişan sayı bütün universiteti sayırdı. Düzəliş: say siyahı ilə eyni əhatədədir, yalnız `STAFF` üçün.
- **C5** (aşağı, performans) — Təsdiqləndi. `serves()` hər dəfə fakültənin bütün tələbələrini oxuyurdu. Düzəliş: bir `EXISTS`
  sorğusu; miqrasiya `0171` `users(group_id)` indeksini əlavə edir.
- **C6** — Test boşluğu təsdiqləndi (`office_for` özü düzgündür). Test əlavə edildi: başqa fakültənin dekanlığına bildiriş getmir,
  `office/summary` əhatəlidir.
- **C7** (aşağı–orta) — Qismən. Mesaj, əməliyyat və önizləmə oxu kimi audit olunmurdu. Düzəliş: `audit_read="request"` və
  `audit_read="document"`. Təkzib olunan hissə: `settings_change` yalnız bölmənin adını yazır (dizayn).
- **C8** (aşağı) — Qismən. Hesab deaktiv ediləndən sonra birdəfəlik açar hələ işləyirdi. Düzəliş: `_key_user` `status='active'`
  tələb edir. `must_change` və əhatə hissələri təkzib olundu.
- **C9** (aşağı) — Təsdiqləndi. İkinci addımı gözləyən sessiya `/verify`, girişi və aktivləşdirməni bağlayırdı. Düzəliş: `auth=False`
  marşrutlarında yarımçıq sessiya `req.user=None` olur.

## D. Giriş, sessiyalar, SSO

- **D1** (orta) — Giriş üçün təsdiqləndi, aktivləşdirmə üçün təkzib olundu (kod yalnız SHA-256 tələb edir). Bir ünvan müxtəlif
  adlarla scrypt-i doldururdu və parol yaya bilirdi. Düzəliş: `LIMITS["password_fail"]` (15 dəqiqədə ünvan başına 100 səhv)
  scrypt-dən əvvəl yoxlanır. Kampus NAT-ı üçün limit geniş saxlanılıb.
- **D2** (aşağı) — Təsdiqləndi. Düzəliş: `LIMITS["sso"]` (dəqiqədə 30) başlanğıc və bağlama üçün; uğursuz discovery 30 s yadda
  saxlanır; `sso_pending(created_at)` indeksi.
- **D3** — Təkzib olundu. Endpoint-ləri yalnız administratorun təyin etdiyi issuer verir.
- **D4** (aşağı) — Qismən. Mövcud və mövcud olmayan ad kilid zamanı fərqli cavab verirdi. Düzəliş: naməlum ad üçün də
  `login_blocks(account, '*')` sayğacı.
- **D5** (praktik təsiri yoxdur) — Kodda təsdiqləndi. Düzəliş: `_number` `math.isfinite` tələb edir.
- **D6** — Təkzib olundu (ASCII olmayan rəqəm 400 olur, cəhd sayılmır).
- **D7** (aşağı) — Təsdiqləndi. SQLite tam ədədindən böyük id 500 verirdi. Düzəliş: `Router.match` `MAX_ID`-dən böyük və
  19 rəqəmdən uzun id üçün 404 (4300+ rəqəmdə `int()` özü `ValueError` verir; bunu təhlükəsizlik yoxlaması tapdı).
- **D8** (aşağı) — Python 3.11+ üçün təsdiqləndi. Həftə tarixi (`2026-W01-1`) qəbul olunurdu. Düzəliş: `DATE` regex-i
  `date_problem`-də və `tenant._iso`-da.
- **D9** (aşağı) — Qismən. userinfo e-poçtsuz `email_verified: true` göndərəndə ID token-in təsdiqlənməmiş ünvanı təsdiqli
  sayılırdı. Düzəliş: `email` olmayan userinfo-dan `email_verified` atılır. Üç test əlavə edildi.

## E. Universitet ayarları

- **E1** (aşağı) — Qismən. Termin olmayanda limit 0 göstərilirdi. Düzəliş: limit `None`, ekranda "—"; ekran `counted`-dan istifadə edir.
- **E2** (orta) — Təsdiqləndi. Tapşırıq 17-dən əvvəlki baza `tenant` ayarını almırdı (qeydiyyat prefiksi `DOC` olurdu). Düzəliş:
  `store.init` çatışmayan `tenant`-ı `content/seed.json`-dan doldurur.
- **E3** — Zərərsiz. Yenə də düzəldildi: `type(x) is int`, yalnız `staff` və `student` saxlanılır.
- **E4** (aşağı, arxitektura) — Təsdiqləndi. Düzəliş: `integration/routes.py` `directory.service.get` və `legacy.common` köməkçilərini işlədir.
- **E5** — `loadRefs` qismən: 403-dən başqa xəta indi bildiriş göstərir. `main.js` hissəsi təkzib olundu.
- **E6** — Təkzib olundu (dizayn).
- **E7** (aşağı) — Qismən, üstəlik yeni 500: `10**400` `OverflowError` verirdi. Düzəliş: `_num` `OverflowError`-u tutur;
  komponentin açarları məhduddur; keçid balı ≥ 1; şkala hədləri (0, 100]; `attendance_points` komponentin maksimumunu keçmir.

## T. Test boşluqları

- **T1** — Təsdiqləndi. Fayl yükləmə testi `.txt` yükləyirdi, o rədd edilirdi və yoxlama atlanırdı. İndi əsl PDF yüklənir.
- **T2** — Təsdiqləndi. İkinci addımı gözləyən sessiya üçün parol, mfa/disable, rol və sessiyalar 403; tələbənin rol keçidi
  bütün işçi rolları üzrə yoxlanır.
- **T3** — Təsdiqləndi. Ləğv testi öz tələbəsini işlədir və `revoked_at`-ı yoxlayır.
- **T4** — Təsdiqləndi. `verify` çağırışları sayılır; uğurlu girişdən sonra `failed_count = 0`; müvəqqəti parol sessiyaları bitirir.
- **T5** — Təsdiqləndi. Üzrlü buraxılış hər iki bayraq üçün; `attendance_points` dəqiq dəyərləri; hər yoxlama budağı üçün 400.
- **T6** — Qismən. `or "left"` silindi; vaxt yoxlaması əvəzinə bloklanmış cəhdin 0 scrypt etdiyi yoxlanır.

## Təhlükəsizlik yoxlaması

`security-review` bacarığı `origin/HEAD` olmadığı üçün işə düşmədi. Eyni yoxlamanı `ecc:security-reviewer` commit olunmamış
diff üzərində apardı: `before()`, dekanlığın əhatəsi, aktivləşdirmə, giriş limitləri, SSO, router, XLSX və CSV. Yüksək
inamlı istismar olunan zəiflik qalmadı. Həddən aşağı bir qeyd (4300+ rəqəmli id) D7-yə əlavə olunub düzəldildi.

## Yoxlama zamanı tapılan

- `tools/i18n.py` `TableError` mətnlərini çıxarmırdı: idxal xətaları ingilis və rus dilində azərbaycanca görünürdü. Skaner
  düzəldildi, 21 mətn tərcümə olundu (`i18n/*/server-13.json`).

## Açıq qalanlar

- Real TLS IdP ilə SSO və sahibin real Forma №3 faylları yoxlanmayıb (real faylların repoya düşməməsi qərarı qüvvədədir).
- `journal.cutover_date`, `lesson_times`, `holidays` hələ yalnız saxlanılır; jurnal Faza 3-dədir.
- Gələcək tarixli qrup dəyişikliyi daxil edildiyi anda tətbiq olunur; köhnə oxuyucular `end_date`-i nəzərə almır.
- Sahibin təsdiqi lazımdır: test nüsxəsinin daimi ünvanı, rol cədvəli, `qa.moderate` / `community.moderate` bölgüsü.
