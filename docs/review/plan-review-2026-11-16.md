# Planın tənqidi yoxlaması — 2026-11-16

Yoxlanan sənədlər: `SPEC.md`, `tasks/plan.md`, `tasks/todo.md` (commit `68c3484`).
Üsul: dörd müstəqil rəyçi (hər biri ən çox 6 tapıntı), sonra hər tapıntı üçün ayrı təkzib agenti.
Nəticə: 24 tapıntı; 5 tam, 19 qismən təsdiqləndi; 0 təkzib olundu.
Aşağıdakı düzəlişlər təkzib agentinin yenidən yazdığı minimal variantdır və sənədlərə tətbiq olunub.
Mətnlər agentlərin yazdığı kimi, ingiliscə saxlanılıb.

| № | Baxış | Dərəcə | Hökm | Tapıntı |
|---|---|---|---|---|
| C01 | Təhlükəsizlik və imtahan | bloklayıcı | təsdiqləndi | Exam answer key is reachable through the practice tutor and practice quizzes; T26's "no answer" test looks only at exam routes |
| C02 | Təhlükəsizlik və imtahan | bloklayıcı | qismən təsdiqləndi | Exam lockdown is bound to one session, not to the student; a second session keeps full access and the scope test checks one direction only |
| C03 | Təhlükəsizlik və imtahan | əsas | qismən təsdiqləndi | No trusted-proxy rule: behind Caddy the exam network list, the per-client limits and the SEB URL hash all use the wrong address or URL |
| C04 | Təhlükəsizlik və imtahan | əsas | qismən təsdiqləndi | Authenticator throttling is under-specified: guessable activation codes, unthrottled TOTP, and a lockout any student can aim at another account |
| C05 | Təhlükəsizlik və imtahan | əsas | qismən təsdiqləndi | The hash chain does not cover answers or scores, and its root is anchored inside the database it is meant to protect |
| C06 | Təhlükəsizlik və imtahan | əsas | qismən təsdiqləndi | OIDC: users are matched by `email`, mandatory ID-token checks are absent from the criteria, and A9 rests on a wrong premise about RS256 |
| C07 | Tədris şöbəsi | bloklayıcı | qismən təsdiqləndi | Teaching model is one course = one teacher = one flat roster: lecture streams, per-group seminars, lab subgroups and substitute teachers cannot be represented |
| C08 | Tədris şöbəsi | bloklayıcı | qismən təsdiqləndi | Mid-semester cutover has no way to load attendance and scores from weeks 1-9, so the 25% status and totals start from zero |
| C09 | Tədris şöbəsi | əsas | təsdiqləndi | The 25% rule is encoded ambiguously or wrongly in four places: denominator, excused absences, who may set the threshold, and the 10 attendance points |
| C10 | Tədris şöbəsi | əsas | qismən təsdiqləndi | Exam session lifecycle is incomplete: a barred student can start the exam, and there is no attempt dimension for retakes, academic debts or the official grade statement |
| C11 | Tədris şöbəsi | əsas | qismən təsdiqləndi | No student status changes by order (academic leave, expulsion, transfer, reinstatement) and no task builds the promised "Tələbə-məzun" export |
| C12 | Tədris şöbəsi | əsas | qismən təsdiqləndi | No curriculum, individual study plan, course registration or credit accounting, and the transcript is switched to real data before any history exists |
| C13 | İstismar və miqrasiya | bloklayıcı | qismən təsdiqləndi | Cutover plan names no system of record; wave closing conditions contradict each other and rollback drops everything written after cutover |
| C14 | İstismar və miqrasiya | bloklayıcı | təsdiqləndi | Mid-semester journal cutover has no import path for attendance and grades already recorded |
| C15 | İstismar və miqrasiya | bloklayıcı | qismən təsdiqləndi | Backup as specified can fail to complete under writes, stays on the host it protects, and allows a 24-hour loss on exam days |
| C16 | İstismar və miqrasiya | əsas | qismən təsdiqləndi | Long work shares the two handler slots and SQLite's single write lock: one import stalls every writer |
| C17 | İstismar və miqrasiya | əsas | təsdiqləndi | Throughput claim was measured on the 147-user demo database, read-only, in one process; no load test uses real-size data or the target server |
| C18 | İstismar və miqrasiya | əsas | qismən təsdiqləndi | Server time: the container runs in UTC while every rule assumes naive Asia/Baku time; no task fixes or tests it |
| C19 | İcra | bloklayıcı | qismən təsdiqləndi | Dalğa 0 semestrin ortasında keçir, amma indiyə qədərki davamiyyət və balların idxal yolu yoxdur |
| C20 | İcra | bloklayıcı | qismən təsdiqləndi | Checkpoint D saat 52-də keçilə bilmir: SEB kompüterinin çatdığı mühit, imtahan yük ssenarisi və imtahan günü runbook-u ondan sonrakı tapşırıqlardadır |
| C21 | İcra | əsas | qismən təsdiqləndi | Paralel zolaqlar asılılıqlarla ziddir; real kritik zəncir 19 ardıcıl tapşırıqdır və kəsmə sırası onu qısaltmır |
| C22 | İcra | əsas | qismən təsdiqləndi | Sahibdən gəlməli üç giriş "Sahibin addımları"nda yoxdur: NICE faylı (nist.gov bu sessiyadan bağlıdır), marşrut qrafı, parolsuz .seb |
| C23 | İcra | əsas | təsdiqləndi | Miqrasiya faylları: Task 12 və 24 tətbiq olunmuş faylı dəyişir, Task 4 bunu qadağan edir; 9 tapşırığın sxem dəyişikliyi üçün fayl göstərilməyib |
| C24 | İcra | əsas | qismən təsdiqləndi | Rol adları üç sənəddə fərqlidir: `office` itib, `moderator` təyin olunmayıb, klub rəhbərinin rol id-si yoxdur |

## C01. Exam answer key is reachable through the practice tutor and practice quizzes; T26's "no answer" test looks only at exam routes

- Baxış: Təhlükəsizlik və imtahan · Dərəcə: bloklayıcı · Hökm: təsdiqləndi
- Yer: tasks/todo.md Task 26 (AC 3), also Task 40 (AC 1); SPEC.md Boundaries "Heç vaxt"

**Təkzib cəhdinin nəticəsi (qısaldılıb):**

I tried to refute this and could not. The core claim stands; three parts of the proposed fix should be dropped or tightened.

**Why the core claim stands**

- **No separation exists in the documents.** A search of SPEC.md, tasks/plan.md and tasks/todo.md for hovuz/pool/practice/məşq/"sual bank" finds only todo.md:465 ("plana görə hovuzlardan variant qurulması"). Out of Scope, Open Questions, Risks and the cut order say nothing on it.
- **Reuse of `questions` is implied, not just left open.** T26 …

**Tətbiq olunan düzəliş:**

No file was modified. Apply these four edits.

**1. tasks/todo.md, Task 26 Description — append:**

"Sual hovuzu: `0009_exam.sql` `questions.purpose` sütununu əlavə edir (`practice` | `exam`, susmaya görə `practice`). Dəyər sual ilk dəfə təsdiqlənəndə seçilir və sonra dəyişmir. İmtahan planı yalnız `purpose='exam'` suallardan qurulur və onları `learning` servisinin funksiyası ilə oxuyur. `purpose='exam'` sual tələbəyə yalnız `scope="exam"` marşrutları ilə, öz cəhdi daxilində gedir: `practice_turn`, `INDEX["questions"]`, Radar-ın məşq addımı onu istisna edir, `quiz_create` 400 qaytarır."

**2. tasks/todo.md, Task 26 — replace AC 3 with two criteria:**

- "[ ] Tələbəyə açıq hər imtahan marşrutunun cavabı icazə siyahılı sxemlə yoxlanır (sual üçün yalnız `id`, `qtype`, `text`, `options`, `unit`); siyahıda olmayan hər açar (`answer`, `explanation`, `correct`, `score` daxil) testi yıxır. Açıqlamadan sonra tələbə yalnız yekun balı və nəticə üzrə bölgünü görür; sualın açarı və izahı V1-də heç bir tələbə marşrutunda qayıtmır."
- "[ ] Sızma testi: mətnində, variantlarında və izahında nişan sətri olan `purpose='exam'` suallardan imtahan qurulur; fənnə yazılmış tələbə adi sessiya ilə marşrut cədvəlindəki bütün GET marşrutlarını çağırır, Məşq rejimində hovuz tükənənə qədər tutorla danışır və Radar planını açır; heç bir cavabda nişan yoxdur. `purpose='exam'` sualın testə əlavə edilməsi və təsdiqlənmiş sualın `purpose`-unun dəyişdirilməsi 400 qaytarır."

Also in Task 26:
- Verification: add `tests/security/test_exam_item_leak.py`.
- Files likely touched: add `backend/zeka/legacy/{r_learning,store,radar}.py` and `tests/security/test_exam_item_leak.py`.

**3. tasks/todo.md, Task 40 AC 1 — append:**

"İstisna: `exam_forms` və açıqlanmamış imtahan balı ixraca düşmür; açıqlamadan sonra ixrac yalnız tələbənin öz cavablarını və balını verir, sual mətni və açar yoxdur. İstisna `data-inventory.md`-də yazılır; T26-nın sızma testi `/api/me/export`-u da çağırır."

**4. SPEC.md line 234 ("Heç vaxt") — replace with:**

"İmtahan hovuzundakı sualın mətninin, açarının və ya izahının imtahan cəhdindən kənar hər hansı marşrutla (tutor, məşq testi, Radar, ixrac) tələbəyə getməsi; balın nəticə açıqlanmadan getməsi."

**Left out of the reviewer's fix on purpose:**
- the T33 FAQ-index clause;
- the "pool retired" mechanism;
- the course-wide tutor lock when the exam window opens.

**Decision for the owner:** whether students ever see item keys after release, for example in appeals. The default written above is no in V1; review happens on the teacher's screen.

## C02. Exam lockdown is bound to one session, not to the student; a second session keeps full access and the scope test checks one direction only

- Baxış: Təhlükəsizlik və imtahan · Dərəcə: bloklayıcı · Hökm: qismən təsdiqləndi
- Yer: tasks/todo.md Task 27 (description, AC 1, AC 3) and Task 29 ("Girişdə şəbəkə siyahısı yoxlanır"); SPEC.md Success Criteria row `exam`; plan.md A10

**Təkzib cəhdinin nəticəsi (qısaldılıb):**

I tried to refute it from the documents and the code. About half falls and half stands.

WHAT STANDS (could not refute)

1. Scope is enforced and tested in one direction only.
- tasks/todo.md:481 says only "Router bu əhatəli sessiyaya yalnız `scope="exam"` marşrutlarını açır". Nothing says a `scope="exam"` route requires a scoped session.
- AC 1 (todo.md:484) and the SPEC `exam` row (SPEC.md:249) test only "exam session → non-exam route 403".
- The SPEC sample (SPEC.md:171, 179) gates `PUT /api/ …

**Tətbiq olunan düzəliş:**

Do not adopt "every session of that user gets 403 on non-exam routes while an attempt is in progress". Make these edits instead.

1. tasks/todo.md, Task 27 description. Replace "Router bu əhatəli sessiyaya yalnız `scope="exam"` marşrutlarını açır." with:
"Əhatə iki istiqamətlidir: `exam:{id}` əhatəli sessiya yalnız `scope="exam"` marşrutlarına çatır; `scope="exam"` marşrutu yalnız əhatəsi həmin marşrutun imtahanına bərabər olan sessiyaya açılır (adi sessiya və başqa imtahanın sessiyası 403 alır)."

2. Task 27 description. Replace "Yeni giriş köhnə sessiyanı bağlayır." with:
"Tək sessiya: imtahana giriş tələbənin bütün başqa sessiyalarını bağlayır. Cəhd gedərkən adi giriş imtahan sessiyasını bağlamır və imtahan marşrutlarına çatmır; cəhdi yalnız T28 və T29 yoxlamalarından keçən yeni imtahana giriş öz üzərinə götürür və əvvəlki imtahan sessiyasını bağlayır. Hər iki hal imtahan hadisəsi kimi yazılır."
This choice (an ordinary login does not close the exam session) is mine and needs the owner's confirmation. The literal alternative, last login wins, lets anyone with the password knock the examinee out.

3. Task 27 AC 1. Replace with:
"- [ ] Marşrut cədvəlindən qurulan avtomatik test: imtahan əhatəli sessiya ilə imtahandan kənar hər marşrut 403; adi tələbə sessiyası ilə hər `scope="exam"` marşrutu 403; `exam:1` sessiyası ilə 2-ci imtahanın cəhd marşrutları 403"

4. Task 27 AC 3. Replace with:
"- [ ] İmtahana giriş tələbənin başqa sessiyalarını bir sorğu ərzində bağlayır; cəhd gedərkən adi giriş imtahan sessiyasını bağlamır; ekrandakı taymer server son vaxtını keçmir"

5. Task 28 AC 2. Replace with:
"- [ ] `seb` rejimində səhv və ya olmayan hash ilə cəhd başlamır və yoxlanmamış sessiya mövcud cəhdin sual və cavab marşrutlarında 403 alır; bir sessiyada tutulan hash başqasında rədd olunur"

6. Task 29 description. Replace "Girişdə şəbəkə siyahısı yoxlanır." with:
"Şəbəkə siyahısı girişdə və hər `scope="exam"` sorğusunda yoxlanır: siyahıdan kənar ünvan 403 alır və jurnala yazılır; siyahı daxilində ünvan dəyişməsi lövhə hadisəsidir."

7. Task 29 AC 1. Replace with:
"- [ ] `allowed_cidrs`-dən kənar ünvandan giriş və cəhd ortasında gələn sorğu rədd olunur və jurnala yazılır"

8. SPEC.md Success Criteria row `exam`. Replace the first sentence with:
"İmtahan sessiyası ilə imtahandan kənar hər marşrut, adi sessiya və ya başqa imtahanın sessiyası ilə hər imtahan marşrutu 403 (bütün marşrut cədvəli üzrə avtomatik test)."
Replace "Eyni tələbənin ikinci sessiyası birincini bağlayır." with:
"İmtahana giriş tələbənin başqa sessiyalarını bağlayır; cəhd gedərkən adi giriş imtahan sessiyasını bağlamır. `allowed_cidrs`-dən kənar sorğu cəhd ortasında da rədd olunur."

9. tasks/plan.md A10 needs no change. The edits above make its four named protections true as stated.

## C03. No trusted-proxy rule: behind Caddy the exam network list, the per-client limits and the SEB URL hash all use the wrong address or URL

- Baxış: Təhlükəsizlik və imtahan · Dərəcə: əsas · Hökm: qismən təsdiqləndi
- Yer: tasks/todo.md Task 9, Task 29 (AC 1), Task 28, Task 7 (AC 2), Task 5; plan.md A4

**Təkzib cəhdinin nəticəsi (qısaldılıb):**

I tried to refute each of the four parts. The core survives, one part falls, and one part is overstated.

**Confirmed: no trusted-proxy rule for the client address (T09, T29, A4)**
- `/home/user/AzTU-Zeka/app/security.py:35` sets `proxy_hops` from `ZEKA_PROXY_HOPS` with default 0. Lines 97-105 return the socket peer unless hops is set, otherwise `xff[-hops]`. The working tree is identical to `trial/integration`.
- A search of `SPEC.md`, `tasks/plan.md` and `tasks/todo.md` for proxy, `PROXY_HOPS` …

**Tətbiq olunan düzəliş:**

Six edits; T05's mode rule and T07 stay as they are.

1. **`tasks/plan.md`, A4, "Qərar" cell** — append: "Tətbiqin portu kənara açılmır; müştəri ünvanı yalnız Caddy-nin yazdığı `X-Forwarded-For`-dan oxunur (`ZEKA_PROXY_HOPS=1`)."

2. **`tasks/todo.md`, Task 5** (it owns `core/config.py` and `test_modes.py`)
   - Description, append: "Prod rejimində `PUBLIC_URL` `https://` ilə başlayırsa və `ZEKA_PROXY_HOPS=0`-dırsa server açılmır və səbəbi yazır (tətbiq TLS danışmır, deməli qabaqda proksi var)."
   - Acceptance criteria, add: "- [ ] Prod rejimində `PUBLIC_URL=https://…` və `ZEKA_PROXY_HOPS=0` ilə server açılmır"

3. **`tasks/todo.md`, Task 9**
   - Description, append: "`compose.yml`-də tətbiq servisinin `ports:` bəndi yoxdur (yalnız daxili şəbəkə); `ZEKA_MODE=prod`, `PUBLIC_URL` və `ZEKA_PROXY_HOPS=1` `.env.example`-dədir. Caddyfile-da `trusted_proxies` təyin olunmur. Qabaqda ikinci proksi olarsa hop sayı və `trusted_proxies` birlikdə dəyişir (runbook)."
   - Acceptance criteria, add: "- [ ] Caddy arxasında giriş jurnalındakı müştəri ünvanı Caddy konteynerinin ünvanı deyil; müştərinin özü göndərdiyi `X-Forwarded-For: 1.2.3.4` jurnalda ünvan kimi görünmür; tətbiqin portu hostdan açılmır"
   - Verification, add: "- [ ] `curl -sk -H 'X-Forwarded-For: 1.2.3.4' https://localhost/healthz`, sonra `docker compose -f infra/compose.yml logs app | grep -c '1.2.3.4'` 0 qaytarır və jurnaldakı ünvan `docker compose exec caddy hostname -i` çıxışından fərqlidir; `curl -s -m 3 http://localhost:5070/healthz` qoşula bilmir"

4. **`tasks/todo.md`, Task 29, AC 1** — replace with: "- [ ] `allowed_cidrs`-dən kənar ünvandan giriş rədd olunur və jurnala yazılır. Ünvan `client_ip()`-dən gəlir; `ZEKA_PROXY_HOPS=1` ilə üç hal yoxlanır: `X-Forwarded-For` siyahıdadır (buraxılır), kənardadır (rədd), `içəri-saxta, kənar-real` (rədd: sağdan birinci ünvan götürülür). `ZEKA_PROXY_HOPS=0` ilə başlıq nəzərə alınmır."
   - Verification stays `tests/integration/test_proctor.py`: the in-process server with `CFG.proxy_hops` set, the test sending the headers itself.

5. **`tasks/todo.md`, Task 28**
   - Description, replace "server `sha256(fraqmentsiz URL + açar)` ilə sabit vaxtlı müqayisə edir" with: "server `sha256(URL + açar)` ilə sabit vaxtlı müqayisə edir; başlıq yolunda URL = `PUBLIC_URL` + sorğunun xam hədəfi (`handler.path`: dekodlanmamış yol və sorğu sətri), JS API yolunda müştərinin göndərdiyi `location.href`-in sxemi və hostu `PUBLIC_URL` ilə eyni olmalıdır".
   - Acceptance criteria, add: "- [ ] `PUBLIC_URL` dinləmə ünvanından fərqli olanda (`https://zeka.test`) və URL-də `%2F` və iki parametr olanda düzgün hash qəbul olunur; `http://127.0.0.1:port` üzərində hesablanan hash rədd olunur"
   - Verification stays `tests/integration/test_seb_verify.py`.

6. **Do not adopt** the finding's two T05 proposals (start fails if `PUBLIC_URL` is set without `ZEKA_MODE`; demo routes 404 on `X-Forwarded-For`).

## C04. Authenticator throttling is under-specified: guessable activation codes, unthrottled TOTP, and a lockout any student can aim at another account

- Baxış: Təhlükəsizlik və imtahan · Dərəcə: əsas · Hökm: qismən təsdiqləndi
- Yer: tasks/todo.md Task 16 (AC 3), Task 12 (ACs), Task 10 (AC 2); Checkpoint B

**Təkzib cəhdinin nəticəsi (qısaldılıb):**

I could not refute the three gaps; several sub-claims are overstated and the proposed fix has defects. Nothing in Out of Scope, Open Questions, Risks, the cut order or A1–A18 mentions activation codes, TOTP throttling or lockout.

**What stands**

1. **T16 activation codes.** tasks/todo.md:281 says only "Aktivləşdirmə kodları: birdəfəlik, müddətli, dekanlıq üçün CSV"; AC todo.md:286 tests one-time use and expiry. Length, identity binding, storage and throttling are absent.
   - Every other secre …

**Tətbiq olunan düzəliş:**

All edits are in tasks/todo.md.

**Task 16**
- Replace the last sentence of the description with: "Aktivləşdirmə kodları yalnız `student` rolu üçündür; işçi hesabı T10-dakı admin müvəqqəti parolu ilə açılır. Kod: `secrets` ilə 60 bit (12 base32 simvol), yalnız verildiyi tələbə nömrəsi ilə birlikdə qəbul olunur, bazada yalnız SHA-256-sı saxlanır, birdəfəlikdir, müddəti tenant ayarıdır (susmaya görə 14 gün). Dekanlıq CSV-si fakültə üzrə yaradılanda bir dəfə verilir; yenidən yaratma köhnə kodları ləğv edir. Yanlış kod cəhdləri T10-dakı (hesab, ünvan) məhdudiyyətindən keçir; yanlış cəhd kodu ləğv etmir."
- Replace AC 3 with: "Aktivləşdirmə kodu bir dəfə işləyir və müddəti bitəndə rədd olunur; düzgün kod başqa tələbə nömrəsi ilə rədd olunur; bazada açıq kod yoxdur (yalnız hash); bir ünvandan 10 yanlış koddan sonra 429, başqa ünvandan düzgün kod işləyir."
- Do not add an export-audit clause (SPEC.md:218 covers it) and do not add "Nth wrong code invalidates".

**Task 12**
- Add to the description: "Yanlış TOTP və bərpa kodu T10-dakı (hesab, ünvan) sayğacına düşür. TOTP toxumu bazada açıq saxlanır (stdlib-də simmetrik şifr yoxdur); bu T41 təhdid modelində qəbul edilmiş risk kimi yazılır; sahib `cryptography` icazəsi versə mühit açarı ilə şifrələnir."
- Add an AC: "5 ardıcıl yanlış TOTP və ya bərpa kodu gözləyən girişi ləğv edir (parol addımı təkrarlanır); bundan sonra düzgün kod da rədd olunur."

**Task 10**
- Replace AC 2 with: "Uğursuz cəhdlər (hesab, müştəri ünvanı; IPv6-da /64) üzrə sayılır: 15 dəqiqədə 10 uğursuz cəhd həmin ünvanı həmin hesab üçün 15 dəqiqə bloklayır (429 və `Retry-After`; handler yatmır; blok scrypt-dən əvvəl yoxlanır; blok zamanı rədd edilən cəhd sayılmır). Hesab üzrə ardıcıl 100 uğursuz cəhd hesabı 15 dəqiqə kilidləyir. Hər blok və kilid audit hadisəsi yazır; admin kilidi səbəblə aça bilir. Test: A ünvanından 50 yanlış parol B ünvanından düzgün girişi gecikdirmir."
- Change Dependencies to "Task 5, Task 7" (the shared limiter table).

**Task 29**
- Add to the reasoned operations in the description: "giriş kilidini aç (yalnız öz imtahan siyahısındakı tələbə üçün)". The existing AC 2 already requires reason and exam-log entry.

**Task 9** (only if the separate trusted-proxy finding does not already add it)
- Description: "`infra/compose.yml` tətbiqə `ZEKA_PROXY_HOPS=1` verir; tətbiq portu yalnız Caddy-yə açıqdır."
- AC: "Caddy arxasında iki fərqli müştəri tətbiqdə fərqli ünvanla görünür; müştərinin göndərdiyi `X-Forwarded-For` nəzərə alınmır."

**Wording alignment**
- tasks/plan.md:87: change "öz hesabı ilə girir" to "aktivləşdirmə kodu ilə öz hesabına girir", matching todo.md:315.

## C05. The hash chain does not cover answers or scores, and its root is anchored inside the database it is meant to protect

- Baxış: Təhlükəsizlik və imtahan · Dərəcə: əsas · Hökm: qismən təsdiqləndi
- Yer: tasks/todo.md Task 30 (description, AC 1, AC 2), Task 26; plan.md A11; SPEC.md replacement matrix ("hash zəncirli QR protokol")

**Təkzib cəhdinin nəticəsi (qısaldılıb):**

I tried to refute all three parts of the problem and could not. The problem statement stands; about a third of the proposed fix does not.

WHAT STANDS

1. Answers and scores are outside the chain.
- /home/user/AzTU-Zeka/tasks/todo.md:531 (T30) chains only `exam_events`.
- todo.md:515 and :519 (T29) are the only places that say what an event is: focus loss, fullscreen exit, reconnect, address change, and proctor actions.
- Answers go to `exam_answers` (todo.md:465) by "tək UPSERT" (/home/user/AzT …

**Tətbiq olunan düzəliş:**

Do not add HMAC or `ZEKA_CHAIN_KEY`. Make the changes below.

1) tasks/todo.md, Task 30 Description. Insert after the first sentence:

"Zəncir imtahan üzrə təkdir və `seq` ilə sıralanır: `UNIQUE(exam_id, seq)`; əlavə `BEGIN IMMEDIATE` içində gedir (başı oxu → hesabla → yaz). T29 hadisələrindən əlavə: təslimdə və avtomatik təslimdə `attempt.submitted {attempt_id, form_seed, answers_sha256}` (`answers_sha256` = `qid` üzrə sıralanmış `(qid, value)` siyahısının kanonik JSON-unun SHA-256-sı); bağlananda qiymətləndirmədən sonra `attempt.graded {attempt_id, score}`, sonra `exam.closed`. `exam-verify <id> [--root <hex>]` halqaları yoxlayır, hər cəhdin son `attempt.submitted` dəyərini `exam_answers`-dən, `attempt.graded` dəyərini `exam_attempts`-dən yenidən hesablayır, başı protokoldakı köklə və verilibsə `--root` ilə tutuşdurur. Kök bazadan kənara çıxır: protokolda tam 64 simvol çap olunur və bağlananda outbox (T36) ilə imtahan müəlliminə və dekanlığa göndərilir. Bağlanandan sonrakı bal dəyişikliyi (apellyasiya) yalnız jurnalda, səbəb və müəlliflə aparılır (T21); `exam_attempts` dəyişmir."

2) Task 30 Acceptance criteria.

Replace AC 1 with:
"Saxlanan hər hansı hadisənin (sonuncu daxil) dəyişdirilməsi və ya silinməsi `exam-verify`-ı yıxır və ilk qırıq halqanı göstərir"

Add:
"Təslimdən sonra `exam_answers.value`-nun və ya bağlanandan sonra `exam_attempts` balının bazada birbaşa dəyişdirilməsi `exam-verify`-ı yıxır və cəhdi göstərir; `yenidən aç`-dan sonrakı yeni təslim yıxmır"

Replace AC 2 with:
"Protokolun QR-i doğrulanır və eyni kökü göstərir; zəncir və protokol sətri bazada yenidən hesablanıb yazılandan sonra `exam-verify --root <e-poçtdakı kök>` yıxılır"

Add:
"İki prosesdən 500 paralel hadisə boşluqsuz bir zəncir verir (`seq` 1..N) və `exam-verify` keçir"

3) Task 30 Verification, Dependencies and Files.
- Verification: add `tests/integration/test_exam_chain_concurrency.py` to the pytest line.
- Dependencies: "Task 26, Task 29, Task 36". T36 runs at hours 22–36 and T30 at 36–52, so the schedule does not change.
- Files: add the migration that creates `exam_events`, for the `UNIQUE(exam_id, seq)` constraint.

4) tasks/plan.md A11.

Decision: "İmtahan hadisələri, hər təslimin cavab hash-i və hər bal hash zənciri ilə yazılır; kök QR-lı protokola düşür və e-poçtla bazadan kənara göndərilir."

Basis: "Sonradan dəyişdirilmə aşkar olunur: zəncir bazada yenidən hesablansa belə kök kənardakı nüsxə ilə üst-üstə düşmür. Mövcud QR sənəd infrastrukturu təkrar istifadə olunur."

Revisit condition: "Rəddedilməzlik tələb olunsa: SİMA/ASAN İmza (Out of Scope)."

5) tasks/todo.md Task 41 Description. Add:

"research/04-dəki 22-ci nəzarət SI-7-yə xəritələnir, sübut T30 testləridir; AU-10 'iddia olunmur' statusu ilə yazılır (imza yoxdur)."

Optional, one line each:
- T42 Verification: run `python backend/manage.py exam-verify <yük imtahanı>` after the load run.
- T43 exam-day runbook: "protokol çap olunur və imzalanır".

## C06. OIDC: users are matched by `email`, mandatory ID-token checks are absent from the criteria, and A9 rests on a wrong premise about RS256

- Baxış: Təhlükəsizlik və imtahan · Dərəcə: əsas · Hökm: qismən təsdiqləndi
- Yer: tasks/plan.md A9; tasks/todo.md Task 14; SPEC.md Tech Stack line on `cryptography`

**Təkzib cəhdinin nəticəsi (qısaldılıb):**

Four of the six sub-claims survive; the headline fix (replace A9 with mandatory RS256 verification) and the T41/FAL consequence do not.

Not verified online: openid.net and pages.nist.gov do not resolve from this session (they must be allowed in the session's network settings). OIDC Core 3.1.3.7, 5.3.2, 5.7 and SP 800-63C are cited from memory.

CONFIRMED

1. Account matching by e-mail (the major half).
- tasks/todo.md:248 reads "İddia → istifadəçi uyğunlaşdırması (`email` və ya tələbə nömrəsi)" …

**Tətbiq olunan düzəliş:**

Keep A9's decision. Make these edits.

1. tasks/todo.md Task 14, Description. Replace the sentence "İddia → istifadəçi uyğunlaşdırması (`email` və ya tələbə nömrəsi)." with:
"Hesab (`iss`, `sub`) cütünə bağlanır; bağlantı `sso_identities(user_id, iss, sub)` cədvəlində saxlanır və sonrakı girişlər yalnız onunla tapılır. İlk bağlantı ayarda adı verilən tələbə nömrəsi iddiası ilə, və ya `email` ilə yalnız `email_verified=true` olanda və yerli hesabın işçi rolu olmayanda qurulur. İşçi rolu olan hesabı yalnız sahibi yerli parol + TOTP sessiyasından, və ya admin bağlayır. ID token OIDC Core 3.1.3.7 üzrə yoxlanır (`iss`, `aud`, `exp`, `nonce`); `userinfo`-nun `sub`-u ID token-in `sub`-u ilə eyni olmalıdır (5.3.2). Issuer və kəşf sənədindəki bütün son nöqtələr `https` olmalıdır; `http` yalnız demo rejimində loopback üçün; sertifikat yoxlamasını söndürən ayar yoxdur."

The reviewer's "staff links are created by an admin" alone is impractical for 1,000+ teachers, hence the self-link from a local password + TOTP session.

2. tasks/todo.md Task 14, Acceptance criteria. Add three:
- "Yanlış `iss`, yanlış `aud`, vaxtı keçmiş `exp`, və ya `userinfo` `sub`-u ID token `sub`-undan fərqli olan cavab rədd olunur"
- "IdP-də `email` dəyişdirilməsi girişi başqa yerli hesaba keçirmir; `email_verified` doğru deyilsə `email` ilə ilk bağlantı qurulmur; işçi hesabı `email` ilə avtomatik bağlanmır"
- "Prod rejimində `http://` issuer və ya kəşf sənədindəki `https` olmayan son nöqtə ilə SSO açılmır"

Do not add the reviewer's "bad signature or `alg=none`" criterion: there is no signature check under A9. Do not add the self-signed-certificate fake IdP: the stdlib cannot create a certificate.

3. tasks/todo.md Task 14, Files likely touched. Add `backend/migrations/0003_identity.sql` (the `sso_identities` table, unique on (`iss`, `sub`)).

4. tasks/plan.md A9. Decision column unchanged.
- "Əsas" column becomes: "OIDC Core 3.1.3.7 bənd 6 kod axınında buna icazə verir; həmin bölmənin qalan yoxlamaları (`iss`, `aud`, `exp`, `nonce`) və 5.3.2 tətbiq olunur. JWKS eyni TLS ilə gəldiyi üçün imza yoxlaması əlavə etibar lövbəri vermir. Hesab (`iss`, `sub`) ilə bağlanır."
- "Yenidən baxma şərti" column becomes: "AzTU SSO-su SAML-dırsa `cryptography` icazəsi. FAL iddiası tələb olunsa və ya token ön kanaldan gəlsə: JWKS ilə RS256 yoxlaması (stdlib ilə, asılılıqsız)."

5. SPEC.md:102. Change the parenthesis to: "`cryptography` (SAML XML imzası və ya RS256 ilə imzalama lazım olsa; RS256 imzasının yoxlanması stdlib ilə mümkündür)".
SPEC.md:263. Change to: "LTI 1.3 və SAML: XML imzası və RS256 ilə imzalama üçün asılılıq icazəsi lazımdır."

## C07. Teaching model is one course = one teacher = one flat roster: lecture streams, per-group seminars, lab subgroups and substitute teachers cannot be represented

- Baxış: Tədris şöbəsi · Dərəcə: bloklayıcı · Hökm: qismən təsdiqləndi
- Yer: tasks/todo.md Task 15, Task 16, Task 19, Task 20, Task 13; SPEC.md Capability Map rows `directory`, `timetable`

**Təkzib cəhdinin nəticəsi (qısaldılıb):**

The core defect stands: I could not refute it. Three parts of the finding do not hold, and the proposed fix is larger than it needs to be.

WHAT I CHECKED AND WHAT HOLDS

1. Code facts are all true.
- /home/user/AzTU-Zeka/app/store.py:29 `courses(... teacher_id INT ...)`, :31 `enrollments(user_id, course_id)`, :32-33 `timetable` and `lessons` have no group and no teacher column, :26 one `group_id` per user.
- /home/user/AzTU-Zeka/app/common.py:113 is the teacher check (the function starts at 106 …

**Tətbiq olunan düzəliş:**

Keep the teaching-unit idea, drop `course_offerings` and the per-component writer rule, and reduce substitution to one column.

1. tasks/todo.md Task 15
- Add to the table list, in `0004_directory.sql`: `teaching_units(id, course_id, kind: mühazirə|məşğələ|laboratoriya, teacher_id, subgroup NULL)` and `teaching_unit_groups(unit_id, group_id)`.
- Add nullable `enrollments.group_id` and `enrollments.subgroup`. The default is the student's own group; the override covers a student who repeats the subject with another group.
- State explicitly: no separate offering table; `courses` bound to `academic_terms` is the offering; `courses.teacher_id` stays as the course lead for legacy handlers.

2. tasks/todo.md Task 16
- State the mapping: OneRoster `classes` goes to `teaching_units`; `enrollments` with role=teacher sets the unit teacher; role=student sets the course enrolment plus group and subgroup.

3. tasks/todo.md Task 19
- Change the row to "tədris vahidi, gün, saat, otaq, həftə nümunəsi" (kind and teacher come from the unit).
- Name a migration in "Files likely touched" that adds `timetable.unit_id`, `lessons.unit_id` and `lessons.teacher_id` (copied from the unit when lessons are generated).
- Define the clash check: room, unit teacher, and every (group, subgroup) of the unit. A whole group clashes with its own subgroups; subgroup 1 does not clash with subgroup 2.
- Add an acceptance criterion: "3 qrupluq mühazirə axını, ikinci müəllimin üç məşğələsi və iki yarımqrupda laboratoriya olan fənn toqquşmasız saxlanır; eyni qrupun eyni saatdakı ikinci dərsi rədd olunur".
- Raise the scope from M to L.

4. tasks/todo.md Task 13
- Replace "`teacher` yalnız öz fənninin" with: the teacher's scope is a course they lead or hold a teaching unit in, and journal writes are limited to the roster of their own units and of lessons reassigned to them.

5. tasks/todo.md Task 20
- Roster = course enrolments whose group (and subgroup, if the unit has one) belongs to the lesson's unit.
- Planned hours per student count only lessons of units whose roster contains the student.
- `dept_head` may change `lessons.teacher_id` with a mandatory reason, audited. This is the whole substitution mechanism.
- Add a test: a student in subgroup 1 has no attendance rows for subgroup 2 labs.

6. tasks/todo.md Task 21
- Add one line only: a teacher writes components only for students on their own units' rosters.

7. SPEC.md
- Capability Map row `directory`: add "tədris vahidi (fənn × növ × müəllim × qrup)".
- Add Open Question 11: "Mühazirə axınla, məşğələ qrupla, laboratoriya yarımqrupla keçilirmi; mühazirə və məşğələ müəllimi fərqlidirmi?"

8. tasks/plan.md "Sahibin addımları", hour 10
- Extend "İlk fakültə, fənlər, müəllimlər" with "real cədvəl ixracı: qrup, yarımqrup, dərs növü, müəllim sütunları ilə".
- The unit model is adopted whatever the answer, because the flat case is its degenerate form.

## C08. Mid-semester cutover has no way to load attendance and scores from weeks 1-9, so the 25% status and totals start from zero

- Baxış: Tədris şöbəsi · Dərəcə: bloklayıcı · Hökm: qismən təsdiqləndi
- Yer: tasks/todo.md Task 16, Task 38, Task 20; tasks/plan.md "Miqrasiya və kəsid" Wave 0 and Checkpoint C

**Təkzib cəhdinin nəticəsi (qısaldılıb):**

I tried to refute this and could not refute the core. The attendance half stands in full. The scores half is only half right, three of the stated consequences are overstated, and the proposed fix has an ordering error and a double-count.

WHAT STANDS (checked in the files)
- /home/user/AzTU-Zeka/tasks/plan.md:163 moves "davamiyyət, cari ballar" in Wave 0 at hour 72. SPEC.md:15 defines V1 as running "bir fakültənin cari semestrini real məlumatla" and keeping the whole import/reconcile/cutover mec …

**Tətbiq olunan düzəliş:**

Apply the following; do not apply the reviewer's fix verbatim.

tasks/todo.md

1. Task 16, Description
   - Extend the kind list to `…|rooms|timetable|attendance-opening|grades`.
   - Add one sentence: Task 16 delivers the kind registry, dry-run and all-or-nothing transaction. The loaders for the last two kinds are written in Task 20 and Task 21 as public functions of `journal/service.py` and wired to `manage.py import` in Task 38 (same pattern as rooms in Task 18).
   - Do not add journal code or journal files to Task 16.

2. Task 20, Description
   - Add table `attendance_opening(student, class, unexcused_hours, excused_hours, as_of, source_id)`.
   - Define the percentage as (opening unexcused hours + unexcused hours of Zəka lessons dated after `as_of`) / planned class hours of the course for the semester.
   - Lessons dated on or before `as_of` are not opened for marking and are excluded from the fill-rate metric in Task 39.
   - Opening rows are not lesson records, so the 48-hour window does not apply. They change only by re-import on `source_id` (audited with the importing account and the file's sha256) or by the department head with a reason.
   - An approved excuse for a date on or before `as_of` moves hours from unexcused to excused in the opening row, with the request id as the reason.

3. Task 20, Acceptance criteria — add:
   - A student with an opening balance of 20% of planned hours plus 6% recorded in Zəka gets "imtahana buraxılmır".
   - Re-importing the same file reports 0 changes.
   - Re-importing with a later `as_of` does not double-count Zəka entries before that date.
   - A teacher cannot edit the balance.

4. Task 21, Description — add:
   - Kind `grades` (student, class, component, score, max) writes through the same service path as the grid, with author = importing account and reason = `import:<file sha256>`.
   - The attendance component is never imported; it is computed from the opening balance plus the journal.
   - If scores turn out not to be in KOICA (SPEC.md:28), the same CSV template is the dean's-office fallback and Excel paste remains the per-teacher path.

5. Task 38
   - Description: adapters aggregate the old system's attendance records into `attendance-opening` rows per student × class. The reconcile key fields include unexcused and excused hours per student × class and score per student × class × component.
   - Acceptance: add "Uzlaşdırma tələbə × fənn üzrə buraxılmış saatda və komponent ballarında fərq 0 göstərir".
   - Files: add `backend/zeka/modules/journal/service.py`, `tests/fixtures/attendance_opening.csv`, `tests/fixtures/grades.csv`.

tasks/plan.md

6. Wave 0 row (line 163)
   - "Zəka-ya keçən": replace "davamiyyət, cari ballar" with "davamiyyət (kəsid tarixinə açılış qalığı + həmin tarixdən sonra Zəka-da yazılan), cari ballar (komponent üzrə idxal)".
   - "Köhnə sistem": "Əsas mənbə qalır: imtahana buraxılış statusu bu dalğada köhnə sistemdən götürülür; Zəka statusu qalığın tarixi ilə göstərir".

7. Step 7 "Kəsid" (line 176): add "Davamiyyət qalığı və ballar kəsid anında yenidən idxal olunur (`as_of` = kəsid tarixi)".

8. Risk row (line 193): extend the fallback to name the two extra templates, `attendance-opening.csv` and `grades.csv`.

9. Owner step at hour 6 (line 221): exports must include attendance-to-date and current component scores per student × course for the pilot faculty.

Leave unchanged
- Checkpoint C: it is a functional gate on fixtures.
- The "Uzlaşdırma fərqi 0" wording: item 5 makes it cover journal data.

## C09. The 25% rule is encoded ambiguously or wrongly in four places: denominator, excused absences, who may set the threshold, and the 10 attendance points

- Baxış: Tədris şöbəsi · Dərəcə: əsas · Hökm: təsdiqləndi
- Yer: tasks/todo.md Task 15, 17, 19, 20, 21, 23, 25; SPEC.md Assumption 10; tasks/plan.md decision A12

**Təkzib cəhdinin nəticəsi (qısaldılıb):**

I tried to refute each of the four parts and could not. All four stand in substance. Two points in the finding are overstated and one element of its fix is itself unsourced; those are listed at the end.

**(a) Denominator: stands.**
- /home/user/AzTU-Zeka/tasks/todo.md:358 (Task 20) says only "buraxılmış saat faizi". Its criteria (361-363) and `tests/unit/test_attendance_rules.py` (366) name no numeric case.
- todo.md:341 (Task 19) says "Semestr üçün dərslər yaradılır, bayram günləri buraxılır". …

**Tətbiq olunan düzəliş:**

**SPEC.md**
- Assumption 10 (line 50): state that the teaching period and the exam session are stored separately, and that the seed range 15.09.2026 – 31.01.2027 covers both with an unknown boundary (Open Questions 11).
- Add Assumption 11, to be confirmed by the owner:
  - The 25% denominator is the academic hours of the course's non-cancelled lessons inside the teaching period.
  - Every missed hour counts, excused included. This is the literal reading of the only source, research:44.
  - The attendance 10 points are computed from the journal by a tenant rule table.
- Success Criteria `journal` (line 246): replace "25% həddi tenant ayarındandır" with "effektiv hədd = min(tenant həddi, dərc olunmuş sillabusun həddi)".
- Success Criteria `syllabus` (line 247): the syllabus may only lower the threshold.
- Open Questions: add 11, covering AzTU's official calendar (last teaching day, session dates), whether excused absences count toward the 25%, whether a cancelled lesson stays in the denominator, and the conversion rule for the 10 attendance points.

**tasks/plan.md**
- A12 (line 29): add "davamiyyət həddini yalnız aşağı sala bilər (≤ tenant həddi)".
- Line 231: "10 sual" becomes "11 sual".
- "Sahibin addımları", Saat 10 row: add the attendance and grading regulation and the official academic calendar. Today the regulations arrive only at hour 52 for T32, after T20/T21.

**tasks/todo.md**
- Task 15 (264): `academic_terms` gets `teaching_start`, `teaching_end`, `exam_start`, `exam_end`, with validation `teaching_end < exam_start`.
- Task 17 (298):
  - Remove "semestr tarixləri".
  - Add `attendance.excused_counts_toward_limit` and `attendance.points_rule` (table).
  - `SEM_WEEKS` (r_learning.py:40) is deleted, not turned into a setting.
  - Readers of the `semester_start` setting (r_learning.py:188, radar.py:82, store.py:397-398) switch to the current `academic_terms` row.
- Task 19 (341, 345):
  - Each timetable row carries its academic hours.
  - Lessons are generated only between `teaching_start` and `teaching_end`.
  - New criterion: no lesson is generated after `teaching_end`.
- Task 20 (358, 363): replace "Üzrlü qayıb sayılmır; hədd tenant ayarındandır" with:
  - Percentage = missed academic hours / planned academic hours of the student's non-cancelled lessons in the teaching period.
  - Excused absences are treated per `attendance.excused_counts_toward_limit`, with unit tests for both values.
  - Effective threshold = min(tenant, published syllabus).
  - Unit test: 45 planned hours, 11 missed = admitted, 12 missed = barred.
- Task 21 (374): the attendance component is computed from the journal by `attendance.points_rule`. It is not typed in the grid; a correction goes only through the existing reasoned, audited change path.
- Task 23 (419): a syllabus attendance threshold above the tenant value is rejected.
- Task 25 (453): add a criterion that publication sets the course threshold and the journal then applies min(tenant, syllabus).

Citations of current code in the documents should use HEAD lines: r_learning.py:40, 63-71, 215 and student.js:333.

## C10. Exam session lifecycle is incomplete: a barred student can start the exam, and there is no attempt dimension for retakes, academic debts or the official grade statement

- Baxış: Tədris şöbəsi · Dərəcə: əsas · Hökm: qismən təsdiqləndi
- Yer: SPEC.md Capability Map row `exam`; tasks/todo.md Task 21, 26, 29, 30; tasks/plan.md Wave 2

**Təkzib cəhdinin nəticəsi (qısaldılıb):**

I tried to refute each of the three parts. The core of all three survives; several of the stated consequences and part of the proposed fix do not.

WHAT STANDS

(a) Admission is computed and never consumed.
- SPEC.md:66 lists `exam` dependencies as `learning`, `identity`, `facilities`. `journal` owns "imtahana buraxılış" (SPEC.md:63).
- This row contradicts the other two documents: todo.md Task 26 has "Dependencies: Task 13, Task 21", and plan.md:51 puts `journal → exam` on the critical path, wh …

**Tətbiq olunan düzəliş:**

1. SPEC.md:66, `exam` row, "Asılıdır": change to `learning`, `identity`, `facilities`, `journal`. In the plan.md:39-49 graph, draw `journal ── exam`. This matches Task 26's dependencies and the critical path.

2. todo.md Task 26, description: add `exams.kind` (əsas | təkrar | fərdi vaxt) and `exam_roster(exam_id, student_id, status, səbəb)`, snapshotted when the exam opens from enrollment plus the admission status in `journal/service.py`.
   Add acceptance criterion: "Siyahıda olmayan tələbə (fənnə yazılmayıb və ya jurnalda «imtahana buraxılmır») cəhd başlada bilmir: 403, tərcümə olunmuş səbəb, hadisə imtahan jurnalında. `dean_office` səbəb yazmaqla istisna əlavə edir; istisna auditdədir."
   Task 29: "siyahı statusu" reads this roster.
   Leave "iki dəfə başlatma eyni cəhdi qaytarır" unchanged.

3. todo.md Task 30, three additions:
   - Scaling: "Xam bal imtahan komponentinin maksimumuna `exam/domain.py`-də çevrilir; yuvarlaqlaşdırma qaydası bir yerdədir; vahid test 16,9 (keçmir) və 17,0 (keçir)."
   - Result write: the score goes through `journal/service.py` with `exam_id` and `attempt_no` (columns in migration 0006, Task 21). A released result from an earlier exam is kept, never overwritten. Result status: keçdi | imtahan < minimum | cəm < keçid | buraxılmayıb | gəlməyib.
     Criterion: "Təkrar imtahanın nəticəsi ilk nəticəni silmir; hər iki cəhd müəllimə və dekanlığa görünür."
   - Statement: after release, a per-group "imtahan-qiymət cədvəli" is generated as a new document kind in the existing QR document infrastructure, and `dean_office` closes it.
     Criterion: "Bağlanmış cədvəldən sonra imtahan balını yalnız `dean_office` dəyişir: səbəb və apellyasiya müraciətinin (`grade_appeal`) və ya əmrin nömrəsi ilə; dəyişiklik qiymət jurnalındadır."

4. todo.md Task 21, one criterion instead of a debts module: "Dekanlıq nəticəsi «keçdi» olmayan tələbə × fənn siyahısını (akademik borclar) görür və CSV ixrac edir."

5. todo.md Task 15, one sentence: `courses` is the per-term offering, so a repeat in a later term is a new row.

6. SPEC.md Out of Scope, add: "Fənnin təkrar dinlənməsi üçün yenidən qeydiyyat, yay semestri və ödənişli təkrar: V1-də köhnə sistemdə."
   SPEC.md Open Questions, add item 11: "Təkrar imtahan qaydası: neçə dəfə, nə vaxt, imtahanaqədərki bal saxlanırmı; imtahan-qiymət cədvəlini kim imzalayır."

7. Fallback if the result-write and statement parts of point 3 are cut for time: add "Təkrar imtahan, akademik borc siyahısı və imzalı imtahan-qiymət cədvəli" to SPEC Out of Scope. Then change the plan.md:165 Wave 2 "Köhnə sistem" cell from "İmtahan nəticələrinin ehtiyat nüsxəsi" to "Rəsmi nəticə, təkrar imtahan və akademik borc köhnə sistemdə qalır; Zəka nəticəni ixrac edir". The admission gate in point 2 is not cut in either case.

Do not add the reviewer's `course_results(pre_exam, exam, total, letter)` table. Task 21 already computes those values.

## C11. No student status changes by order (academic leave, expulsion, transfer, reinstatement) and no task builds the promised "Tələbə-məzun" export

- Baxış: Tədris şöbəsi · Dərəcə: əsas · Hökm: qismən təsdiqləndi
- Yer: tasks/todo.md Task 15, Task 37; SPEC.md Out of Scope (line 261); tasks/plan.md Waves 1 and 3

**Təkzib cəhdinin nəticəsi (qısaldılıb):**

I tried to refute it on four grounds. The core survives; three sub-claims and one part of the proposed fix do not.

**What stands (not refuted)**
- No order-based status change exists in the three documents. A search of SPEC.md, tasks/plan.md and tasks/todo.md for order number, order date, effective date, leave, expulsion, transfer, reinstatement returns nothing. "əmr" appears only as "command" (SPEC.md:96), "bərpa" only as backup restore or recovery codes.
- The only lifecycle operations are `u …

**Tətbiq olunan düzəliş:**

Keep the core of the fix, drop the 5.4.7 claim, and correct the wave condition. Five edits.

**1. tasks/todo.md, Task 15, slice 2 (Description, one acceptance criterion, Files)**
- Add table `student_status_events(id, student_id, kind, order_no, order_date, effective_date, from_group_id, to_group_id, note, entered_by, created_at, reported_at)` in `0004_directory.sql`.
- `kind` uses English codes: `admission | group_change | transfer_in | transfer_out | academic_leave | expulsion | reinstatement | graduation`.
- The table is append-only; a correction is a new event with a reason (consistent with "silmə yoxdur").
- `enrollments` gains `begin_date` and `end_date` (OneRoster `beginDate`/`endDate`, so Task 16 import and the Task 37 round trip carry them).
- Academic status is derived from the latest event and is separate from the account `users.status` of Task 10.
- In legacy `r_services` and `docs.leave_body`: `issue` on `academic_leave` requires `order_no` and `order_date`, writes the event, and the extract prints that number and date instead of the issue date.
- New acceptance criterion: "Əmr nömrəsi, əmr tarixi və qüvvəyə minmə tarixi olmadan status dəyişmir; akademik məzuniyyət və xaric qüvvəyə minmə tarixindən sonrakı dərs siyahılarından tələbəni çıxarır, əvvəlki davamiyyət və ballar qalır; məzuniyyətdəki tələbə hesabına girir və öz sənədlərini görür."
- Owner decision: whether `dean_office` (own faculty scope) enters events, or only `academic_office`.

**2. tasks/todo.md, Task 20 (one acceptance criterion)**
- "Buraxılmış saat faizi yalnız qeydiyyatın `begin_date`–`end_date` aralığındakı dərslərdən hesablanır."

**3. tasks/todo.md, Task 37 (name the target; no new mechanism)**
- In "İxraclar" add: "'Tələbə-məzun' operatoru üçün dəyişiklik siyahısı: verilən tarixdən bəri `student_status_events`, 10 günlük müddətə qalan gün, 'daxil edildi' işarəsi (`reported_at`)."
- Add one acceptance criterion for it.
- Mark the 10-day anchor (order date) as an assumption to check against Decree 225.

**4. SPEC.md**
- Line 261: "V1-də fayl ixracı" becomes "V1-də fayl ixracı (T37: reyestr ixracı və 'Tələbə-məzun' dəyişiklik siyahısı)".
- Success Criteria, `directory` row: add the criterion from edit 1.
- Do not touch Task 39 for 5.4.7; that indicator is TMİS.

**5. tasks/plan.md, wave table (replaces the proposed "exists in both systems" condition)**
- Wave 0 "Bağlanma şərti": add "paralel dövrdə köhnə sistemdə verilən hər status əmri təkrar idxaldan sonra Zəka-dadır".
- Wave 1 "Köhnə sistem": the switch to "Yalnız oxunur" happens only after at least one real order has been entered in Zəka and the operator has used the change list.

**Alternative, if the owner defers edit 1 from the sprint**
- Wave 1 cell reads "kontingent əmrləri dalğa 3-ə qədər köhnə sistemdə yazılır".
- The same sentence is added to SPEC Out of Scope.
- The build is listed as a Wave 1 precondition.

## C12. No curriculum, individual study plan, course registration or credit accounting, and the transcript is switched to real data before any history exists

- Baxış: Tədris şöbəsi · Dərəcə: əsas · Hökm: qismən təsdiqləndi
- Yer: SPEC.md Capability Map row `directory`; tasks/todo.md Task 15, Task 17, Task 21; tasks/plan.md Waves 2 and 3

**Təkzib cəhdinin nəticəsi (qısaldılıb):**

I tried to refute this and could not refute the core. Two halves stand, the reviewer's primary fix and three sub-claims do not.

CONFIRMED (checked in the files)
1. The omission is real and undocumented. `grep -i kredit SPEC.md tasks/plan.md tasks/todo.md | grep -vi akkredit` returns nothing. Task 15 (todo.md:262-277) creates only `faculties`, `departments`, `specialties`, `academic_terms` and binds `study_groups`/`courses` to them. Task 16 kinds are `orgs|terms|users|courses|classes|enrollments …

**Tətbiq olunan düzəliş:**

Do not add a sprint task. Make five document changes.

1. SPEC.md, Out of Scope (Deferred), new bullet:
"- Tədris planı (ixtisas × qəbul ili × semestr × fənn × kredit × məcburi/seçmə × prerekvizit), fərdi tədris planı, seçmə fənn qeydiyyatı (tyutor və ya dekanlıq təsdiqi), kredit yükü həddi, təkrar fənn və akademik borc: V1-də yoxdur. V1-də qeydiyyat köhnə sistemdən `classes` və `enrollments` idxalı ilə gəlir. Dalğa 3-ün şərtidir (plan.md)."
In the replacement matrix row "KOICA Academic, kabinetlər" append: "tədris planı və fənn qeydiyyatı V1-də əvəz olunmur (Out of Scope)".

2. SPEC.md, Open Questions, new item 11:
"11. 2026/27 yaz semestrinin fənn qeydiyyatı harada aparılır: KOICA Academic-də (sonra ixrac), yoxsa Zəka-da? 348 nömrəli qərarın fərdi tədris planı və kredit həddi (40 kredit: mənbə təsdiqlənməyib) AzTU-da necə tətbiq olunur?"

3. tasks/plan.md, Wave 3 row. Column "Zəka-ya keçən": "Zəka əsas sistemdir; tədris planı və fənn qeydiyyatı modulu (sprintdən sonrakı tapşırıq); tarixi məlumat köçürülür; dövlət sistemlərinə ixrac". Column "Bağlanma şərti", add: "yaz semestrinin qeydiyyatı (qrup × fənn, seçmələr, təkrar fənlər) köhnə sistemdən ixrac, idxal və uzlaşdırma ilə Zəka-dadır; qeydiyyat modulu Zəka-da qəbul olunana qədər köhnə Academic modulu arxivlənmir". Add one Risks row: "Dalğa 3-də qeydiyyat mənbəyi yoxdur | Yüksək | Yaz qeydiyyatı arxivdən əvvəl köhnə sistemdən ixrac olunur; modul Dalğa 3-dən əvvəl ayrıca tapşırıqdır".

4. tasks/todo.md, Task 21. Replace the last sentence of the Description with:
"Tələbənin qiymət səhifəsi real məlumatdan oxuyur. Transkript yalnız dərc olunmuş yekun qiymətlərdən qurulur: orta bal = Σ(yekun bal × kredit) / Σ kredit; "Cəmi kredit" yalnız keçid balını və imtahan minimumunu keçən fənləri sayır; bir tələbə × fənn × semestr üçün bir sətir. `transcript` müraciət növü tələbənin tarixçəsi uzlaşdırılana qədər (`history_reconciled_at`; qəbul semestri Zəka-dakı ilk semestrdən əvvəl olmayan tələbələr üçün avtomatik) bağlıdır və səbəbi göstərir. Şablondan "Ballar sintetikdir (demo)" sətri çıxarılır."
Add acceptance criterion: "Tarixçəsi uzlaşdırılmamış tələbənin transkript müraciəti tərcümə olunmuş səbəblə rədd olunur; uzlaşdırılmış tələbədə kəsilən fənn "Cəmi kredit"ə düşmür və orta bal əl hesabı ilə üst-üstə düşür". Verification: `python -m pytest tests/integration/test_transcript_gate.py -q`. Files likely touched: add `backend/zeka/legacy/docs.py`, `backend/zeka/legacy/r_services.py`.

5. tasks/todo.md, small corrections:
- Task 38 Description, add: "Tarixi yekun qiymətlər `results` idxal növü ilə gəlir (tələbə, fənn, semestr, kredit, bal); uzlaşdırma keçəndə `history_reconciled_at` qoyulur." (Task 16 has no kind for past results today.)
- Task 17: `PREREQ` is per-course data, not a tenant setting. Change "`r_academy.py` (`PREREQ`)" to "`r_academy.py` (`PREREQ` fənnin sahəsinə keçir, Task 23-də sillabusun prerekvizit sahəsi olur)". Do not add the credit cap to Task 17 until a registration write path exists to enforce it.

Rejected from the proposed fix: the new M task in Phase 1 (`curricula`, `curriculum_items`, enrollment generation, elective window, approvals). It is needed before Wave 3, not in the 72 hours, and is larger than M.

## C13. Cutover plan names no system of record; wave closing conditions contradict each other and rollback drops everything written after cutover

- Baxış: İstismar və miqrasiya · Dərəcə: bloklayıcı · Hökm: qismən təsdiqləndi
- Yer: tasks/plan.md "Miqrasiya və kəsid" (wave table lines 163-166; steps 4, 6, 7 at lines 173-176); tasks/todo.md Task 16, Task 38, Task 43

**Təkzib cəhdinin nəticəsi (qısaldılıb):**

Checked: tasks/plan.md:9, 159-176, 188-227; tasks/todo.md Task 15 (264-267), Task 16 (281-286), Task 37 (655), Task 38 (681-690), Task 43 (764-769), Task 44 (780-788), Checkpoint F (798); SPEC.md:15-16, 41, 46, 50, 225, 255, 272-273; docs/research/01-azerbaycan-bazar-ve-qanun.md:13-14; docs/report/zeka-vahid-hesabat.html:526-534; app/store.py:24-36.

WHAT FALLS (the finding is wrong or overstated here)
- Title, "names no system of record": plan.md:163 names it for wave 0 ("Əsas mənbə qalır" = th …

**Tətbiq olunan düzəliş:**

1. tasks/plan.md wave table (163-165).
- Wave 1, "Köhnə sistem": "Paralel iş zamanı yazılır, gecəlik müqayisə; kəsiddən (T1) sonra jurnal, cədvəl və tapşırıq modulları yalnız oxunur".
- Wave 2, "Köhnə sistem": "İmtahan nəticələri ehtiyat kimi köhnə sistemin imtahan moduluna da yazılır (kim yazır: sahibin qərarı); qalan modullar yalnız oxunur".
- Wave 0, "Bağlanma şərti": "T0 ixracına qarşı uzlaşdırma fərqi 0 və ya sətir-sətir izahlı; 300 nəfərlik sınaq imtahanı".
- Wave 1, "Bağlanma şərti": "Mənbə ilə bağlı sətirlərdə 14 ardıcıl gecə fərq 0 və ya izahlı; kəsiddən sonra köhnə sistemdə T1-dən sonra yazı 0; dəstək sorğuları sabitləşib".

2. tasks/plan.md: add a table "Qeydin sahibi" under the wave table (varlıq x dalğa: sahib sistem, kim yazır, sinxron istiqaməti).
- Şəxslər, struktur, fənn, qeydiyyat: köhnə sistem T1-ə qədər (idxal mənbədən Zəka-ya); T1-dən sonra Zəka.
- Cədvəl, otaq: ilk idxaldan Zəka (köhnə sistemdə yoxdur); təkrar idxal yalnız konflikt hesabatı ilə.
- Davamiyyət, cari ballar, dalğa 0: sahibin qərarı. (A) köhnə sistem əsasdır, pilot müəllimlər T1-ə qədər hər ikisinə yazır, fərqdə köhnə sistemin dəyəri qalır (indiki "Əsas mənbə qalır" bunu nəzərdə tutur); (B) T0-dan Zəka, köhnə sistemə daxiletmə dekan əmri ilə dayanır. T1-dən sonra Zəka.
- İmtahan nəticələri: dalğa 2-yə qədər köhnə sistem; dalğa 2-də Zəka, ehtiyat nüsxə köhnə sistemdə.
Add to "Sahibin addımları", Saat 10: "'Qeydin sahibi' cədvəlinin təsdiqi; dalğa 0 üçün A və ya B; dekan əmri | T16, T38, T43".

3. tasks/plan.md steps.
- Step 6: replace "Müəyyən müddət" with "Dalğa 0: T1-ə qədər; dalğa 1: ən azı 14 gecə. Kim harada yazır: 'Qeydin sahibi' cədvəli."
- Step 7: replace the rollback sentence with "Geri qayıtma pəncərəsi: kəsiddən sonra N gün (sahib təyin edir, susmaya görə 14). Pəncərədə: Zəka həmin varlıqlar üçün yalnız oxunur, `manage.py export --kind grades|attendance|oneroster --since T` (Task 37) çıxışı dekanlığa verilir və ya köhnə sistemə idxal olunur, köhnə sistem yazma rejiminə qaytarılır. Pəncərədən sonra yalnız irəli düzəliş." Delete "son backup".

4. tasks/todo.md Task 16.
- Add table `import_links(kind, source_system, source_id, row_id, source_hash, imported_at)`, unique on (kind, source_system, source_id); `--source <ad>` is required. One table, not columns in eight tables.
- Rule: a row whose source-mapped fields were changed in Zəka after `imported_at` and differ from the file is written to a conflict report and not overwritten; `--prefer source` forces it and is audited.
- New acceptance criterion: "Zəka-da dəyişdirilmiş sətir təkrar idxalda üstünə yazılmır, konflikt hesabatında sətir nömrəsi ilə görünür".
- Do not disable Task 15 editing for legacy rows.

5. tasks/todo.md Task 37: add an attendance CSV to the exports and a `--since <ISO vaxt>` filter on grades and attendance, exposed as `manage.py export`. No second export path elsewhere.

6. tasks/todo.md Task 38.
- Add import kinds `attendance|grades` (the pre-T0 opening balance, or the parallel comparison under option A), loaded through the Task 16 service.
- `reconcile` compares only rows present in `import_links` for the given source and writes the export instant and each source file's SHA-256 into the report.
- New acceptance criterion: "Zəka-da yaradılan sətir fərq sayılmır; hesabatda ixrac anı və fayl SHA-256-ları var".

7. tasks/todo.md Task 43, Task 44, Checkpoint F.
- Task 43: the "dalğa üzrə kəsid siyahısı" runbook includes the reverse path; add criterion "Geri qayıtma ixracı sınaq serverində bir dəfə icra olunub, müddəti ölçülüb".
- Task 44 and Checkpoint F (also plan.md:142): "uzlaşdırma fərqi 0" becomes "T0 ixracına qarşı uzlaşdırma fərqi 0 və ya izahlı; T0 release runbook-da yazılıb".

8. SPEC.md Open Questions 2: append "Köhnə sistem idxal qəbul edirmi, modul-modul yalnız oxunan rejimə keçirilə bilirmi, bunu kim edir; gecəlik ixracı kim verir?"

## C14. Mid-semester journal cutover has no import path for attendance and grades already recorded

- Baxış: İstismar və miqrasiya · Dərəcə: bloklayıcı · Hökm: təsdiqləndi
- Yer: tasks/todo.md Task 16 (line 281), Task 19, Task 20, Task 21 (line 374), Task 38 (line 681); tasks/plan.md waves 0, 2, 3 (lines 163-166); SPEC.md Assumption 10

**Təkzib cəhdinin nəticəsi (qısaldılıb):**

I tried four refutations; none holds. The core claim stands, but two details of the finding and the placement of its fix are wrong.

WHAT I CHECKED (all quotes verified)
- tasks/todo.md:281 Task 16 kinds are exactly `orgs|terms|users|courses|classes|enrollments|rooms|timetable`. A search of todo.md for idxal/import/köçür/tarixi/legacy finds no task that loads lessons, attendance or grades.
- tasks/todo.md:681 Task 38: "çevirmələr (ad normallaşdırma, qrup kodu, qiymət şkalası). Yükləmə Task 16-da …

**Tətbiq olunan düzəliş:**

Put the journal loaders in Task 38, not Task 16.

1. tasks/todo.md Task 38, Description (line 681). Replace "Yükləmə Task 16-dakı idxal servisindən keçir." with:
"Yükləmə Task 16-dakı idxal servisindən keçir (quru sınaq, ya tam ya heç, idempotentlik). Bu tapşırıq ona iki növ əlavə edir: `--kind attendance|grades`. `attendance` iki forma qəbul edir: (a) dərs səviyyəsi: fənn `sourcedId`, tələbə `sourcedId`, tarix, başlama saatı, status; dərs tapılmasa həmin açarla yaradılır; (b) köhnə sistem yalnız yekun verirsə açılış qalığı: tələbə × fənn üzrə kəsid tarixinə qədər üzrsüz və üzrlü qayıb saatı. `grades`: tələbə × fənn × komponent × bal × maksimum. Hər sətir `source='legacy'` və kəsid tarixi daşıyır; qiymət jurnalında müəllif `migration`, səbəb idxal faylının adı və SHA-256-sıdır."
Add `backend/zeka/modules/migration/loaders.py` to Files likely touched. Change scope from M to L.

2. Task 38, Acceptance criteria. Add:
"- [ ] Davamiyyət və qiymət uzlaşdırılır: tələbə × fənn üzrə qayıb saatı cəmi və (tələbə, fənn, komponent, bal) yoxlama cəmi mənbə ilə bərabərdir
- [ ] Pilot fakültənin 50 təsadüfi tələbəsinin qayıb faizi kəsid tarixində köhnə sistemin rəqəmi ilə eynidir; dekanlıq təsdiqləyir"

3. Task 19, Description (line 341). After "Semestr üçün dərslər yaradılır, bayram günləri buraxılır." add:
"Yaradılma (fənn, tarix, başlama saatı) açarı üzrə idempotentdir. Davam edən semestrdə kəsid tarixindən (tenant ayarı) əvvəlki dərslər yaradılmır; onlar Task 38 idxalından gəlir."

4. Task 20, Acceptance criteria. Add:
"- [ ] Faizə və 'davamiyyət' komponentinə kəsid tarixinə qədərki idxal olunmuş qayıblar (sətir və ya açılış qalığı) daxildir; idxal olunmuş sətri yalnız kafedra müdiri səbəblə dəyişir"

5. tasks/plan.md line 165 (wave 2, "Zəka-ya keçən"). Change "e-xidmətlər" to:
"e-xidmətlər (transkript və keçmiş semestr qiymətinə əsaslanan sənədlər istisna: dalğa 3-də, tarixi qiymətlər köçürüləndən sonra açılır)"
Task 21, Acceptance criteria. Add:
"- [ ] Keçmiş semestrlərin qiyməti idxal olunmayıbsa `transcript` sorğu növü bağlıdır; sintetik `transcript_rows` silinir"

6. SPEC.md Open Question 2 (line 273). Append:
"Cari semestrin davamiyyəti dərs səviyyəsində, yoxsa yalnız yekun kimi ixrac olunur? Cari ballar köhnə sistemdədir, yoxsa müəllimin kağız və ya Excel jurnalında?"
The answer selects form (a) or (b) and decides whether current scores arrive by ETL or by teacher paste (Task 21).
plan.md "Sahibin addımları", row "Saat 6". Append: "o cümlədən pilot fakültənin cari semestr davamiyyəti və cari balları".

Do not add a `lessons` kind. Do not move the kinds into Task 16.

## C15. Backup as specified can fail to complete under writes, stays on the host it protects, and allows a 24-hour loss on exam days

- Baxış: İstismar və miqrasiya · Dərəcə: bloklayıcı · Hökm: qismən təsdiqləndi
- Yer: tasks/todo.md Task 8 (line 139), Task 9 (line 156), Task 4, Task 44 (line 784); SPEC.md Success Criteria `platform` (line 242); tasks/plan.md risk "İmtahan zamanı server düşür"

**Təkzib cəhdinin nəticəsi (qısaldılıb):**

I could not refute the core (a, b, d, e). Three statements in the finding are wrong or already covered, and one part of the fix is over-scoped for the sprint.

CONFIRMED

(a) `.backup` restarts under writes: mechanism is real, but conditional on size x commit rate.
- /home/user/AzTU-Zeka/tasks/todo.md:139 specifies "`sqlite3 .backup` ilə ardıcıl nüsxə". The CLI loops over 100-page steps; a commit from another connection restarts the copy.
- I re-ran it myself (SQLite 3.53.1, `Connection.backup(p …

**Tətbiq olunan düzəliş:**

Minimal edits. Insert texts are in Azerbaijani, as the documents are.

1. tasks/todo.md Task 8, description (line 139). Replace "`sqlite3 .backup` ilə ardıcıl nüsxə, yükləmələrin arxivi" with:
"`backend/manage.py backup`: `sqlite3.Connection.backup()` tək addımda (və ya `VACUUM INTO`) ardıcıl nüsxə; `sqlite3` CLI istifadə olunmur (100 səhifəlik addımlar başqa bağlantının hər commit-ində nüsxəni yenidən başladır). Yükləmələrdən yalnız əvvəlki dəstlərdə olmayan fayllar (məzmun ünvanlıdır)".
After the manifest add:
"Sonra dəst `BACKUP_REMOTE`-a (ölkə daxilində ikinci host) göndərilir və manifest orada yoxlanır; prod rejimində `BACKUP_REMOTE` boşdursa və ya göndərmə alınmırsa skript xəta ilə bitir."
Add `backend/manage.py` to Files.

2. Task 8, new acceptance criteria:
- "Başqa proses hər 20 ms-dən bir commit edərkən backup boş bazadakı müddətin 3 mislindən tez bitir; bərpada `integrity_check` keçir"
- "Göndərmə uğursuz olanda skript sıfırdan fərqli kodla bitir; uzaq tərəfdə manifest yoxlanır"

3. Task 4 (line 77): "Hər miqrasiyadan əvvəl bazanın nüsxəsi yaradılır; son 5 nüsxə saxlanır".

4. Task 9 (line 156): add "hər servis üçün log həddi (`logging: max-size 50m, max-file 5`)". New acceptance: "`docker inspect` hər konteyner üçün log həddini göstərir".

5. Task 43:
- Backup runbook: "açarın iki nüsxəsi serverdən kənarda saxlanır (sahib və AzTU İT)".
- Exam-day runbook: "imtahan bağlananda `manage.py backup` işlədilir".
- Line 772: "başqa adam yalnız runbook və açarın kənar nüsxəsi ilə bərpanı icra edir".

6. Task 44:
- Line 784: "Uzlaşdırma fərqi 0; cədvəl üzrə avtomatik göndərilmiş backup ikinci maşında, açarın kənar nüsxəsi ilə bərpa olunub".
- New acceptance: "Backup yaşı > 26 saat, boş disk < 20% və göndərmə xətası üçün adı yazılmış alıcıya xəbərdarlıq qurulub; hər biri sınaqda bir dəfə işə salınıb".

7. SPEC.md line 242. Replace "Gecəlik şifrəli backup; bərpa sınağı CI-da keçir." with:
"Gecəlik şifrəli backup yazı yükü altında tamamlanır və ölkə daxilində ikinci hosta göndərilir; RPO 24 saat, imtahan günü imtahan bağlananda əlavə backup; bərpa sınağı CI-da keçir, bərpa müddəti ölçülüb."

8. tasks/plan.md:
- Risks, new row: "Server və ya disk itir | Yüksək | Hər backup ikinci hosta gedir; açar serverdən kənardadır; bərpa müddəti ölçülüb (T43); RPO 24 saat, imtahan günü imtahan bağlananda."
- Sahibin addımları, hour 0: "Backup üçün ölkə daxilində ikinci host və açarın saxlanma yeri | T08, T44".
- Wave 2, decision before it starts: "İmtahan günü RPO: bağlananda backup kifayətdir, yoxsa imtahan zamanı dövri backup (bu halda T42 imtahan yük testi backup işləyərkən p95 < 500 ms verməlidir)".

Not adopted from the proposed fix:
- The 15-minute exam cadence and "RPO ≤ 15 dəq" as sprint criteria (moved to the wave-2 decision above).
- The key rotation step.
- "RTO ölçülüb" (already Task 43, todo.md:768).

## C16. Long work shares the two handler slots and SQLite's single write lock: one import stalls every writer

- Baxış: İstismar və miqrasiya · Dərəcə: əsas · Hökm: qismən təsdiqləndi
- Yer: SPEC.md Tech Stack "Paralellik" (line 91); tasks/plan.md A5; tasks/todo.md Task 6 (lines 106-111), Task 16 (line 281), Task 36 (line 639), Task 38

**Təkzib cəhdinin nəticəsi (qısaldılıb):**

Headline refuted by measurement; three small parts stand. Severity should drop from major to minor.

REFUTED

1. "Task 16 means one write transaction of up to 60 s." The 60 s (/home/user/AzTU-Zeka/tasks/todo.md:284, SPEC.md:244) is a wall-clock acceptance ceiling, not a lock hold. The reviewer's lock.py holds the lock with `time.sleep(hold)` between INSERT and commit; it never measures an import. I re-ran it: 4.5-4.8 s wait at 5 s, "database is locked" at 15.0 s at 20 s. True for SQLite, but say …

**Tətbiq olunan düzəliş:**

Keep "Fayl ya tam idxal olunur, ya heç", single-transaction import, SO_REUSEPORT and Task 36's place in Phase 4. Add only these lines.

1. tasks/todo.md Task 16, new acceptance line:
"- [ ] Doğrulama yazma tranzaksiyasından əvvəl bitir; yazma tək `BEGIN IMMEDIATE` tranzaksiyasıdır və kilid müddəti idxal hesabatında çıxır: 10 000 sətirdə ≤ 1 s. Admin ekranı ≤ 20 000 sətir qəbul edir; böyük fayl yalnız `manage.py` ilə"

2. tasks/todo.md Task 38, new acceptance line:
"- [ ] Yazan idxal hər hansı imtahan `gedir` statusunda olanda başlamır (`--force` yalnız audit qeydi ilə); 200 000 sətirdən böyük yükləmə fayllara bölünür, hər fayl ayrıca atomardır"
Task 43, wave runbook: one line that write imports run outside lesson hours.

3. tasks/todo.md Task 6, description: add
"Xaricə şəbəkə çağırışı edən marşrut (`slow=True`: LLM, OIDC) əsas 2 slotu tutmur, ayrıca hədli semaforda gedir (`ZEKA_SLOW`, susmaya görə 4); hər xarici çağırışın açıq vaxt aşımı var (≤ 15 s)."
New acceptance line:
"- [ ] 4 paralel 10 saniyəlik `slow` handler gedərkən oxu və yazma sorğuları: 5xx = 0, p95 ≤ 500 ms"
Mirror in plan.md A5 and SPEC.md:91: "xarici çağırışlar ayrıca həddə".

4. tasks/todo.md Task 7, new acceptance line:
"- [ ] Limit sayğacı öz qısa tranzaksiyasında yazılır və dərhal commit olunur; test rejimində ilk yazmadan commit-ə qədər 200 ms-dən uzun sorğu tranzaksiyası testi yıxır (idxal istisna)"

5. tasks/todo.md Task 10, description: replace "parametrlər sətirdə saxlanır" with
"parametrlər sabitdir və sətirdə saxlanır: n=2^15, r=8, p=1, `maxmem` açıq verilir (stdlib-in susmaya görə həddi bu parametri rədd edir); n=2^17 sahibin qərarı ilə (ölçülüb: 323 ms və 128 MiB hər hash). Hash açıq yazma tranzaksiyası olmadan hesablanır."
Task 42, description: "İmtahan ssenarisi 60 saniyə ərzində 500 girişlə başlayır."

6. tasks/todo.md Task 36, description: replace "icarə müddətli tək işçi dövrü nəzarətçi prosesdə" with
"icarə müddətli tək işçi dövrü nəzarətçinin başlatdığı və yenidən başlatdığı ayrıca uşaq prosesdə; `smtplib.SMTP(timeout=10)`"
New acceptance line:
"- [ ] Bağlantını qəbul edib cavab verməyən saxta SMTP: cəhd 15 saniyədə uğursuz sayılır, növbədəki digər işlər davam edir, öldürülən web işçisi yenə 2 saniyəyə bərpa olunur"
Task 37: webhook `urlopen(timeout=10)`.

7. tasks/todo.md Task 42: give "məşğul baza" a pass criterion:
"- [ ] Məşğul baza: 2 saniyə saxlanan yazma kilidi zamanı 5xx = 0, itən cavab 0"

Do not add: staging table, 500-row batches, revert by run id, core/jobs.py in Phase 0, per-worker ports with `lb_policy least_conn`, or the "10 saniyəlik yazma tranzaksiyası gedərkən p95 ≤ 500 ms" criterion.

## C17. Throughput claim was measured on the 147-user demo database, read-only, in one process; no load test uses real-size data or the target server

- Baxış: İstismar və miqrasiya · Dərəcə: əsas · Hökm: təsdiqləndi
- Yer: SPEC.md Tech Stack lines 91-92 and Success Criteria `platform` (line 242); tasks/plan.md A5, A7, risk "SQLite bir fakültədən artıq yükü çəkmir"; tasks/todo.md Task 6 (lines 109-111), Task 7, Task 42, Task 44, Checkpoint F

**Təkzib cəhdinin nəticəsi (qısaldılıb):**

I tried to refute this on four grounds (already handled elsewhere, misreading, wrong numbers, not relevant inside the sprint) and could not. I reproduced the baseline and re-ran it on real-size data: the finding holds and is understated.

**1. Provenance of the figure: confirmed.**
- The measurement script is `/tmp/claude-0/-home-user-AzTU-Zeka/24f86abd-a307-5440-b233-35fa8609f137/scratchpad/load/probe.py`. It logs in once as the demo student and all N clients reuse that single token against `GE …

**Tətbiq olunan düzəliş:**

Thirteen one-line edits across the three documents. The 60% threshold in edit 6 is mine, derived from the measurements above (171 vs 241 req/s with indexes only, 62 without); the owner may adjust it.

**SPEC.md**

1. Line 91, "Əsas" cell: "Ölçülüb (demo baza: 147 istifadəçi; yalnız `GET /api/student/home`, bir sessiya; tək proses): 47 → 226 sorğu/san, 300 müştəridə 0 xəta. Qapının müqayisəsidir, tutum ölçüsü deyil."
   - Add the same qualifier "(demo baza, tək marşrut)" to plan.md A5.
2. Line 92, "Əsas" cell: replace "Bir fakültə üçün kifayətdir" with "Bir fakültə üçün fərziyyədir; `faculty` və `university` dəstlərində yük testi (T07, T42, T44) təsdiqləyir".
3. Line 242, last sentence: "Demo bazada qapının reqressiya yoxlaması: 300 paralel müştəridə 0 xəta, tək prosesdə ≥ 200 sorğu/san. Tutum: `university` dəstində, hədəf serverdə gündəlik qarışıq 1 000 istifadəçi p95 < 500 ms, 5xx 0."
   - Line 202 and line 249: add "(`university` dəsti; buraxılışda hədəf serverdə)".
   - Line 262: replace "ölçmə tələb edəndə" with "`university` yük testi hədəf serverdə p95 < 500 ms-i tutmayanda".

**tasks/todo.md**

4. Task 6, Description: after "`tools/loadtest.py` yazılır" add: "`--dataset demo|faculty|university` müvəqqəti bazada sintetik dəst yaradır (faculty: 2 000 tələbə, 12 000 qeydiyyat, 1 200 cədvəl sətri, 20 000 cəhd, 20 000 hissə; university: 10 000 / 60 000 / 6 000 / 100 000 / 100 000); hər ssenarinin marşrut qarışığı və düşünmə fasiləsi faylın başında yazılır."
   - Line 109: append "(demo baza; qapının reqressiya yoxlaması)".
5. Task 6, line 111: replace "öldürülən proses 2 saniyəyə bərpa olunur" with "öldürülən proses demo bazada 2 saniyəyə bərpa olunur; işçi dinləmə yuvasını yalnız indeksi qurandan sonra açır və bu müddətdə qalan proseslər xətasız cavab verir".
6. Task 7, Description: replace "`index_version` ayarı dəyişəndə növbəti sorğuda yenilənir" with "`index_version` dəyişəndə proses yalnız dəyişən sənədləri (əlavə, yenilənmə, silinmə) tətbiq edir; tam qurma yalnız proses başlayanda olur". Then add: "`0002`-də isti yol indeksləri: `attempts(user_id, quiz_id)`, `timetable(course_id)`, `enrollments(course_id)`, `quizzes(course_id)`, `materials(course_id)`, `lessons(course_id)`; `student_home` cədvəli tələbənin fənləri üzrə JOIN ilə oxuyur." Add three acceptance criteria:
   - "`university` dəstində oxu ssenarisinin marşrutlarının icra etdiyi heç bir sorğunun `EXPLAIN QUERY PLAN`-ında 1 000 sətirdən böyük cədvəl üzrə `SCAN` yoxdur (`tests/load/test_query_plans.py`; T42 qarışıq və imtahan ssenarilərini əlavə edir)"
   - "`faculty` dəstində tək prosesin oxu ssenarisi demo nəticəsinin ≥ 60%-ni verir və 300 paralel müştəridə 0 xəta; `university` nəticəsi `docs/perf/baseline.md`-də yazılıb"
   - "`university` dəstində (100 000 hissə) material yükləndikdən sonra digər prosesin növbəti axtarışı ≤ 200 ms gecikir (tam yenidənqurma yoxdur); işçinin başlanğıc müddəti və proses başına indeks yaddaşı ölçülüb və eyni faylda yazılıb"
   - Files: add `tools/loadtest.py`, `tests/load/test_query_plans.py`, `docs/perf/baseline.md`, `backend/zeka/legacy/r_learning.py`. Scope M → L (two commits).
7. Checkpoint A (todo.md:175 and plan.md:72): "300 paralel müştəridə 0 xəta (`demo` və `faculty` dəstləri)".
8. Task 42, Description: after "gündəlik qarışıq 1 000 istifadəçi" add "hər ikisi `--dataset university` ilə; maşının nüvə sayı, yaddaşı və işçi sayı nəticə faylında".
   - Acceptance line 751: "İmtahan yükü və gündəlik qarışıq 1 000 istifadəçi: p95 < 500 ms, itən cavab 0, 5xx 0 (`university` dəsti)".
   - Verification: add `--dataset university` to the exam command, and add `python tools/loadtest.py --scenario mixed --users 1000 --dataset university --seconds 600`.
9. Task 44: new acceptance criterion: "Hədəf serverdə, canlı məlumat idxal olunmazdan əvvəl, ayrıca müvəqqəti bazada `loadtest --scenario mixed --users 1000 --dataset university --seconds 300` və `--scenario exam --users 500 --dataset university --seconds 300`: p95 < 500 ms, itki 0; nəticə `docs/perf/target.md`-də, müvəqqəti baza silinib". Add both commands to Verification.
10. Checkpoint F (todo.md:798 and plan.md:142): "Hədəf serverdə bərpa sınağı və `university` yük testi keçib; ...".

**tasks/plan.md**

11. A7, "Yenidən baxma şərti": replace "10 000 tələbə eyni anda: Postgres." with "`university` yük testi (T42, T44) hədəf serverdə p95 < 500 ms-i tutmursa: Postgres tapşırığı dalğa 1-dən əvvəl."
    - A6, "Yenidən baxma şərti": replace "—" with "İşçi başlanğıcı və ya indeks yaddaşı T07-də ölçülən həddi keçərsə: SQLite FTS5."
12. Risk row at line 195, mitigation: replace "A5 ilə ölçülmüş ehtiyat" with "`faculty` və `university` dəstlərində yük testi (T07, T42, T44)".
13. Wave table, dalğa 0 "Bağlanma şərti" (not dalğa 1 as the reviewer proposed): append "; `university` yük testi hədəf serverdə keçib, keçməyibsə Postgres tapşırığı dalğa 1-dən əvvəl planlaşdırılıb".

## C18. Server time: the container runs in UTC while every rule assumes naive Asia/Baku time; no task fixes or tests it

- Baxış: İstismar və miqrasiya · Dərəcə: əsas · Hökm: qismən təsdiqləndi
- Yer: tasks/todo.md Task 9 (line 156), Task 5, Task 12, Task 18, Task 19 (line 346), Task 20, Task 26; CLAUDE.md "Things that will bite you" (line 99)

**Təkzib cəhdinin nəticəsi (qısaldılıb):**

Verdict: the time-zone half stands, and "major" is fair for it. The TOTP/NTP half and several details of the proposed fix do not stand. I could not refute the core.

WHAT I CHECKED TO REFUTE IT

1. Handled elsewhere? No. I searched SPEC.md, tasks/plan.md and tasks/todo.md for TZ, timezone, Asia/Baku, UTC, NTP, chrony, tzdata and "qurşaq". The only hit is tasks/todo.md:346 (iCal `TZID=Asia/Baku`). Decisions A1-A18, Risks, the cut order, Out of Scope and Open Questions say nothing about time. Task …

**Tətbiq olunan düzəliş:**

Minimal changes. Insert texts are in Azerbaijani, as in the documents.

1. tasks/plan.md, Architecture Decisions: new row A19. The owner decides it before Task 10.
"| A19 | Vaxt bir mənbədən gəlir: `core/clock.py`. Proses saat qurşağından asılı deyil; qurşaq `ZEKA_TZ`-dir (susmaya görə `Asia/Baku`). Yeni cədvəllər anı UTC-də, ofsetlə saxlayır (`2026-12-01T06:00:00+00:00`; `Z` yox, Python 3.10 onu oxumur). Divar saatı qaydaları (bugün, həftə günü, `HH:MM`, insanın daxil etdiyi pəncərə və son tarix) `clock.local()` ilə hesablanır. Legacy sütunlar Asia/Baku lokal qalır və bu, `0001_baseline.sql`-də yazılır. Legacy və yeni vaxt sütunu SQL-də müqayisə olunmur. | Konteyner UTC-dədir, qaydalar Bakı vaxtı ilədir (AUDIT R-04, CODEMAP L17). Hash zəncirli hadisə sonradan düzəldilə bilmir. | Yay vaxtı olan qurşaqda tenant və ya Postgres mərhələsi: legacy sütunlar da çevrilir. |"
Cheaper variant, if the owner wants one convention in V1: every column stays Asia/Baku local behind the same clock, and only immutable records (exam_events, grade journal, audit) write the offset. It is correct for a fixed +04:00 zone. Whichever is chosen must be written in A19.

2. tasks/todo.md, Task 5.
- Description, add: "`core/clock.py`: `now()` (UTC, ofsetli) və `local()` (`ZEKA_TZ`). `store.now()` `clock.local()`-dan oxuyur; legacy davranışı dəyişmir. Prod rejimində qurşaq tapılmasa server açılmır. Demo rejimində tz bazası yoxdursa (Windows) OS vaxtı işlənir. `ruff` `DTZ005` və `DTZ011` açılır: `clock.py`-dən kənarda `datetime.now()` və `date.today()` lint xətasıdır."
- Acceptance, add: "- [ ] Proses `TZ=America/Los_Angeles`, `ZEKA_TZ=Asia/Baku`, saat 06:00Z-yə sabitlənib: `/api/student/home` 10:00–11:30 dərsini `now` göstərir (Linux; tz bazası olmayan Windows-da keçilir)".
- Files, add: `backend/zeka/core/clock.py`, `backend/zeka/legacy/store.py`, `tests/integration/test_clock.py`, `pyproject.toml`, `.github/workflows/ci.yml`.
- CI: one ubuntu matrix entry gets `TZ: America/Los_Angeles`. It is useful only together with the test above and the Task 26 test.

3. tasks/todo.md, Task 6: "`/healthz` `server_time` (UTC, ofsetli) və `tz` qaytarır."

4. tasks/todo.md, Task 9.
- Description, add: "`infra/Dockerfile`-də `ENV TZ=Asia/Baku` (log vaxtı və kənar `datetime.now()` üçün ehtiyat); `.env.example`-də `ZEKA_TZ`."
- Acceptance, add: "- [ ] `docker compose -f infra/compose.yml exec app python -c \"import time; print(time.strftime('%z'))\"` `+0400` çap edir; `/healthz`-dəki `server_time` hostun `date -u` çıxışından 2 saniyədən çox fərqlənmir".

5. tasks/todo.md, Task 26, Acceptance, add: "- [ ] Proses UTC-də, `ZEKA_TZ=Asia/Baku`: 10:00–12:00 kimi daxil edilən pəncərə `06:00:00+00:00`-da açılır, `08:00:00+00:00`-da bağlanır".

6. tasks/todo.md, Task 27, Acceptance: replace "ekrandakı taymer server son vaxtını keçmir" with "taymer serverin verdiyi qalan saniyədən sayılır; müştəri saatı 4 saat səhv olanda da server son vaxtı ilə 2 saniyə dəqiqliklə üst-üstə düşür". This closes the client-side form of the same defect (static/js/student.js:230); lab PC clocks are unknown (Open Question 5).

7. tasks/todo.md, Task 43, Description, add to the deploy and exam-day runbooks: "host saatı sinxrondur: `timedatectl show -p NTPSynchronized --value` → `yes`".

8. CLAUDE.md:99: append "(Task 5: clock; Task 9: container zone)".

Do not apply from the original fix:
- Task 12 and Task 20 as affected tasks.
- The Task 44 clock-offset alert.
- A tenant `timezone` setting in Task 5; it is `ZEKA_TZ` in config, and Task 17 may display it.
- The "Z" suffix.
- `/healthz` under Task 9.

## C19. Dalğa 0 semestrin ortasında keçir, amma indiyə qədərki davamiyyət və balların idxal yolu yoxdur

- Baxış: İcra · Dərəcə: bloklayıcı · Hökm: qismən təsdiqləndi
- Yer: /home/user/AzTU-Zeka/tasks/todo.md Task 16, Task 20, Task 38; /home/user/AzTU-Zeka/tasks/plan.md "Miqrasiya və kəsid" dalğa 0 sətri; /home/user/AzTU-Zeka/SPEC.md Commands

**Təkzib cəhdinin nəticəsi (qısaldılıb):**

Hökm: nüvə təsdiqlənir, təkzib edə bilmədim. İki nəticə şişirdilib, təklif olunan düzəlişin yeri səhvdir.

YOXLANAN FAKTLAR (hamısı düzdür)
- T16 növləri 8-dir: `orgs|terms|users|courses|classes|enrollments|rooms|timetable` (tasks/todo.md:281). `attendance` və `grades` yoxdur.
- T38: "Yükləmə Task 16-dakı idxal servisindən keçir", çevirmələrdə "qiymət şkalası" (todo.md:681). T38-in fayl siyahısında importer yoxdur (todo.md:693). Meyar "hər varlıq üçün bərabər say" deyir, varlıqları saymır (todo. …

**Tətbiq olunan düzəliş:**

Səkkiz dəqiq dəyişiklik. Yeni tapşırıq yoxdur, T20 M ölçüsünün yuxarı həddində qalır.

1. tasks/todo.md Task 16, Description. Növ siyahısı: `orgs|terms|users|courses|classes|enrollments|rooms|timetable|attendance-opening|grades`. Bir cümlə əlavə et: "T16 ümumi mexanizmi və növ reyestrini verir; `rooms` T18-də, `attendance-opening` T20-də, `grades` T21-də icra olunur." T16-nın əhatəsi və ölçüsü dəyişmir.

2. tasks/todo.md Task 20. Description-a: "Açılış qalığı (`attendance-opening` idxal növü): tələbə × fənn × semestr üzrə kəsid tarixinə qədər keçilmiş, buraxılmış və üzrlü saat. İdempotentlik açarı: (semestr sourcedId, fənn sourcedId, tələbə sourcedId); təkrar idxal sətri əvəz edir. İdxal düzəliş pəncərəsindən keçmir, mənbə və fayl adı ilə auditə yazılır. Kəsid tarixindən əvvəlki dərslər jurnalda açılmır." Meyar əlavə et: "Faiz = (açılış buraxılmış + Zəka-da yazılan buraxılmış) / fənnin plan saatı; kəsid tarixindən əvvəl dərsi olan, amma açılış qalığı olmayan fənn 'normal' yox, 'məlumat natamam' göstərir və 'imtahana buraxılmır' statusu avtomatik verilmir." Fayllara `backend/migrations/0006_journal.sql` və `tests/fixtures/attendance_opening.csv` əlavə et.

3. tasks/todo.md Task 21. Description-a: "`grades` idxal növü: tələbə × fənn × komponent × bal. Açar: (fənn sourcedId, tələbə sourcedId, komponent açarı). Sxemdə olmayan komponent səhv sətirdir." Meyar: "İdxal olunan bal qiymət jurnalında mənbə 'idxal' və fayl adı ilə görünür; təkrar idxal 0 dəyişiklik bildirir."

4. tasks/todo.md Task 38. Description-da "varlıq üzrə say" sözündən sonra varlıqları adla yaz: "istifadəçi, fənn, qeydiyyat, cədvəl, davamiyyət açılış qalığı, bal". Əlavə et: "İxrac dərs səviyyəsindədirsə adapter onu tələbə × fənn üzrə cəmləyib açılış qalığına çevirir." İkinci meyarı belə dəyiş: "İdxaldan sonra uzlaşdırma hər varlıq üçün bərabər say, davamiyyət üçün tələbə × fənn üzrə bərabər buraxılmış saat cəmi, bal üçün tələbə × fənn × komponent üzrə bərabər cəm göstərir." Dependencies: "Task 16, Task 20, Task 21".

5. tasks/plan.md, "Miqrasiya və kəsid", dalğa 0 sətri, "Köhnə sistem" xanası: "Hüquqi qeyd qalır. Pilot fakültənin müəllimi kəsid tarixindən davamiyyəti və balı hər iki sistemə yazır; gündəlik fərq hesabatı köhnə sistemin ixracını Zəka ilə müqayisə edir." Bu sahibin qərarıdır: SPEC.md Open Questions 9-a "kəsid tarixi və dalğa 0-da yazı sistemi" sözlərini əlavə et. Sahib tək sistemi seçsə, cümlə ona görə dəyişir, amma boş qalmır.

6. tasks/plan.md, "Sahibin addımları", Saat 6 sətri: "Köhnə sistemlərin siyahısı və ilk ixraclar; cari semestrin davamiyyəti (tələbə × fənn: keçilmiş və buraxılmış saat) və cari balları (tələbə × fənn × komponent) daxil. İxrac yoxdursa dekanlıq Excel şablonunu doldurur."

7. tasks/plan.md, Risks, "ixrac gecikir və ya natamamdır" sətrinin azaltmasına: "Şablon dəstinə `attendance-opening.csv` və `grades.csv` daxildir."

8. SPEC.md:121: `import --kind students --file students.csv --dry-run` → `import --kind users --file users.csv --dry-run`.

Ciddilik: "blocker (72-ci saat)" yox, "yüksək; dalğa 0-ın 'uzlaşdırma fərqi 0' qapısı üçün blocker" kimi qeyd olunsun.

## C20. Checkpoint D saat 52-də keçilə bilmir: SEB kompüterinin çatdığı mühit, imtahan yük ssenarisi və imtahan günü runbook-u ondan sonrakı tapşırıqlardadır

- Baxış: İcra · Dərəcə: bloklayıcı · Hökm: qismən təsdiqləndi
- Yer: /home/user/AzTU-Zeka/tasks/todo.md Task 9, 18, 19, 28, 42, 43, 44, Checkpoint D; /home/user/AzTU-Zeka/tasks/plan.md "Sahibin addımları"

**Təkzib cəhdinin nəticəsi (qısaldılıb):**

Hökm: qismən təsdiq. Başlıqdakı "keçilə bilmir" və "blocker" dərəcəsi düz deyil. Üç dayaqdan ikisi realdır, üçüncüsü (runbook) Checkpoint D-yə aid deyil.

TƏSDİQLƏNƏN

1) İmtahan yük ssenarisi. Checkpoint D saat 52-də "300 simulyasiya olunmuş tələbə ilə sınaq imtahanı: 0 itki, p95 < 500 ms" tələb edir (tasks/todo.md:548, tasks/plan.md:113). Task 6 yalnız oxu ssenarisini ölçür (todo.md:109, 114). `--scenario exam` yalnız Task 42-nin Verification bəndindədir (todo.md:756); Task 42 saat 62–72-dədir …

**Tətbiq olunan düzəliş:**

Dərəcə: blocker → yüksək. Yeni nömrəli tapşırıq əlavə olunmur, runbook köçürülmür. Yeddi dəqiq dəyişiklik:

1) tasks/todo.md Task 27. "Files likely touched"-a `tools/loadtest.py` əlavə et. Meyar əlavə et: "300 simulyasiya olunmuş tələbə imtahanı başladır, cavab yazır və təslim edir: itən cavab 0 (server sayı = müştəri sayı), p95 < 500 ms". Verification-a əlavə et: `python tools/loadtest.py --scenario exam --users 300 --seconds 300`. Fayl sayı 7 olur; ölçünü yenidən yaz.

2) tasks/todo.md Checkpoint D birinci bənd və tasks/plan.md:113. Eyni əmri göstər və "Task 30-dan sonra yenidən işlədilir" yaz (hash zənciri və nəzarətçi sorğusu yükə əlavə olunur). Task 42 dəyişmir: 500 istifadəçi, 1800 saniyə, xaos.

3) tasks/todo.md Task 9. Description-da `infra/.env.example` üçün `ZEKA_PROXY_HOPS=1` və `PUBLIC_URL` yaz. Meyar əlavə et: "Caddy arxasından gələn sorğuda `req.ip` müştərinin ünvanıdır, Caddy-nin deyil; tətbiqin portu host-a açılmır; müştərinin göndərdiyi saxta `X-Forwarded-For` nəzərə alınmır". Verification: compose üzərində test və ya `docker compose -f infra/compose.yml logs app`-da müştəri ünvanı.

4) tasks/plan.md "Sahibin addımları", saat 0 "Hostinq qərarı və server girişi" sətri. Əlavə et: "sınaq nüsxəsi üçün DNS adı; sertifikat üsulu (ACME və ya AzTU-nun verdiyi sertifikat); imtahan auditoriyasının alt şəbəkəsi (CIDR) və oradan serverin 443 portuna çıxış". "Niyə" sütunu: T09, T18, T19, T28, T29, T44.

5) Checkpoint B (tasks/todo.md:312 və tasks/plan.md:85). Bənd əlavə et: "Sınaq nüsxəsi sabit adla açılır: `curl https://<ad>/healthz` (`-k` olmadan) sahibin SEB kompüterindən 200 qaytarır; sintetik məlumatla işləyir; hər yoxlama nöqtəsində push-dan sonra `docs/runbooks/deploy.md` ilə yenilənir. Ad saat 22-yə hazır deyilsə: Task 18, 19, 28-in əl yoxlamaları LAN-da http ilə (`seb://`) aparılır, `sebs://` sınağı və Google Calendar abunəliyi Task 44-ün meyarına yazılır."

6) tasks/todo.md Task 28 Verification, ikinci bənd. "sınaq nüsxəsində `sebs://` keçidi; nüsxə yoxdursa LAN-da `seb://`" yaz ki, sınağın yeri birmənalı olsun.

7) tasks/todo.md Task 43, üçüncü meyar. Belə yaz: "İmtahan günü runbook-u Task 42-nin imtahan yük sınağında və SEB əl sınağının təkrarında istifadə olunub". Dependencies-ə Task 42 əlavə et.

## C21. Paralel zolaqlar asılılıqlarla ziddir; real kritik zəncir 19 ardıcıl tapşırıqdır və kəsmə sırası onu qısaltmır

- Baxış: İcra · Dərəcə: əsas · Hökm: qismən təsdiqləndi
- Yer: /home/user/AzTU-Zeka/tasks/plan.md "Dependency Graph", "Paralel zolaqlar", "Kəsmə sırası"; /home/user/AzTU-Zeka/tasks/todo.md Task 15, 16, 17, 18, 19, 22, 42, 44

**Təkzib cəhdinin nəticəsi (qısaldılıb):**

I could not refute the core of the finding, but two of its conclusions and two parts of its fix do not hold.

CONFIRMED (checked against the files):
1. Critical-path sentence contradicts the dependencies. /home/user/AzTU-Zeka/tasks/plan.md:51-52 says the path is platform → identity → directory → timetable → journal → exam and that `facilities` is off it. /home/user/AzTU-Zeka/tasks/todo.md:352 (Task 19 "Dependencies: Task 18") and :335 (Task 18 "Dependencies: Task 16") put facilities and import o …

**Tətbiq olunan düzəliş:**

Minimal edits, no renumbering (the task count stays 44).

/home/user/AzTU-Zeka/tasks/todo.md
1. Task 19, Dependencies: "Task 18" → "Task 15 (dilim 1), Task 17". Add one sentence to the Description: "Otaq `timetable.room` kodu kimi saxlanır, toqquşma normallaşdırılmış kodla yoxlanır; `rooms` cədvəlinə bağlama Task 18-dədir."
2. Task 18, Dependencies: keep "Task 16" (it reuses the import service) and append "; `timetable.room` bağlama dilimi Task 19 birləşdiriləndən sonra". Do not change it to Task 15.
3. Task 16, Description: remove `rooms` from the `--kind` list. In Task 18, change "CSV idxalı" to "CSV idxalı: Task 16-dakı idxal servisinə `--kind rooms` əlavə olunur".
4. Task 16 and Task 17, Dependencies: "Task 15" → "Task 15 (dilim 1: struktur və semestr)". Task 15 already defines the two slices and two commits, so no 15a/15b split is needed.
5. Task 42, Dependencies: "Task 30, Task 35" → "Task 30; Task 35 (kəsilməyibsə)".

/home/user/AzTU-Zeka/tasks/plan.md
6. Lines 51-52: replace with the chain that follows from todo.md after the edits above: "Kritik yol (todo.md asılılıqlarından ən uzun zəncir, 18 tapşırıq): T02→T03→T04→T05→T10→T11→T13→T15/1→T17→T19→T20→T21→T26→T27→T29→T30→T42→T44. `facilities` (T18, T31), idxal (T16), `syllabus`, `qa`, `community`, `comms` bu zəncirdən kənardır və paralel gedir."
7. "Paralel zolaqlar" table:
   - 10–22: Zolaq 1 "T10, T11, T13, T15/1, T17"; Zolaq 2 "T15/2, T16 (T15/1-dən sonra)"; Zolaq 3 "T12, T14 (T11-dən sonra)".
   - 22–36: Zolaq 1 "T19–T21"; Zolaq 2 "T18, sonra T22 (T21-dən sonra)"; Zolaq 3 "T36".
   - 62–72: remove T44 from Zolaq 3 and add under the table: "T44 zolaq deyil: T38, T41, T42, T43 bitəndən sonra son addımdır."
   - Under the table add: "Zolaq daxilində tapşırıq todo.md-dəki asılılığı bağlananda başlayır."
8. "Kəsmə sırası": keep the six items and add a second list, "Kritik zəncirdə incəltmə (tapşırıq qalır, bənd növbəti versiyaya keçir)", containing only sub-features that are absent from SPEC Success Criteria (SPEC.md:242-255):
   - T30: sual statistikası və oxşar səhv cavab siyahısı.
   - T21: Excel-dən yapışdırma.
   - T19: ləğv və köçürmə bildirişi.
   - T11: "Sessiyalarım" siyahısı.
   Do not list Task 15 slice 2: it is off the chain after edit 4 and carries user deactivation.
9. Risk row at line 199: "Kəsmə sırası aşağıdadır; kritik yol kəsilmir." → "Kəsmə sırası yan işi silir; kritik zəncirdə gecikmə üçün incəltmə siyahısı aşağıdadır."

Do not add a statement that Checkpoint B or C is infeasible; that part of the finding is unproven.

## C22. Sahibdən gəlməli üç giriş "Sahibin addımları"nda yoxdur: NICE faylı (nist.gov bu sessiyadan bağlıdır), marşrut qrafı, parolsuz .seb

- Baxış: İcra · Dərəcə: əsas · Hökm: qismən təsdiqləndi
- Yer: /home/user/AzTU-Zeka/tasks/todo.md Task 24, Task 31, Task 28; /home/user/AzTU-Zeka/tasks/plan.md "Sahibin addımları"

**Təkzib cəhdinin nəticəsi (qısaldılıb):**

Təkzib etməyə çalışdım; üç boşluğun hər biri sənədlərdə realdır və başqa yerdə bağlanmayıb. Amma ağırlıq "major" deyil, nəticələrin üçü də şişirdilib, təklif olunan düzəlişin bir bəndi indi icra oluna bilməz, biri isə yetərsizdir.

1) NICE faylı — TƏSDİQ (ağırlıq orta).
- Özüm yoxladım: `curl -m 15 https://www.nist.gov/` → "curl: (56) CONNECT tunnel failed, response 403". csrc.nist.gov, 1edtech.org və www.imsglobal.org eyni cavabı verir. WebFetch də "www.nist.gov has to be allowed in the session …

**Tətbiq olunan düzəliş:**

Dörd dəyişiklik; hər biri bir-iki sətirdir.

1) tasks/plan.md, "Sahibin addımları" — yeni sətir:
`| Saat 0 (ən geci saat 36) | Sessiya mühitinin şəbəkə icazəsinə `www.nist.gov` və `csrc.nist.gov` əlavə et; mümkün deyilsə NICE Framework Components v2.2.0 JSON faylını dəyişdirmədən `content/frameworks/nice-components-2.2.0.json` kimi ver | T24 |`
Zolaq cədvəlində (plan.md:153, Sahib sütunu) eyni giriş əlavə olunsun.
İstəyə görə: T16-nın sütun adlarını spesifikasiya ilə tutuşdurmaq üçün eyni sətrə `www.imsglobal.org`.

2) tasks/todo.md, Task 24:
- Yeni meyar: "İdxal NIST-in dərc etdiyi dəyişdirilməmiş fayldan aparılır; idxaldan sonra hər növ üzrə (iş rolu, bilik, bacarıq, tapşırıq bəyanatı) sətir sayı fayldakı element sayına bərabərdir."
- Description-a: "Test nümunəsi real fayldan kəsilir. Fayl əlçatan deyilsə tapşırıq bloklanmış qalır; nümunə və ya fayl əl ilə yazılmır."
- Dependencies: "Task 23; sahibin NICE addımı (plan.md, Sahibin addımları)".

3) Marşrut qrafı:
- plan.md:223 → "Otaq siyahısı, korpus girişləri; dalğa 0 korpuslarının mərtəbə planları (PDF və ya şəkil); qraf qaralamasını yoxlayacaq şəxs | T18, T31". plan.md:152-yə "mərtəbə planları" əlavə olunsun.
- todo.md Task 31, Description-a: "Pilot korpus: dalğa 0 cədvəlində ən azı bir dərsi olan korpus; siyahı T18-in otaq bağlama hesabatından çıxır. Düyün və til CSV-sini T31 sahibin verdiyi mərtəbə planlarından qaralayır; sahibin təyin etdiyi şəxs 5 marşrutu yerində yoxlayır."
- todo.md:561 meyarı → "Pilot korpuslarda T18-də idxal olunmuş hər otaq qrafda düyündür; istənilən iki otaq arasında marşrut qayıdır və ya çatışmayan bağlantı yazılır."
- Meyara korpusun adı yazılmır: ilk fakültə (Open Question 9, saat 10) hələ seçilməyib.
- Boş CSV şablonunu T18-ə əlavə etmək yalnız sahib "CSV-ni AzTU əməkdaşı doldurur" variantını seçərsə lazımdır.

4) `.seb`:
- plan.md:225 → "SEB qurulmuş 2 Windows kompüteri; SEB Config Tool-da "Use SEB settings file for: starting an exam" seçimi ilə, parol və sertifikat seçilmədən, şifrələnməmiş saxlanmış bir `.seb` faylı və alətin göstərdiyi Config Key". plan.md:153 eyni sözlə.
- todo.md Task 28, Description-a: "İstinad faylının oxuyucusu xam XML plist və gzip + `plnd` bükümünü qəbul edir; `pswd`, `pwcc` və ya `pkhs` gələrsə səbəbi deyən xəta verir."

Tapıntının ağırlığı "major"dan "minor"a endirilsin.

## C23. Miqrasiya faylları: Task 12 və 24 tətbiq olunmuş faylı dəyişir, Task 4 bunu qadağan edir; 9 tapşırığın sxem dəyişikliyi üçün fayl göstərilməyib

- Baxış: İcra · Dərəcə: əsas · Hökm: təsdiqləndi
- Yer: /home/user/AzTU-Zeka/tasks/todo.md Task 4, 10, 11, 12, 13, 16, 19, 23, 24, 29, 30, 34, 36, 39, 40; /home/user/AzTU-Zeka/SPEC.md Project Structure, Testing Strategy

**Təkzib cəhdinin nəticəsi (qısaldılıb):**

Təkzib etməyə çalışdım, alınmadı. PROBLEM bölməsindəki hər fakt sənəddə və kodda təsdiqlənir. Yalnız nəticə (CONSEQUENCE) şişirdilib və düzəlişin bir bəndi yanlış yerə düşür.

Təsdiqlənən faktlar:
- tasks/todo.md:76 (Task 4): checksum dəyişibsə server açılmır. SPEC.md:216: "yalnız irəli gedən nömrəli miqrasiya". Mühərrik həm də rejimə görə fərq qoymur.
- todo.md:195 (T10) və :227 (T12) eyni `0003_identity.sql`-i göstərir; :427 (T23) və :444 (T24) eyni `0008_syllabus.sql`-i. Asılılıq T12 ← T11 ← …

**Tətbiq olunan düzəliş:**

Dəyişiklik yalnız sənədlərdədir: `tasks/todo.md` və `SPEC.md`.

**1. todo.md, Task 4, Description-a əlavə:**
"Fayl adı `NNNN_ad.sql`, NNNN = tapşırıq nömrəsi × 10 (T12 → `0120_totp.sql`); eyni tapşırığın sonrakı düzəlişi `0121_…`. Birləşdirilmiş (commit olunmuş) miqrasiya faylı redaktə edilmir, hər tapşırıq öz faylını əlavə edir. Mühərrik `schema_migrations`-da olmayan hər faylı nömrə sırası ilə tətbiq edir; nömrələrdə boşluq və kiçik nömrənin gec gəlməsi xəta deyil. Miqrasiya yalnız öz tapşırığının `Dependencies` zəncirindəki cədvəllərə söykənir."

**2. todo.md, Task 4, Acceptance criteria:**
- Sətir 75: "Sxem versiyası 3 olan" → "`PRAGMA user_version = 4` olan (indiki `SCHEMA_VERSION`)".
- Sətir 76: "baza daha yeni versiyadadırsa" → "bazada faylı olmayan versiya qeydi varsa (baza daha yeni koddandır) və ya eyni NNNN ilə iki fayl varsa".
- Yeni meyar: "`0001` və `0030` tətbiq olunmuş bazaya sonradan əlavə olunan `0020` tətbiq olunur (test)."

**3. todo.md, mövcud 13 adın dəyişməsi ("Files likely touched"):**
- T7: `0002_shared_state` → `0070_shared_state`
- T10: `0003_identity` → `0100_identity`
- T12: `0003_identity` → `0120_totp` (ayrıca fayl)
- T15: `0004_directory` → `0150_directory`
- T18: `0005_facilities` → `0180_facilities`
- T21: `0006_journal` → `0210_journal`
- T22: `0007_assignments` → `0220_assignments`
- T23: `0008_syllabus` → `0230_syllabus`
- T24: `0008_syllabus` → `0240_frameworks` (ayrıca fayl)
- T26: `0009_exam` → `0260_exam`
- T32: `0010_kb` → `0320_kb`
- T33: `0011_qa` → `0330_qa`
- T35: `0012_community` → `0365_community` (T35 T36-dan asılıdır; boş bazada ondan sonra işləməlidir)
- T36: `0013_comms` → `0360_comms`
- T37: `0014_integration` → `0370_integration`

**4. todo.md, fayl siyahısına miqrasiya əlavə olunan tapşırıqlar:**
- T11: `backend/migrations/0110_sessions.sql`
- T13: `0130_role_grants.sql`
- T16: `0160_import.sql` (`sourcedId` sütunları, aktivləşdirmə kodları)
- T19: `0190_timetable.sql` (həftə nümunəsi, iCal tokeni)
- T29: `0290_proctor.sql` (nəzarətçi təyinatı və `exam_events`, `prev_hash` və `hash` sütunları ilə) və `modules/exam/repo.py`
- T31: `0310_routes.sql` (marşrut qrafının düyün və til cədvəlləri) və `modules/facilities/repo.py`
- T34: `0340_office_hours.sql`
- T39: `0390_events.sql`
- T40: `0400_privacy.sql`

**5. todo.md, Task 30, Description:**
"`exam_events` yalnız əlavə olunur" → "`exam_events` (T29-da yaradılıb) yalnız əlavə olunur". T30-a miqrasiya lazım deyil.

**6. SPEC.md:**
- Sətir 140: "0001_baseline.sql, 0002_identity.sql, ..." → "0001_baseline.sql, 0070_shared_state.sql, 0100_identity.sql, ... (NNNN = tapşırıq nömrəsi × 10)".
- Sətir 200: "v3 demo bazasından" → "v4 demo bazasından".
- Sətir 216-ya əlavə: "birləşdirilmiş miqrasiya faylı redaktə edilmir".

## C24. Rol adları üç sənəddə fərqlidir: `office` itib, `moderator` təyin olunmayıb, klub rəhbərinin rol id-si yoxdur

- Baxış: İcra · Dərəcə: əsas · Hökm: qismən təsdiqləndi
- Yer: /home/user/AzTU-Zeka/SPEC.md Objective, Testing Strategy, Success Criteria (`qa`, `community`); /home/user/AzTU-Zeka/tasks/todo.md Task 13, 33, 35, 42

**Təkzib cəhdinin nəticəsi (qısaldılıb):**

Tapıntının üç hissəsini təkzib edə bilmədim, iki hissəsi isə dayanmır. Ciddilik "major" yox, ortadır: düzəliş bir cədvəl və dörd sətirdir, amma kritik yoldakı Task 13-ə düşür.

**Təsdiqlənən hissələr**

1. `office` üçün keçid qaydası yoxdur.
   - `tasks/todo.md:232` səkkiz rol verir, aralarında `office` yoxdur, `dean_office` var.
   - Kodda dekanlıq `office`-dir: `app/common.py:18-19`, `app/r_services.py:230, 363, 414, 457`, `app/r_support.py:14-15, 48`, `app/r_radar.py:12-13, 164`, `app/r_core. …

**Tətbiq olunan düzəliş:**

Dörd redaktə və bir sahib qərarı. Ən ucuz yol `office` id-sini saxlamaqdır: A3-ə uyğundur, 698 testə toxunmur, miqrasiya tələb etmir.

**1. `tasks/todo.md` Task 13, Description.** "Rollar: `student`, ... `admin`." cümləsini bu cədvəllə əvəz et:

| İstifadəçi növü (SPEC Objective) | Rol id-si | Qeyd |
|---|---|---|
| tələbə | `student` | kodda var |
| müəllim | `teacher` | kodda var |
| kafedra müdiri | `dept_head` | yeni |
| dekanlıq | `office` | kodda var; id dəyişmir (A3) |
| tədris şöbəsi | `academic_office` | yeni |
| imtahan nəzarətçisi | `proctor` | yeni |
| rəhbərlik (rektorluq) | `leader` | kodda var; klub rəhbəri deyil |
| İT admin | `admin` | kodda var |
| klub rəhbəri | rol deyil | Task 35: klubun `rəhbər` sahəsi, obyekt səviyyəli yoxlama |
| moderator | rol deyil | icazələr: `qa.moderate`, `community.moderate` (`core/perms.py`) |

Cədvəlin altına bir sətir əlavə et:
- "Susmaya görə `qa.moderate`: `office`, `admin`. `community.moderate`: klubun rəhbəri (öz klubunda), `office`, `admin`; klub rəhbərinə qarşı şikayət `office` növbəsinə düşür."

Bu bölgü mənim təklifimdir, sənədlərdə yoxdur. Sahib Checkpoint B-də təsdiqləməlidir, çünki anonim müəllifi kimin görəcəyini müəyyən edir.

**2. `tasks/todo.md` Task 13, Acceptance criteria.** Bir bənd əlavə et:
- "Legacy marşrutlarda mövcud beş rolun (`student`, `teacher`, `office`, `leader`, `admin`) matrisi Task 13-dən əvvəlki ilə eynidir."

**3. Moderator sözünü icazə id-si ilə yaz.**
- `tasks/todo.md:595` və `SPEC.md:251`: "müəllim və moderator görür" → "fənnin müəllimi və `qa.moderate` icazəsi olan görür".
- `tasks/todo.md:627` və `SPEC.md:252`: "moderator növbəsinə düşür" → "`community.moderate` icazəsi olanların növbəsinə düşür".

**4. `SPEC.md:201`.** "5 rol × 3 dil" → "Task 13-dəki hər rol × 3 dil".

**Sahib `dean_office` adını istəsə.** Onda Task 13-ə bunlar yazılmalıdır və ölçü M-dən L-ə keçir:
- Fayllar: `legacy/{common,r_services,r_support,r_radar,r_core}.py`, `frontend/js/{shell,services,support,news,radar,demo}.js`, `tests/conftest.py` və `office` fiksturunu işlədən testlər, `content/seed.json`, `content/guide.json`.
- Demo bazası üçün miqrasiya: `UPDATE users SET role='dean_office' WHERE role='office'`.
- Həcm: 23 Python, 25 JS, təxminən 100 test sətri.

Klub rəhbəri üçün ayrıca rol id-si əlavə etmək lazım deyil.

