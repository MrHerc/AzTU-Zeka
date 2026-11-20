# Fərdi məlumatların inventarı (Task 40)

Bu sənəd Zəka platformasında şəxsə aid məlumatı saxlayan hər sütunu göstərir: məqsəd, ixrac, silmə, saxlama müddəti
və hüquqi əsas. "Fərdi məlumatlar haqqında" Qanunun (998-IIIQ) 15-ci maddəsi üzrə informasiya sisteminin dövlət
qeydiyyatı üçün əsasdır.

Mənbə kodda: `backend/zeka/modules/identity/repo.py` → `INVENTORY`, `VIA`, `SELECTS`, `ERASE_FIRST`, `ANONYMISE`.
`tests/integration/test_privacy.py` sxemi oxuyur: şəxsin id-sini saxlayan yeni sütun (`user_id`, `student_id`,
`*_by` və s.) `INVENTORY`-də və bu sənəddə yoxdursa, test düşür.

Hüquqi əsaslar hüquqşünasın rəyinə qədər təklifdir (SPEC, açıq sual 10).

## Qaydalar

**İxrac.** `GET /api/me/export` daxil olmuş şəxsə öz sətirlərini JSON faylı kimi verir. Hər ixrac auditə yazılır
(`privacy_export`). Heç vaxt ixraca düşmür:

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
  `assignee_id`) ixraca düşmür.

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
| R | Şəxsin razılığı (8-ci maddə); geri götürülə bilər |
| S | İnformasiya təhlükəsizliyi və hesabatlılıq (giriş, sessiya, audit) |
| İ | İşçinin vəzifəsi üzrə əməli (icraçı sütunu); qeydin əsası qeydin özünün əsasıdır |

## Saxlama müddətləri (universitet ayarları)

"Universitet ayarları" → "Saxlama müddətləri" (`PUT /api/admin/settings/retention`, `limits` ayarında). Gündəlik
`retention.purge` işi (`backend/zeka/legacy/periodic.py`) bu müddətdən köhnə sətirləri silir.

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
| `messages.user_id` | AI tutor və kampus köməkçisi söhbətləri | bəli | sil | `chats_days` | R |
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

## Sahibin və hüquqşünasın qərarları

1. Portal içində işarə qutusu ilə razılıq (`method = 'portal'`) 8-ci maddənin "yazılı və ya gücləndirilmiş elektron
   imza ilə" tələbinə uyğundurmu? Uyğun deyilsə, kağız və ya e-imza ilə razılıq ayrıca üsul kimi yazılmalıdır.
2. Hər "Q-müddət" üçün konkret saxlama müddəti (qiymət, davamiyyət, imtahan, sənəd, müraciət).
3. Silmədən sonra tələbə bileti nömrəsi qalsınmı (dövlət reyestri ilə əlaqə), yoxsa o da silinsin?
4. Silmə qərarını tədris şöbəsi verirmi, yoxsa ayrıca məlumatların qorunması üzrə məsul şəxs (rol) lazımdır?
5. Xarici AI xidməti ölkə xaricindədirsə (14-cü maddə): razılıq mətnində xidmətin adı və ölkəsi yazılmalıdırmı?
6. Müəllim, işçi və tələbədən başqa (abituriyent, məzun) şəxslər sistemə düşəcəkmi? Qeydiyyat ərizəsindəki subyekt
   kateqoriyaları buna görə yazılır. Yalnız işçilərə aid sistem qeydiyyatdan azaddır; Zəka tələbə məlumatı saxladığı
   üçün azad deyil.

## Maddə 15 qeydiyyatı üçün xülasə

- Sistem: Zəka, AzTU Rəqəmsal Kampus. Operator: universitet (`settings.university`).
- Subyektlər: tələbələr, müəllimlər, işçilər.
- Kateqoriyalar: kimlik və təhsil məlumatı, akademik qeydlər, müraciət və sənədlər, yazışma və AI söhbətləri, texniki
  jurnallar. Biometrik məlumat (9.5-ci maddə) toplanmır: proktorinq kamerasız və səssizdir.
- Alıcılar: universitetin işçiləri öz rolu və əhatəsi daxilində; xarici AI xidməti yalnız şəxsin razılığı ilə və
  maskalanmış suallarla (`backend/zeka/legacy/r_learning.py`, `privacy.allowed`); webhook və ixraclar admin icazəsi ilə.
- Saxlama: yuxarıdakı cədvəl və universitet ayarları.
- Təhlükəsizlik tədbirləri: `SECURITY.md`, `docs/runbooks/backup.md`, rol × marşrut matrisi
  (`tests/security/matrix.json`), audit jurnalı.
