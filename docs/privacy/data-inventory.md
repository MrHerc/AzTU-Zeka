# Fərdi məlumatların inventarı (Task 40)

Bu sənəd Zəka platformasında şəxsə aid məlumatı saxlayan hər sütunu göstərir: məqsəd, ixrac, silmə, saxlama müddəti
və hüquqi əsas. "Fərdi məlumatlar haqqında" Qanunun (998-IIIQ) 15-ci maddəsi üzrə informasiya sisteminin dövlət
qeydiyyatı üçün əsasdır.

Mənbə kodda: `backend/zeka/modules/identity/repo.py` → `INVENTORY`, `VIA`, `SELECTS`, `ERASE_FIRST`, `ANONYMISE`.
`tests/integration/test_privacy.py` sxemi oxuyur: şəxsin id-sini saxlayan yeni sütun (`user_id`, `student_id`,
`*_by` və s.) `INVENTORY`-də və bu sənəddə yoxdursa, test düşür.

Hüquqi əsasları və hüquqşünasa ünvanlanmış sualları sahibin 2026-11-21 tapşırığı ilə qərara bağladım: "AI köməkçiləri:
hüquqi əsas" və "Qərarlar" bölmələri. Hər qərarın yanında səbəbi və onu nəyin dəyişə biləcəyi yazılıb. Maddə 15 üzrə
dövlət qeydiyyatı açıq qalır (SPEC, açıq sual 10).

## Qaydalar

**İxrac.** `GET /api/me/export` daxil olmuş şəxsə öz sətirlərini JSON faylı kimi verir. Hər ixrac auditə yazılır
(`privacy_export`). Bir şəxs saatda ən çox beş dəfə ixrac edə bilər, altıncı sorğuya 429 cavabı verilir. İxracın və
silmənin oxuduğu hər şəxs sütununun indeksi var (`0401_privacy_indexes.sql`). Heç vaxt ixraca düşmür:

- sirlər: parol hash-i, TOTP toxumu, bərpa və aktivləşdirmə kodlarının hash-i, təqvim lentinin və sessiyanın hash-i,
  SEB nonce (sütun adına görə süzülür: `password`, `secret`, `nonce`, `verifier`, `*_hash`, `totp_*`);
- `audit.detail` (işçinin qeydində başqa şəxsin nömrəsi olur), `files.path` (diskdəki yer), `exam_events.actor_id`;
- `exam_forms`: imtahan variantı (sualların və variantların sırası) heç vaxt ixrac olunmur;
- açıqlanmamış imtahan balı: `exam_attempts.score` və `max_score` imtahan `released` olana qədər boşdur;
  `exam_answers` və `exam_events` yalnız açıqlanmış imtahan üçün ixraca düşür;
- imtahan sualının mətni, variantları, açarı və izahı: `questions` cədvəli ixrac olunmur; açıqlamadan sonra ixracda
  yalnız tələbənin öz cavabları (`qid`, `value`, `saved_at`) və balı olur;
- dərc olunmamış (qaralama) qiymət: `grades` yalnız `status = 'published'`;
- imtahan protokolu və imtahan-qiymət cədvəli (`exam_protocol`, `exam_statement`): sahibi müəllimdir, amma içində
  bütün tələbələrin balı var; müəllimin ixracına düşmür;
- başqasının sətri: hər sətir şəxsin öz sütunu ilə seçilir; işçinin başqasına etdiyi əməl (`*_by`, `actor_id`,
  `assignee_id`) ixraca düşmür;
- müəllimin göndərilmədiyi AI qaralaması (`teacher_questions.ai_draft`): müəllimin iş məhsuludur, tələbənin məlumatı
  deyil (SA-F7).

**Zəka Radar risk balı ixraca düşür** (sahibin qərarı, 2026-11-21). Dəstək planının `interventions.risk_before`,
`interventions.level_before` və `interventions.drivers` sütunları (plan göndəriləndə tələbənin risk balı, səviyyəsi və
balın səbəbləri) tələbənin öz məlumatıdır və onun ixracında olduğu kimi qalır. Portalın tələbə ekranı balı göstərmir:
bu, pedaqoji seçimdir (tələbə plandakı addımları görür), məlumatı gizlətmək üçün deyil. Ekran və ixrac fərqli işi görür:
ekran öyrənməyə kömək edir, ixrac isə şəxsin öz məlumatına çıxış hüququnu təmin edir.

Şəxsi sütunu olmayan, amma şəxsin öz işinə aid sətirlər (`VIA`): `exam_answers` (açıqlanmış cəhdin cavabları),
`request_events` və `request_messages` (öz müraciətlərinin tarixçəsi), `support_messages` (öz dəstək sorğusuna
cavablar; dəstək xidmətinin daxili qeydləri yox).

**Silmə.** Şəxs profildən silmə sorğusu göndərir (`POST /api/me/erase`). Qərarı `privacy.decide` icazəsi olan rol verir:
**tədris şöbəsi** (`academic_office`, `backend/zeka/core/perms.py`), öz əhatəsində (fakültə qrantı olan yalnız öz
fakültəsinin tələbəsini görür). Administrator qərar vermir. Heç kim öz sorğusu haqqında qərar vermir. Demo girişinin
hesabı silinmir. Təsdiq inventara görə işləyir və auditə yazılır (`privacy_erased`, cədvəl üzrə silinən sətir sayı;
rədd: `privacy_erase_rejected`):

- **sil**: şəxsin bu sütunla bağlı sətirləri silinir; əvvəlcə onlardan asılı sətirlər (`ERASE_FIRST`): öz klub
  mesajlarına şikayətlər, öz forum mövzularının cavabları və şikayətləri, öz dəstək sorğularının mesajları;
- **saxla**: akademik və hüquqi qeyd, ya da başqasının qeydi (şəxs orada icraçıdır); sətir qalır, anonimləşdirilmiş
  hesaba bağlı olur;
- **anonimləşdir** (`users`): ad `#<id>`, istifadəçi adı `erased-<id>`, ata adı, e-poçt, parol, TOTP, seçimlər, razılıq
  vaxtı silinir, status `erased` olur; sessiyalar silinir. Tələbə bileti nömrəsi qalır (dövlət reyestri ilə əlaqə, sahibin
  qərarı). Verilmiş sənədlər (`documents`) olduğu kimi qalır: yükü hash-lənib, `/verify` onu yoxlayır; adı sənəddə qalır.
  `exam_events` yalnız əlavə olunan jurnaldır (triggerlər): ona toxunulmur.

## Hüquqi əsas kodları

| Kod | Əsas |
|---|---|
| Q | Qanunla aparılmalı akademik qeyd (təhsil qanunvericiliyi, kredit sistemi qaydaları); saxlama norması hüquqşünasla təsdiqlənir |
| T | Təhsil prosesinin, e-xidmətin və kampus xidmətinin göstərilməsi (operatorun funksiyası; 9.6-cı maddədəki əsaslardan hansı olduğu hüquqşünasla təsdiqlənir) |
| R | Şəxsin razılığı (8-ci maddə). İstəyə bağlıdır və istənilən vaxt geri götürülə bilər; imtina portalın qalan hissəsinə təsir etmir |
| S | İnformasiya təhlükəsizliyi və hesabatlılıq (giriş, sessiya, audit) |
| İ | İşçinin vəzifəsi üzrə əməli (icraçı sütunu); qeydin əsası qeydin özünün əsasıdır |

## AI köməkçiləri: hüquqi əsas (sahibin qərarı, 2026-11-21)

Sahib tapşırdı: universitet üçün hansı əsasın düzgün olduğunu araşdır və tətbiq et. Qərar belədir: AI tutorun və kampus
köməkçisinin platformadakı emalı **razılıq** (R) əsasında qalır. Razılıq həqiqətən könüllüdür və geri götürülür.
Xarici AI xidmətinə göndərmə ayrıca razılıqdır (`external_ai`, aşağıda "Qərarlar", 4).

Səbəblər:

1. **Qanun.** 998-IIIQ razılığı əsas qayda kimi qoyur (8-ci maddə: yazılı razılıq və ya gücləndirilmiş elektron imzalı
   sənəd; sübut yükü operatorun üzərindədir). Razılıqsız emalın halları 9.6-cı maddədədir
   (`docs/research/01-azerbaycan-bazar-ve-qanun.md`, §3). Davamiyyət, qiymət və e-xidmət operatorun funksiyasıdır (T, Q).
   AI tutor və kampus köməkçisi isə tədrisin məcburi hissəsi deyil. Heç bir qayda tələbəni onlardan istifadəyə məcbur
   etmir: dərsi, materialı, müəllimin cavabını və e-xidməti tələbə onlarsız da alır. Ona görə bu emal təhsil funksiyasına
   deyil, şəxsin seçiminə əsaslanır.
2. **Oxşar təcrübə.** GDPR-də dövlət universitetinin əsas təhsil emalı 6(1)(e) bəndinə ("ictimai vəzifə") əsaslanır,
   istəyə bağlı xidmət isə razılığa. EDPB-nin razılıq haqqında 05/2020 saylı təlimatı (13, 16–21, 114, 117-ci bəndlər)
   razılığın etibarlılığı üçün bu şərtləri qoyur:
   - Qurumla şəxs arasında güc fərqi olduqda razılıq yalnız imtinanın heç bir zərəri olmadıqda etibarlıdır.
   - Razılığı geri götürmək onu vermək qədər asan olmalıdır.
   - Başqa əsas yoxdursa, razılıq geri götürüləndə onun əsasında saxlanan məlumat silinir.

   Avropa məlumat qoruma orqanları məktəb və universitetlərdə AI alətlərinə də eyni yanaşırlar: istəyə bağlı alət
   təhsilin şərtinə çevrilmir, onsuz da təhsil almaq mümkün qalır. Təhsilin məcburi hissəsi olan analitika isə qanuni
   vəzifəyə əsaslanmalıdır.
3. **Kodda.** Razılıq yalnız bu şərtlərlə etibarlıdır, ona görə platforma belə işləyir:
   - Server AI tutor (`POST /api/tutor/{cid}/ask`) və kampus köməkçisi (`POST /api/campus/ask`) sorğusunu cari mətnə
     verilmiş `ai` razılığı olmadan tərcümə olunmuş 403 ilə rədd edir. Heç nə saxlanmır: nə sual, nə cavab, nə limit
     sayğacı. Qayda AI-dan istifadə edən hər rola aiddir: tələbəyə, müəllimin "Tutoru sınayın" səhifəsinə, kampus
     köməkçisini çağıran işçiyə (`backend/zeka/legacy/r_learning.py`, `_ai_consent`).
   - İşçinin iş alətləri bu razılığın əhatəsində deyil: Test studiyasında sual yaratma, sual-cavabda müəllim cavabının
     qaralaması və sillabus fənn materialını oflayn mühərriklə emal edir. Bu, işçinin vəzifəsidir (T, İ). Şəxsin
     sualını xarici AI-yə göndərən yeganə yer AI tutordur və o, `external_ai` razılığını yoxlayır.
   - Portalın qalan hissəsi bu razılıqdan asılı deyil. Portalın hər yerini bağlayan pəncərə yoxdur. Razılıq pəncərəsi
     yalnız AI səhifəsi açılanda çıxır və "İndi yox" düyməsi var. Razılıq verilməyibsə, səhifə açıq qalır, sual xanası
     isə bağlanır və "Razılıq ver" düyməsi göstərilir (`frontend/js/privacy.js`, `aiConsent`; `frontend/js/chat.js`).
   - Profildə razılığı geri götürmək olar. Geri götürmə şəxsin AI söhbətlərini (`messages`) dərhal silir və auditə
     yazılır (`consent`, `chats_deleted`). Əvvəl təsdiq pəncərəsi bunu xəbər verir.
   - Mətn dəyişəndə versiya dəyişir, köhnə razılıq qüvvədən düşür və AI səhifəsi razılığı yenidən soruşur.
   - Demo bazasında demo şəxslərin razılığı əvvəlcədən yazılıb (`store.seed`). Prod heç kimi yaratmır: hər real
     istifadəçi razılığı öz seçimi ilə verir.
4. **Qərarı nə dəyişə bilər.** Universitet AI tutoru tədrisin məcburi hissəsi edərsə (məsələn, fənn proqramında
   qiymətləndirilən tapşırıq kimi), emalın əsası T olur. Onda hüquqşünasın 9.6-cı maddə üzrə rəyi lazımdır. Razılıq
   yalnız xarici AI üçün qalır, `_ai_consent` yoxlaması isə həmin fənnin tutoru üçün götürülür.

Bu sessiyada qanunun mətnini (e-qanun.az) yenidən açmaq mümkün olmadı: iş mühitinin şəbəkəsi sayta çıxışı bağlayır.
Yuxarıdakı maddələr tədqiqat sənədindəki yoxlanmış xülasəyə əsaslanır. EDPB təlimatı və Avropa orqanlarının yanaşması
isə müəllifin biliyidir, bu sessiyada mənbədən yoxlanmayıb. Hüquqşünas baxanda bu bölmə ilk yoxlanacaq yerdir.

## Saxlama müddətləri (universitet ayarları)

"Universitet ayarları" → "Saxlama müddətləri" (`PUT /api/admin/settings/retention`, `limits` ayarında). Gündəlik
`retention.purge` işi (`backend/zeka/legacy/periodic.py`) bu müddətdən köhnə sətirləri silir. Sətirlər 5 000-lik
hissələrlə silinir və hər hissədən sonra tranzaksiya təsdiqlənir: müddət qısaldılanda da yazma kilidi uzun tutulmur.

| Ayar | Susmaya görə | Hədd | Nə silinir |
|---|---|---|---|
| `chats_days` (`limits.retention_days`) | 180 | 30–3650 | `messages` (AI tutor və kampus köməkçisi söhbətləri) |
| `community_days` (`limits.community_retention_days`) | 180 | 1–3650 | `club_messages` və onların şikayətləri |
| `notifications_days` | 365 | 30–3650 | `notifications` |
| `logs_days` | 90 | 7–3650 | `job_runs`, göndərilmiş `outbox`, bitmiş `webhook_deliveries` |
| `audit_days` | 1825 | 365–3650 | `audit` |

Ayarsız qısa müddətlər: `doc_keys` (5 dəqiqə), `rate_hits` və `login_blocks` (1 gün), `sessions` (boş qalma həddi),
`sso_pending` (10 dəqiqə). "Q-müddət": qanunun tələb etdiyi müddət; platforma bu qeydləri silmir, müddəti sahib təyin edir.

## Cədvəl

| Sütun | Məqsəd | İxrac | Silmə | Saxlama | Əsas |
|---|---|---|---|---|---|
| `users.id` | Hesab: ad, rol, qrup, tələbə bileti, e-poçt, parol, MFA, seçimlər | bəli (sirlər yox) | anonimləşdir | Q-müddət | T, Q |
| `academy_progress.user_id` | Müəllimin AI Akademiya irəliləyişi | bəli | sil | hesab qədər | T |
| `activation_codes.user_id` | Birdəfəlik aktivləşdirmə kodu | bəli (hash yox) | sil | kodun müddəti | S |
| `api_tokens.created_by` | API açarını yaradan admin | yox: icraçı | saxla | açar qədər | İ |
| `assignments.created_by` | Tapşırığı yaradan müəllim | yox: icraçı | saxla | Q-müddət | İ |
| `attempts.user_id` | Test cəhdləri (məşq və qiymətli) | bəli | saxla | Q-müddət | Q |
| `attendance.user_id` | Davamiyyət | bəli | saxla | Q-müddət | Q |
| `attendance.marked_by` | Davamiyyəti qeyd edən | yox: icraçı | saxla | Q-müddət | İ |
| `attendance_opening.student_id` | Kəsid tarixinə qədərki davamiyyət | bəli | saxla | Q-müddət | Q |
| `audit.user_id` | Şəxsin öz əməlləri (giriş, razılıq, müraciət) | bəli (`detail` yox) | saxla | `audit_days` | S |
| `campus_kb.updated_by` | Bilik bazası məqaləsini dəyişən | yox: icraçı | saxla | məqalə qədər | İ |
| `campus_kb_versions.changed_by` | Məqalə versiyasının müəllifi | yox: icraçı | saxla | məqalə qədər | İ |
| `club_members.user_id` | Klub üzvlüyü | bəli | sil | hesab qədər | T |
| `club_messages.author_id` | Öz klub mesajları | bəli | sil | `community_days` | T |
| `club_reports.reporter_id` | Öz şikayətləri | bəli | sil | `community_days` | T |
| `club_reports.resolved_by` | Şikayətə baxan moderator | yox: icraçı | saxla | `community_days` | İ |
| `clubs.leader_id` | Rəhbərlik etdiyi klub | bəli | saxla | klub qədər | T |
| `clubs.decided_by` | Klubu təsdiqləyən dekanlıq | yox: icraçı | saxla | klub qədər | İ |
| `consents.user_id` | Razılıq: məqsəd, mətnin versiyası, vaxt, üsul | bəli | saxla (sübut) | Q-müddət | R |
| `course_tools.added_by` | Fənnə aləti əlavə edən | yox: icraçı | saxla | fənn qədər | İ |
| `courses.teacher_id` | Müəllimin apardığı fənlər | bəli | saxla | Q-müddət | T |
| `doc_keys.user_id` | Birdəfəlik baxış açarı | yox: canlı açardır | sil | 5 dəqiqə | S |
| `documents.holder_id` | Verilmiş sənədlər (arayış, sertifikat) | bəli (imtahan protokolu və cədvəli yox) | saxla | Q-müddət | Q |
| `documents.issued_by` | Sənədi verən | yox: icraçı | saxla | Q-müddət | İ |
| `enrollments.user_id` | Fənnə qeydiyyat | bəli | saxla | Q-müddət | Q |
| `exam_attempts.student_id` | İmtahan cəhdi | bəli (bal yalnız açıqlamadan sonra) | saxla | Q-müddət | Q |
| `exam_events.actor_id` | İmtahan jurnalında icraçı (nəzarətçi, müəllim) | yox: icraçı | saxla (əlavə olunan jurnal) | Q-müddət | İ |
| `exam_events.student_id` | İmtahan jurnalında tələbəyə aid hadisələr | yalnız açıqlanmış imtahan | saxla (əlavə olunan jurnal) | Q-müddət | Q |
| `exam_forms.student_id` | Tələbənin imtahan variantı | **heç vaxt** | saxla | Q-müddət | Q |
| `exam_proctors.user_id` | Nəzarətçi təyinatı | bəli | saxla | Q-müddət | T |
| `exam_proctors.added_by` | Nəzarətçini təyin edən | yox: icraçı | saxla | Q-müddət | İ |
| `exam_roster.student_id` | İmtahan siyahısında yer, buraxılmama səbəbi | bəli | saxla | Q-müddət | Q |
| `exam_roster.added_by` | İstisnanı əlavə edən | yox: icraçı | saxla | Q-müddət | İ |
| `exam_statements.closed_by` | İmtahan-qiymət cədvəlini bağlayan dekanlıq | yox: icraçı | saxla | Q-müddət | İ |
| `events.user_id` | Fəaliyyət qeydi: giriş, günün ilk sorğusu, dəyişiklik edən sorğu (rol, modul, vaxt); aktiv istifadəçi və akkreditasiya göstəriciləri | bəli | sil | 365 gün | S, T |
| `exams.created_by` | İmtahanı yaradan müəllim | yox: icraçı | saxla | Q-müddət | İ |
| `feedback.user_id` | Platforma haqqında rəy | bəli | sil | hesab qədər | T |
| `files.owner_id` | Yüklədiyi fayllar (həkim arayışı, tapşırıq) | bəli (metadata; fayl öz keçidi ilə) | saxla | bağlı qeyd qədər | T, Q |
| `final_grades.user_id` | Yekun qiymətlər (transkript) | bəli | saxla | Q-müddət | Q |
| `grade_changes.user_id` | Dərc olunmuş balın dəyişmə tarixçəsi | bəli | saxla | Q-müddət | Q |
| `grade_changes.changed_by` | Balı dəyişən | yox: icraçı | saxla | Q-müddət | İ |
| `grades.user_id` | Komponent balları | yalnız dərc olunmuş | saxla | Q-müddət | Q |
| `grades.entered_by` | Balı yazan | yox: icraçı | saxla | Q-müddət | İ |
| `ical_feeds.user_id` | Şəxsi təqvim lenti | bəli (hash yox) | sil | hesab qədər | T |
| `interventions.student_id` | Zəka Radar dəstək planı | bəli | sil | hesab qədər | T |
| `interventions.created_by` | Planı yazan müəllim | yox: icraçı | saxla | plan qədər | İ |
| `lessons.teacher_id` | Müəllimin dərsləri | bəli | saxla | Q-müddət | T |
| `materials.uploaded_by` | Materialı yükləyən | yox: icraçı | saxla | fənn qədər | İ |
| `messages.user_id` | AI tutor və kampus köməkçisi söhbətləri | bəli | sil; `ai` razılığı geri götürüləndə də dərhal silinir | `chats_days` | R |
| `migration_files.imported_by` | Köhnə sistemin faylını yükləyən işçi (Task 38) | yox: icraçı | saxla | Q-müddət | İ |
| `news.author_id` | Xəbərin müəllifi (işçi) | yox: icraçı | saxla | xəbər qədər | İ |
| `news_reads.user_id` | Oxunmuş xəbərlər | bəli | sil | hesab qədər | T |
| `news_rsvp.user_id` | Tədbirə qeydiyyat | bəli | sil | hesab qədər | T |
| `news_saved.user_id` | Saxlanmış xəbərlər | bəli | sil | hesab qədər | T |
| `notifications.user_id` | Bildirişlər | bəli | sil | `notifications_days` | T |
| `office_bookings.student_id` | Qəbul saatına yazılış | bəli | sil | hesab qədər | T |
| `office_bookings.teacher_id` | Müəllimin qəbul saatına yazılanlar | yox: sətir tələbənindir | saxla | yazılış qədər | İ |
| `office_bookings.cancelled_by` | Yazılışı ləğv edən | yox: icraçı | saxla | yazılış qədər | İ |
| `office_hours.teacher_id` | Müəllimin qəbul saatları | bəli | saxla | hesab qədər | T |
| `outbox.user_id` | Göndərilən e-poçt məktubları | bəli | sil | `logs_days` | T |
| `privacy_requests.user_id` | Silmə sorğusu | bəli | saxla (sübut) | Q-müddət | S |
| `privacy_requests.decided_by` | Qərarı verən | yox: icraçı | saxla | Q-müddət | İ |
| `qa_replies.author_id` | Forumda öz cavabları | bəli | sil | fənn qədər | T |
| `qa_reports.reporter_id` | Forumda öz şikayətləri | bəli | sil | fənn qədər | T |
| `qa_reports.resolved_by` | Şikayətə baxan | yox: icraçı | saxla | fənn qədər | İ |
| `questions.created_by` | Sualı yazan müəllim | yox: imtahan hovuzu heç vaxt çıxmır | saxla | fənn qədər | İ |
| `recovery_codes.user_id` | MFA bərpa kodları | bəli (hash yox) | sil | hesab qədər | S |
| `request_events.actor_id` | Müraciət addımını atan işçi | yox: icraçı (öz müraciətinin tarixçəsi `VIA` ilə) | saxla | Q-müddət | İ |
| `request_messages.author_id` | Müraciətdə öz mesajları | bəli | saxla | Q-müddət | T |
| `requests.student_id` | E-xidmət müraciətləri | bəli | saxla | Q-müddət | T, Q |
| `role_grants.user_id` | Əlavə rollar | bəli | sil | hesab qədər | S |
| `role_grants.granted_by` | Rolu verən admin | yox: icraçı | saxla | qrant qədər | İ |
| `sessions.user_id` | Sessiyalar (IP, brauzer) | bəli (hash yox) | sil | boş qalma həddi | S |
| `sso_identities.user_id` | Universitet hesabı (SSO) bağlantısı | bəli | sil | hesab qədər | S |
| `sso_identities.linked_by` | Bağlantının üsulu (şəxs id-si deyil) | yox | saxla | bağlantı qədər | S |
| `sso_pending.link_user_id` | Yarımçıq SSO girişi | yox: canlı sirr | sil | 10 dəqiqə | S |
| `student_status_events.student_id` | Status əmrləri (məzuniyyət, xaric, köçürmə) | bəli | saxla | Q-müddət | Q |
| `student_status_events.entered_by` | Əmri daxil edən | yox: icraçı | saxla | Q-müddət | İ |
| `submissions.student_id` | Tapşırıq işləri və balları | bəli | saxla | Q-müddət | Q |
| `submissions.graded_by` | Qiymətləndirən | yox: icraçı | saxla | Q-müddət | İ |
| `support_messages.author_id` | Dəstək sorğusunda öz mesajları | bəli | sil | sorğu qədər | T |
| `support_tickets.user_id` | Dəstək sorğuları | bəli | sil | hesab qədər | T |
| `support_tickets.assignee_id` | Sorğuya baxan işçi | yox: icraçı | saxla | sorğu qədər | İ |
| `syllabi.user_id` | Sillabusun qaralamasını yazan | yox: iş məhsulu, fərdi deyil | saxla | fənn qədər | İ |
| `syllabus_steps.user_id` | Təsdiq addımını atan | yox: icraçı | saxla | Q-müddət | İ |
| `syllabus_versions.author_id` | Sillabus versiyasının müəllifi | yox: iş məhsulu | saxla | Q-müddət | İ |
| `syllabus_versions.decided_by` | Versiyanı təsdiqləyən | yox: icraçı | saxla | Q-müddət | İ |
| `teacher_questions.student_id` | Müəllimə öz sualları (forum mövzuları) | bəli | sil | fənn qədər | T |
| `teaching_units.teacher_id` | Müəllimin tədris vahidləri | bəli | saxla | Q-müddət | T |
| `webhooks.created_by` | Webhook-u yaradan admin | yox: icraçı | saxla | webhook qədər | İ |

Şəxsi sütunu olmayan cədvəllər: `exam_answers` (cavablar `exam_attempts` ilə şəxsə bağlıdır: ixrac yalnız açıqlamadan
sonra, silmə: saxla), `request_events`, `request_messages`, `support_messages` (yuxarıda). `login_blocks.account` və
`rate_hits.key` girişin yazıldığı adı və ya açarı saxlayır, şəxs id-si deyil: 1 gündən sonra silinir. Qalan cədvəllər
(fənn materialı, cədvəl, otaq, kataloq, ayar) şəxsə aid deyil.

## Qərarlar

Bu suallar əvvəl hüquqşünasa ünvanlanmışdı. Sahib 2026-11-21-də qərarı mənə tapşırdı. Hər qərar qüvvədədir və yanında
onu nəyin dəyişə biləcəyi yazılıb. Hüquqşünasın sonrakı yazılı rəyi qərarı dəyişirsə, düzəliş bu bölmədə və kodda edilir.

### 1. Razılığın üsulu: portalda işarə qutusu

**Qərar.** Hər iki məqsəd üçün ("AI köməkçiləri" və "xarici AI") razılıq portalda işarə qutusu ilə verilir. Hər seçim
ayrıca sətirdir (`consents`): şəxsin hesabı, məqsəd, mətnin versiyası, vaxt, dil və üsul (`method = 'portal'`).
Razılıq verilən hər mətn versiyası olduğu kimi `consent_texts`-də qalır. Bu məqsədlər üçün e-imza tələb olunmur.

**Səbəb.**
- Şəxs öz hesabına (parol və MFA, ya da universitet SSO-su ilə) daxil olub seçimi özü edir. Qeyd kimin, hansı mətnə, nə
  vaxt, hansı dildə razılıq verdiyini sübut edir. 8-ci maddəyə görə sübut yükü operatorun üzərindədir və bu qeyd onu
  daşıyır.
- Hər iki məqsəd istəyə bağlıdır: imtina yalnız həmin köməkçini bağlayır, başqa heç bir xidməti yox. Razılığı bir
  düymə ilə geri götürmək olur.
- E-imza tələbi ASAN və ya SİMA imzası olmayan tələbəni AI köməkçilərindən praktik olaraq ayırardı. Bu da imtinanı
  zərərsiz saxlamaq şərtinə ziddir.
- Təhsilin əsas emalı razılığa əsaslanmır (Q, T, S).

**Qalan risk.** 8-ci maddənin hərfi mətni yazılı razılığı və ya gücləndirilmiş elektron imzalı sənədi adlandırır. Portal
qeydi bunlardan heç biri deyil. Bu üsul etibarsız sayılarsa, yalnız iki istəyə bağlı köməkçinin emalı əsassız qalır:
onlar yeni üsulla razılıq toplanana qədər bağlanır. Təhsilin əsas emalına, qiymətlərə və sənədlərə bu risk toxunmur.

**Qərarı nə dəyişə bilər.** Səlahiyyətli dövlət orqanı və ya universitetin hüquqşünası 8-ci maddədəki "yazılı forma"
tələbinin portal qeydini əhatə etmədiyini yazılı bildirə bilər. Onda gücləndirilmiş e-imza (mygov ID və ya SİMA
qoşulanda) və ya kağız razılıq ayrıca üsul kimi əlavə olunur. `consents.method` sütunu bunun üçündür
(`backend/migrations/0400_privacy.sql`), kodda yalnız qeydin alındığı yer dəyişir.

### 2. Akademik qeydlərin saxlanma müddəti

**Qərar.** Cari ayarlar qalır:
- "Q-müddət" ilə işarələnən qeydləri (qiymət, davamiyyət, imtahan, verilmiş sənəd, müraciət, status əmri) platforma
  silmir.
- Ayarla idarə olunan müddətlər dəyişmir: söhbətlər 180 gün, klub mesajları 180 gün, bildirişlər 365 gün, texniki
  jurnallar 90 gün, audit 1825 gün.

**Səbəb.** Təhsil sənədlərinin saxlanma müddətini dövlət arxiv qaydaları (tipik sənədlərin saxlanma müddətləri ilə
siyahı) və universitetin işlər nomenklaturası müəyyən edir. Bu sessiyada həmin siyahını mənbədən oxumaq mümkün olmadı,
ona görə il yazmıram. Səhv qısa müddət geri qaytarılmayan silmədir, uzun saxlamanı isə sonra düzəltmək olar.
Əsaslandıra bildiyim müddətlər bunlardır:
- **Audit, 5 il (1825 gün).** Akkreditasiya beş ildən bir keçirilir. 3.5.3 və 5.4.2–5.4.8 göstəriciləri platformanın
  fəaliyyət jurnalını və təhlükəsizliyini sübut kimi istəyir (`docs/research/01-azerbaycan-bazar-ve-qanun.md`, §3).
- **Fəaliyyət qeydi (`events`), 365 gün.** Bir tədris ili və illik hesabat üçün kifayətdir.
- **Yekun qiymət, status əmri və verilmiş sənəd.** Diplom və transkript bunlara əsaslanır. Məzun onları ömrü boyu
  istəyə bilər, ona görə silinmir.

**Kim təsdiqləyir.** Universitetin arxivi (işlər nomenklaturası) və hüquqşünas. Təsdiq olunan müddət bu sənəddə
"Q-müddət" yerinə yazılır. Silmə lazım olarsa, `retention.purge` işinə yeni ayar kimi əlavə olunur.

### 3. Silmədən sonra tələbə bileti nömrəsi qalır

**Qərar.** Anonimləşdirmə ad, ata adı, e-poçt, parol və seçimləri silir. `users.student_no` qalır.

**Səbəb.** Silmədən sonra saxlanan akademik qeydlər (Q) anonim hesaba bağlıdır. Nömrə onları dövlət reyestri
"Tələbə-məzun"dakı qeydlə uzlaşdırmağın yeganə açarıdır. Reyestr Prezidentin 225 nömrəli Fərmanı (23.02.2010) ilə
aparılır: hər universitet ona qoşulur və dəyişikliyi 10 gün ərzində daxil edir. Nömrə silinsə, saxlanan qeydlər
reyestrlə yoxlanıla bilməz, məzunun arayış və ya transkript sorğusu cavabsız qalar. Təkrar idxal silinmiş hesabı geri
qaytarmır (`test_a_users_import_never_brings_an_erased_account_back`).

**Qərarı nə dəyişə bilər.** Reyestr başqa açara keçə bilər və ya hüquqşünas nömrənin də silinməli olduğunu yaza bilər.
Onda nömrə arxivin saxladığı ayrıca uyğunluq cədvəlinə köçürülür və `users`-dən silinir.

### 4. Xarici AI xidmətinin adı və ölkəsi

**Qərar.** Razılıq mətni xidmətin adının və yerləşdiyi ölkənin məxfilik bildirişində göstərildiyini deyir. Bildiriş
onları LLM ayarlarından götürür: `config.json`-da `llm.vendor` və `llm.country`, ya da `AZTU_LLM_VENDOR` və
`AZTU_LLM_COUNTRY` (`GET /api/privacy` → `external_ai`). Razılığın versiyası mətnlə yanaşı bu iki dəyəri də daşıyır:
- Başqa xidmət və ya ölkə yeni versiyadır. Köhnə razılıqlar dayanır, suala oflayn mühərrik cavab verir.
- `consent_texts` razılıq anında göstərilən adı və ölkəni də saxlayır.
- Mətnin bu dəyişikliyi də yeni versiyadır. Əvvəlki xarici AI razılıqları dayanır və yenidən soruşulur: bu, gözlənilən
  nəticədir.

**Səbəb.** 14-cü maddə ekvivalent qoruması olmayan ölkəyə ötürməni yalnız şəxsin razılığı ilə qəbul edir. Belə
razılıq konkret alıcıya və ölkəyə verilməlidir. Adı mətnin özünə yazmaq hər xidmət dəyişikliyində tərcümələri ilə yeni
mətn tələb edərdi. Ayardan gələn ad eyni nəticəni verir: ad dəyişəndə razılıq yenə dayanır. Xarici LLM qoşulub, amma
ad və ya ölkə yazılmayıbsa, bildiriş "göstərilməyib" yazır. Yerləşdirmə runbook-u hər iki dəyəri doldurmağı tələb edir
(`docs/runbooks/deploy.md`).

**Qərarı nə dəyişə bilər.** Universitet ölkə daxilində işləyən model seçə bilər (G-Cloud və ya öz serveri). Onda
`country` "Azərbaycan" olur və 14-cü maddə tətbiq olunmur. Razılıq yenə soruşulur, çünki versiya dəyişir.

### 5. Silmə qərarını kim verir

**Qərar.** Qərarı tədris şöbəsi öz əhatəsində verir (`privacy.decide`). Administrator qərar vermir.

**Səbəb.** Qeydin sahibi və tələbənin statusunu bilən tədris şöbəsidir. Administrator texniki roldur. Məlumatın
taleyini həll etməsi vəzifələrin bölgüsünü pozardı (SA-F8 testi).

**Qərarı nə dəyişə bilər.** Universitet məlumatların qorunması üzrə məsul şəxs təyin edə bilər. Onda
`backend/zeka/core/perms.py`-də yeni rol `privacy.decide` icazəsini alır.

### 6. Subyektlərin kateqoriyaları

**Qərar.** Sistemdə tələbələr, müəllimlər və işçilər var. Abituriyent və məzun sistemə düşmür: qəbul və məzun modulu
yoxdur, silmədən sonra qalan qeyd anonimdir. Zəka tələbə məlumatı saxladığı üçün qeydiyyatdan azad deyil.

**Qərarı nə dəyişə bilər.** Qəbul və ya məzun modulu əlavə oluna bilər. Onda qeydiyyat ərizəsinə yeni kateqoriya yazılır.

### 7. Zəka Radar risk balı ixraca düşür

**Qərar.** Bu qərarı sahib özü verib (2026-11-21). `interventions.risk_before`, `interventions.level_before` və
`interventions.drivers` tələbənin öz ixracındadır. Müəllimin AI qaralaması (`teacher_questions.ai_draft`) ixraca düşmür.

**Səbəb.** Bal tələbə haqqında çıxarılmış nəticədir, yəni onun fərdi məlumatıdır. Çıxış hüququ onu əhatə edir.

**Qərarı nə dəyişə bilər.** Sahibin yeni qərarı. Onda `privacy.OMIT`-ə sütunlar əlavə olunur, bu bölmə və
`docs/API.md` yenilənir.

## Maddə 15 qeydiyyatı üçün xülasə

- Sistem: Zəka, AzTU Rəqəmsal Kampus. Operator: universitet (`settings.university`).
- Subyektlər: tələbələr, müəllimlər, işçilər.
- Kateqoriyalar: kimlik və təhsil məlumatı, akademik qeydlər, müraciət və sənədlər, yazışma və AI söhbətləri, texniki
  jurnallar. Biometrik məlumat (9.5-ci maddə) toplanmır: proktorinq kamerasız və səssizdir.
- Alıcılar: universitetin işçiləri öz rolu və əhatəsi daxilində; xarici AI xidməti yalnız şəxsin razılığı ilə və
  maskalanmış suallarla (`backend/zeka/legacy/r_learning.py`, `privacy.allowed`). Xidmətin adı və ölkəsi bildirişdə
  ayardan göstərilir ("Qərarlar", 4). Webhook və ixraclar admin icazəsi ilə.
- Saxlama: yuxarıdakı cədvəl və universitet ayarları.
- Təhlükəsizlik tədbirləri: `SECURITY.md`, `docs/runbooks/backup.md`, rol × marşrut matrisi
  (`tests/security/matrix.json`), audit jurnalı.
