# Runbook: insident cavabı

Kim üçün: növbətçi admin, AzTU İT və məhsulun sahibi. Nəzarət: NIST CSF RESPOND, SP 800-53 IR-4, IR-6, IR-8
(`docs/security/nist-csf-profile.md` #27). `C` aşağıda `docker compose -f infra/compose.yml` deməkdir.

## Rollar və əlaqə

| Rol | Kim | Nə edir |
|---|---|---|
| Növbətçi admin | Sahib təyin edir | İlk baxış, təsnif, sərhədləmə |
| İnsidentin rəhbəri | Məhsulun sahibi | Qərar, xəbərdarlıq, bağlanış |
| AzTU İT | İT şöbəsinin rəhbəri | Server, şəbəkə, backup açarının ikinci nüsxəsi |
| Hüquqşünas | Universitet | Fərdi məlumat pozuntusunda bildiriş qərarı |

Adlar və telefonlar bu cədvələ hədəf serverdə yazılır (Task 44). **Hələ boşdur:** sahib sonra verəcək
(`docs/runbooks/release-v1.md`, "Sahibin verəcəkləri", 4). Kənardan gələn zəiflik bildirişi
`ZEKA_SECURITY_CONTACT` ünvanına gəlir (`/.well-known/security.txt`).

## Səviyyələr

| Səviyyə | Nümunə | Cavab müddəti |
|---|---|---|
| 1 | Fərdi məlumatın sızması, kimliyin ələ keçirilməsi, imtahan zəncirinin qırılması, baza zədəsi | Dərhal; sahib 1 saat ərzində xəbərdar edilir |
| 2 | Portal 15 dəqiqədən çox açılmır, imtahan zamanı kəsinti, backup 26 saatdan köhnədir | 1 saat |
| 3 | Bir modulun xətası, e-poçt gecikir, tək istifadəçinin problemi | Növbəti iş günü |

## Addımlar

1. **Qeyd et.** Vaxt, kim xəbər verdi, nə görünür. İnsident jurnalı: tarix, səviyyə, xülasə, hərəkətlər, bağlanış.
2. **İlk baxış.**
   ```bash
   timedatectl show -p NTPSynchronized --value           # yes
   curl -s -o /dev/null -w '%{http_code}\n' https://<ad>/healthz
   $C ps && $C logs --tail 300 app
   $C exec app python backend/manage.py jobs status      # işlərin son icrası və xətası
   $C exec app python backend/manage.py jobs check       # backup yaşı, boş disk, ardıcıl xətalar, icraçı (kod 1: problem var, 2: baza yoxdur)
   df -h /var/lib/docker
   ```
3. **Sərhədlə.**
   - Hesab ələ keçirilib: admin hesabı aktiv olmayan statusa keçirir (struktur və reyestr). Aktiv olmayan hesabın
     sessiyaları növbəti sorğuda bitir. Əlavə rol təyinatı götürülürsə, o rolda iş də dərhal dayanır. Sonra parol
     sıfırlanır (müvəqqəti parol, `must_change`).
   - API açarı sızıb: İnteqrasiya → açar → ləğv et. Webhook sirri: yenisini yaradın.
   - Hamının sessiyası bağlanmalıdır (hamı yenidən daxil olur):
     `$C exec app python -c "import os, sqlite3; c = sqlite3.connect(os.environ['ZEKA_DATA'] + '/campus.db'); c.execute('DELETE FROM sessions'); c.commit()"`
   - Server ələ keçirilib: tətbiqi dayandırın (`$C stop app`), diskin nüsxəsini (sübut) AzTU İT götürür, sonra təmiz
     serverdə ikinci hostdakı son backup-dan bərpa (`docs/runbooks/backup.md`).
4. **Sübutu saxla.** Silmədən əvvəl: `$C logs app > incident-<tarix>.log`, giriş jurnalı (`ZEKA_ACCESS_LOG`), audit
   (`/admin/audit`), lazım olsa `manage.py exam-verify <id>`. Audit jurnalının sətri dəyişdirilmir və ən azı bir il saxlanır (`0410`); universitetin saxlama müddəti (`audit_days`) bitəndən sonra gündəlik iş onu silir.
5. **Bərpa et.** Səbəb aradan qalxandan sonra: `/healthz`, hər rolun əsas səhifəsi, `jobs status`, backup.
6. **Xəbər ver.**
   - Fərdi məlumat pozuntusu: hüquqşünas qərar verir. Bildiriş müddəti universitetin müqaviləsinə və Azərbaycan
     qanunvericiliyinə görədir. Qanunun oxunmuş maddələrində (998-IIIQ, 2, 5, 8–10, 13–17) müddət tapılmayıb: hüquqşünas
     təsdiqləyir.
   - İmtahana təsir: dekanlıq və müəllim; imtahan günü runbook-u (`docs/runbooks/exam-day.md`).
7. **Bağla.** 5 iş günü ərzində qısa nəticə: səbəb, təsir, nə dəyişdi, reqressiya testi.
   Təhlükəsizlik tapıntısı `docs/security/review-log.md`-yə yazılır.

## Tez-tez olan hallar

| Hal | Hərəkət |
|---|---|
| «Serverin vəziyyəti» bildirişi (`ops`) | Admin səhifəsində hansı yoxlamadır; hədlər və hərəkət `docs/runbooks/backup.md`, «Xəbərdarlıqlar» |
| Disk dolub | Köhnə backup-lar ikinci hostdadırsa lokal `backups/`-dan köhnələri silin; `docker system prune` (həcmlər yox) |
| `outbox` `failed` artır | `ZEKA_SMTP_*` və relə; `SELECT last_error, COUNT(*) FROM outbox WHERE status='failed' GROUP BY 1` |
| Server başlamır: "checksum" | Tətbiq olunmuş miqrasiya faylı dəyişib. Əvvəlki teqə qayıdın (`docs/runbooks/deploy.md`, Geri qaytarma) |
| Server başlamır: baza koddan yenidir | Bazanın versiyasının kodunu yerləşdirin |
| 503 və `Retry-After` artır | Yük: `ZEKA_WORKERS` nüvə sayına qədər; yavaş sorğu üçün `tools/queryplan.py` |
| Webhook alıcısı cavab vermir | Çatdırılma özü təkrar olunur; digər alıcılara təsir etmir |

## Məşq

İldə bir dəfə masaüstü məşq (IR-2, IR-3): bir səviyyə 1 ssenarisi (məsələn, müəllim hesabının ələ keçirilməsi)
addım-addım keçilir. Nəticə bu fayla əlavə olunur. İlk məşq sahibin qərarıdır (`nist-csf-profile.md` #28).
