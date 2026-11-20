# Runbook: imtahan günü

Kim üçün: imtahanı açan müəllim, gözətçilər (proktor), dekanlıq və növbətçi admin. Kod: `backend/zeka/modules/exam/`,
gözətçi paneli `/proctor`. İmtahanın jurnalı hash zənciridir (Task 30): hər addım `exam_events`-də qalır.
`C` aşağıda `docker compose -f infra/compose.yml` deməkdir.

## 24 saat əvvəl

| # | Yoxlama | Əmr və ya yer | Gözlənən |
|---|---|---|---|
| 1 | Host saatı sinxrondur | `timedatectl show -p NTPSynchronized --value` | `yes` |
| 2 | Saat qurşağı | `$C exec app python -c "import time; print(time.strftime('%z'))"` | `+0400` |
| 3 | Gözləyən miqrasiya yoxdur | `$C exec app python backend/manage.py status` | Hamısı tətbiq olunub |
| 4 | Dünənki backup var və açılır | `infra/restore.sh backups/latest.enc /tmp/restore-check`, sonra qovluğu silin | Kod 0 |
| 5 | Dövri işlər işləyir | `$C exec app python backend/manage.py jobs status` | `exam.autosubmit` son dəqiqədə `ok` |
| 6 | Pəncərə, plan və suallar | Müəllimin fənn səhifəsi → İmtahanlar | Başlama və bitmə yerli vaxtla düzgündür; hovuzda planın istədiyi qədər sual var |
| 7 | Siyahı və buraxılış | Dekanlıq: buraxılmayanların səbəbi; istisna lazımdırsa indi əlavə olunur (auditli) | Hər tələbənin statusu bəllidir |
| 8 | Gözətçilər | Fənn səhifəsində gözətçilər (`PUT /api/exams/{id}/proctors`) | Hər zal üçün ən azı bir gözətçi |
| 9 | Şəbəkə siyahısı | İmtahanın şəbəkə siyahısında zalın ünvanları | Zaldakı kompüterdən giriş açılır, kənardan `net.refused` |
| 10 | SEB (seçilibsə) | Zaldakı bir kompüterdə `.seb` faylı ilə sınaq girişi | Səhifə açılır; SEB-siz brauzer 403 alır |
| 11 | Kağız ehtiyat | Hər zal üçün sualların çap nüsxəsi möhürlü zərfdə, cavab vərəqləri | Zərf dekanlıqdadır |

Yük: 300 tələbə bir prosesdə sınaqdan keçib (`docs/perf/baseline.md`). Daha böyük imtahan üçün `ZEKA_WORKERS` nüvə
sayına qədər artırılır.

## Başlanğıc (T−30 dəqiqə)

1. `timedatectl show -p NTPSynchronized --value` → `yes`. `curl -s https://<ad>/healthz` → 200.
2. Müəllim imtahanı açır (İmtahanlar → Aç). Siyahı bir dəfə çəkilir: açandan sonra gələn tələbə yalnız dekanlığın
   istisnası ilə girir.
3. Gözətçi `/proctor` səhifəsini açır. Panel hər 5 saniyədə yenilənir.
4. Tələbə portalda imtahana daxil olur. Bu, tələbənin bütün digər sessiyalarını bağlayır.

## Gediş

| Hadisə | Gözətçinin hərəkəti | Qeyd |
|---|---|---|
| Tələbənin kompüteri dondu | Başqa kompüterdə yenidən daxil olsun. Cavablar serverdədir | Yeni giriş köhnə sessiyanı bağlayır (`session.takeover`) |
| İnternet qısa kəsildi | Heç nə. Səhifə cavabları yaddaşda saxlayır və bərpada göndərir | Göndərilməmiş cavab varsa, əl ilə təhvil vermə rədd olunur |
| Əlavə vaxt | Panel → tələbə → `extend`, səbəb məcburidir | Hadisə zəncirdə və auditdə |
| Fasilə (tibbi və s.) | `pause`, sonra `resume`. Fasilədə saat dayanır, cavab qəbul olunmur | |
| Pozuntu | `end`, səbəb ilə. Protokola düşür | |
| Səhvən bitirilib | `reopen` | |
| Giriş bloklanıb | `unlock` | |
| Zalın ünvanı dəyişib | Siyahıdakı ünvandırsa `net.changed` (xəbərdarlıq); deyilsə giriş rədd olunur | Şəbəkə siyahısını müəllim düzəldir |

Vaxt bitəndə `exam.autosubmit` işi gecikmiş cəhdləri hər dəqiqə təhvil verir. Server saatı əsasdır.

## İnsident

- **Server cavab vermir.** Növbətçi admin: `$C ps`, `$C logs --tail 200 app`, sonra `$C restart app`. Cavablar
  bazadadır, cəhdin vaxtı serverdə davam edir. Kəsilmə 10 dəqiqədən çoxdursa, müəllim hər tələbəyə eyni əlavə vaxt
  verir (`extend`, səbəb "server kəsintisi").
- **30 dəqiqədən çox kəsilmə və ya baza zədəsi.** Kağız ehtiyata keçin: dekanlıq zərfi açır, qalan vaxt kağızda davam
  edir. Onlayn cəhdlər olduğu kimi qalır. Kağız nəticələri dekanlıq sonra bal dəyişikliyi ilə yazır (səbəb və əmr nömrəsi).
- **Şübhəli dəyişiklik.** `$C exec app python backend/manage.py exam-verify <id>`: qırılan halqanı, dəyişmiş cavabı və
  ya balı göstərir.
- Hər insident `docs/runbooks/incident.md` ilə qeydə alınır.

## Bağlanış

1. Müəllim imtahanı bağlayır. Hər cəhd qiymətləndirilir, protokol (QR sənəd) yaradılır, zəncirin kökü müəllimə və
   dekanlıqlara e-poçtla gedir.
2. Kökü olan məktubu silməyin: o, bazadan kənarda saxlanan sübutdur.
3. Protokolu çap edin. Müəllim və gözətçilər imzalayır. İmzalı nüsxə dekanlığa verilir.
4. Backup: `$C run --rm -T backup`. Kod 0 olmalıdır.
5. Yoxlama: `$C exec app python backend/manage.py exam-verify <id> --root <məktubdakı kök>`. Problem olmamalıdır.
6. Nəticələrin açıqlanması (İmtahanlar → Açıqla) və qrup cədvəllərinin bağlanması (dekanlıq) ayrıca addımlardır.

## Sınaq icrası

Saat, backup, bərpa və `exam-verify` addımları 2026-11-20-də sınaq konteynerində işlədilib. Çıxış
`docs/runbooks/restore-log.md`-dədir. Hədəf serverdə və real zalda SEB ilə ilk icra Task 44-dədir.
