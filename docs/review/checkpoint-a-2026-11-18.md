# Checkpoint A baxışı (2026-11-18)

Faza 1 diff-i (`7df5ad4..HEAD`) yeddi rəyçi ilə yoxlandı: `ecc:code-reviewer`, `ecc:security-reviewer`, `ecc:silent-failure-hunter`, `agent-skills:code-reviewer`, `agent-skills:security-auditor`, `agent-skills:test-engineer`, `ecc:python-reviewer`. Dublikatlar birləşdirildi və 45 tapıntı qaldı. Orta və yüksək 33 tapıntının hər birini ayrıca agent təkzib etməyə çalışdı: 32-si təsdiqləndi, 1-i təkzib olundu. Aşağı səviyyəli 12 tapıntı yoxlanmadı, ona görə də düzəldilmədi. `security-review` bacarığı yüksək inamlı zəiflik tapmadı. Onun iki aşağı qeydindən `render.yaml` şərhi düzəldildi; ikincisi B qrupunda həll olundu.

## Təsdiqlənən və düzəldilən tapıntılar

### A. İkinci host və backup

- **F1** (high) `backend/zeka/core/backup.py:277` — Second-host mirror never re-checks a file that is already there, so a corrupt copy stays
- **F12** (high) `backend/zeka/core/backup.py:305` — Second-host mirror never re-verifies files already present by name; an interrupted ssh transfer is reported as success on the next run
- **F18** (high) `backend/zeka/core/backup.py:305` — İkinci hostda yarımçıq və ya xarab fayl bir daha göndərilmir və yoxlanmır
- **F25** (high) `backend/zeka/core/backup.py:305` — Second host: a file that failed to transfer or failed its checksum is never re-sent or checked again
- **F30** (high) `tests/migration/test_backup_restore.py:200` — Bad-copy test stops at the first failure; the next send() reports success and leaves the damaged set on the second host
- **F7** (high) `backend/zeka/core/backup.py:315` — Second-host mirror deletes remote history when the local backup directory is lost
- **F26** (high) `backend/zeka/core/backup.py:315` — Second-host mirror deletes every remote set that is missing locally, including after host loss
- **F42** (high) `backend/zeka/core/backup.py:269` — send() mirrors deletions, so a lost or recreated local backup directory wipes the offsite history
- **F6** (medium) `backend/zeka/core/backup.py:307` — ssh transfer reads the whole tar into memory; TimeoutExpired is raised from _ssh
- **F13** (medium) `backend/zeka/core/backup.py:276` — Local-path BACKUP_REMOTE creates the directory tree itself, so an unmounted second disk silently becomes a copy on the same disk
- **F14** (low) `backend/zeka/core/backup.py:218` — Non-atomic manifest write, plus uncaught JSON errors in prune/_files, leave backups failing permanently with an undocumented exit code and no offsite copy
- **F28** (medium) `backend/zeka/core/backup.py:205` — The backup encrypts uploads without checking their hash, so one truncated .bin breaks every restore
- **F9** (low) `backend/zeka/core/backup.py:348` — Restore writes the plaintext database before restricting directory permissions
- **F43** (low) `backend/zeka/core/backup.py:115` — decrypt() does not catch zlib.error, so a damaged backup ends in a traceback instead of a BackupError

Düzəliş: Fayl ikinci hostda son adını yalnız SHA-256 uyğun gələndən sonra alır (`.part`, ssh-də `.incoming`); kəsilən göndəriş növbəti dəfə yenidən gedir. Silmə hər iki tərəfin dəstləri üzrə saxlama ilə hesablanır. tar diskdə axınla göndərilir, ssh vaxt aşımı `BackupError` olur. Qoşulmamış disk qovluğu yaradılmır (kod 3). Manifest atomik yazılır, pozulmuş manifest kod 2 verir. SHA-256-sı uyğun gəlməyən yükləmə dəstə düşmür, kod 5 ilə bildirilir. Bərpa qovluğu yazmadan əvvəl 0700 olur. `zlib.error` tutulur.

### B. Backup açarları veb konteynerində

- **F27** (medium) `infra/compose.yml:25` — The off-site backup credentials sit inside the internet-facing app container

Düzəliş: Ayrıca `backup` servisi (`profiles: [backup]`). Backup açarı və ssh açarı yalnız ona qoşulur.

### C. rate_hits təmizlənməsi

- **F5** (medium) `backend/zeka/core/security.py:75` — rate_hits cədvəli heç vaxt təmizlənmir: bir daha gəlməyən açarın sətirləri əbədi qalır
- **F10** (medium) `backend/zeka/core/security.py:71` — DB-backed rate limiter can raise on lock timeout and has no purge for stale keys
- **F44** (medium) `backend/zeka/core/security.py:68` — DB-backed rate limiter never purges stale keys, and lock contention raises sqlite3.OperationalError (HTTP 500)

Düzəliş: Hər limit öz köhnə sətirlərini dəqiqədə bir dəfə silir. F10-un in-memory geri düşməsi edilmədi (F44-ün yoxlayıcısının əsaslandırması).

### D. Supervisor və işçi siqnalları

- **F3** (low) `backend/run.py:123` — Worker installs its SIGTERM handler late; until then it runs the supervisor's inherited stop() handler
- **F41** (low) `backend/run.py:131` — Supervisor can hang on SIGTERM: worker spawned after stop(), and forked child keeps the supervisor's SIGTERM handler
- **F15** (medium) `backend/run.py:171` — Supervisor respawns a worker after a stop request and never gives up on workers that fail at once
- **F19** (medium) `backend/run.py:173` — İşçilər başlaya bilməyəndə supervisor hər saniyə sonsuza qədər yenidən başladır və heç vaxt çıxmır

Düzəliş: Uşaq prosesdə SIGTERM `SIG_DFL` olur. Dayandırmadan sonra işçi doğulmur. 3 × işçi sayı ardıcıl tez ölümdən sonra supervisor səbəbi stderr-ə yazıb kod 1 ilə çıxır.

### E–K. Nüvə

- **F20** (medium) `backend/zeka/legacy/store.py:227` — sync_indexes: kilidsiz oxunan köhnə `last` saxta 'reset' sayılır və tam yenidənqurma başlayır
- **F16** (medium) `backend/zeka/legacy/store.py:722` — Any sqlite3.Error while probing the database is reported as 'not a database'; in demo this deletes the file
- **F17** (high) `backend/zeka/legacy/r_core.py:309` — PDF önizləməsi sürətli GATE yerini 15 s tutur: bir tələbə bütün işçini 503-ə salır
- **F24** (high) `backend/zeka/core/web.py:309` — The request body is read while a handler-gate slot is held, so slow uploads stop a worker
- **F21** (low) `backend/zeka/core/web.py:339` — JSON access log sətirləri paralel işdə qarışır: 'hər sətirdə bir JSON obyekti' pozulur
- **F34** (medium) `tests/integration/test_concurrency.py:196` — Graceful stop is only tested on an idle server; drain() returns before in-flight responses are delivered
- **F2** (low) `backend/run.py:70` — Prod start-up does not require PUBLIC_URL, so documents get localhost QR codes and the session cookie is not Secure

Düzəliş: `sync_indexes` kilid içində `MAX(seq)`-i yenidən oxuyur. `_rebuild_reason` yalnız `DatabaseError`-u "baza deyil" sayır. PDF önizləməsi `slow=True`. Etimadnaməsi olan sorğunun gövdəsi qapıdan əvvəl oxunur (etimadnaməsiz sorğu əvvəlki kimi oxunmadan rədd olunur). Jurnal sətri bir `write` ilə yazılır. `drain()` başlamış hər cavabın yazılmasını gözləyir, keep-alive bağlantıları bağlayır. Prod şəbəkədə `PUBLIC_URL` tələb edir.

### L. Testlər

- **F31** (medium) `tests/integration/test_modes.py:95` — Access-log test is flaky: the log line is printed after the response is sent
- **F32** (low) `tests/migration/test_schema_migrations.py:96` — Pre-migration backup retention test passes when the code keeps the oldest five and deletes the newest
- **F33** (low) `tests/integration/test_concurrency.py:140` — Slow-route test covers only /api/admin/test-llm; the tutor slow flag and the 'writes during slow handlers' criterion are untested

Düzəliş: Jurnal testi sorğu ilə gözləyir. Saxlama testi dəqiq beş ən yeni nüsxəni yoxlayır. Tutor `slow` testi oxu və yazmanı yoxlayır.

## Təkzib olunan

- **F8** `backend/zeka/legacy/store.py:743` — Pre-migration database copies are unencrypted and written with the default umask. Səbəb: canlı baza ilə eyni qovluqda və eyni icazələrlə saxlanır, əlavə giriş vermir.

## Yoxlanmayan aşağı tapıntılar (düzəldilmədi)

- **F4** `backend/run.py:102` — Single-process mode has no SIGTERM handling or drain
- **F11** `backend/zeka/core/backup.py:272` — BACKUP_REMOTE host is not protected against ssh option injection
- **F22** `backend/zeka/legacy/store.py:229` — Yazan proses öz indeks dəyişikliklərini növbəti sorğuda yenidən indeksləyir
- **F23** `backend/run.py:157` — Dayandırma yarışları: uşaq supervisor-un SIGTERM handler-ini miras alır, stop-dan sonra yeni işçi doğulur
- **F29** `backend/run.py:173` — A SIGTERM that arrives while a worker is (re)starting is lost, and shutdown hangs until SIGKILL
- **F35** `tests/integration/test_modes.py:57` — Prod 'restart keeps the account' and 'never deletes' tests do not assert the property they name
- **F36** `tests/migration/test_schema_migrations.py:113` — Pre-engine database simulation re-applies every migration to a head-schema database
- **F37** `tests/unit/test_layers.py:169` — Domain-layer check passes vacuously: backend/zeka/modules does not exist
- **F38** `tests/conftest.py:41` — No test proves the ZEKA_TX_GUARD write-lock guard fires
- **F39** `tests/integration/test_modes.py:72` — Start-up refusal subprocess tests run without ZEKA_DATA or --port
- **F40** `tests/integration/test_multiworker_state.py:120` — Cross-worker index sync is tested only for additions, not deletions
- **F45** `backend/run.py:102` — Single-worker path has no SIGTERM handling; no drain and no stop_grace_period for the multi-worker path

Hər düzəlişin testi var. Yeni testlər köhnə kodda yıxılır (yoxlanıb: gövdə qapısı, drain, ikinci host, lokal itki).
