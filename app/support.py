"""Support desk and feedback: vocabularies, SLA rules and synthetic demo data."""
from __future__ import annotations

import random
from datetime import timedelta

from .i18n import S_

CATEGORIES = [
    ("account", "user", S_("Hesab və giriş")),
    ("learning", "book", S_("Dərslər və materiallar")),
    ("ai", "sparkles", S_("AI tutor və köməkçi")),
    ("services", "grid", S_("E-xidmətlər və sənədlər")),
    ("technical", "alert", S_("Texniki nasazlıq")),
    ("suggestion", "star", S_("Təklif və ideya")),
    ("university", "building", S_("Universitetə sual")),
    ("other", "help", S_("Digər")),
]
PRIORITIES = [("low", S_("Aşağı")), ("normal", S_("Normal")), ("high", S_("Yüksək")), ("urgent", S_("Təcili"))]
STATUSES = [("open", S_("Yeni")), ("in_progress", S_("İcrada")), ("waiting", S_("Cavabınız gözlənilir")),
            ("resolved", S_("Həll olunub")), ("closed", S_("Bağlanıb"))]
SLA_HOURS = {"urgent": 4, "high": 8, "normal": 24, "low": 72}
AREAS = [("overall", S_("Ümumi təəssürat")), ("tutor", S_("AI tutor")), ("services", S_("E-xidmətlər")),
         ("schedule", S_("Cədvəl və davamiyyət")), ("quizzes", S_("Testlər")), ("news", S_("Xəbərlər və tədbirlər")),
         ("academy", S_("AI Akademiya")), ("design", S_("Dizayn və rahatlıq")), ("mobile", S_("Mobil versiya"))]
SCORE_LABELS = [S_("Çox pis"), S_("Pis"), S_("Orta"), S_("Yaxşı"), S_("Əla")]
OPEN = ("open", "in_progress", "waiting")
CODES = {"category": {k for k, _, _ in CATEGORIES}, "priority": {k for k, _ in PRIORITIES}, "status": {k for k, _ in STATUSES},
         "area": {k for k, _ in AREAS}}

_SYN_TICKETS = [
    ("account", "normal", "Profildə qrupum köhnə göstərilir", "Qrupum dəyişib, amma profildə hələ köhnə qrup görünür."),
    ("ai", "low", "Tutor bəzən ingiliscə termin işlədir", "İzah rejimində bəzi terminlər ingilis dilində qalır, azərbaycanca qarşılığını da yazmaq olar?"),
    ("services", "high", "Yataqxana müraciətinə cavab gəlmir", "Müraciətimi 5 gün əvvəl göndərmişəm, status dəyişməyib."),
    ("technical", "urgent", "Test zamanı səhifə yeniləndi", "Testin ortasında səhifə yeniləndi, cavablarım saxlanıldımı?"),
    ("learning", "normal", "Mühazirə materialı açılmır", "Fizika I fənnində 3-cü mövzunun materialı açılmır."),
    ("suggestion", "low", "Cədvəli telefona əlavə etmək", "Dərs cədvəlini telefonun təqviminə ixrac etmək imkanı olsa, çox rahat olardı."),
    ("university", "normal", "Kitabxananın iş saatları", "Kitabxana şənbə günləri işləyirmi?"),
    ("services", "normal", "Transkriptin ingiliscə variantı", "Transkriptin ingilis dilində variantını necə ala bilərəm?"),
    ("technical", "high", "Bildirişlər gəlmir", "Son iki gündə heç bir bildiriş almamışam."),
    ("ai", "normal", "Kampus köməkçisi təqaüd barədə", "Təqaüdün məbləği barədə sualıma cavab tapılmadı."),
    ("account", "low", "Profil şəklini dəyişmək", "Profil şəklini necə dəyişə bilərəm?"),
    ("suggestion", "normal", "Qaranlıq rejim üçün təşəkkür", "Qaranlıq rejim gözəl alınıb, avtomatik keçid də əlavə olunsa yaxşı olar."),
    ("learning", "normal", "Testin nəticəsi göstərilmir", "Məşq testini bitirdim, amma nəticə səhifəsi boş açıldı."),
    ("services", "low", "Tələbə biletinin bərpası", "Tələbə biletimi itirmişəm, bərpası nə qədər çəkir?"),
]
_SYN_COMMENTS = {
    5: ["Çox rahatdır, arayışı 10 dəqiqəyə aldım.", "AI tutor mövzunu addım-addım izah edir, çox faydalıdır.", "Hər şey bir yerdədir, əla!",
        "Bildirişlər vaxtında gəlir.", "Mobil versiya da çox rahatdır."],
    4: ["Yaxşıdır, amma bəzi cavablar uzundur.", "Cədvəl çox rahatdır, təqvimə ixrac da olsa əla olar.", "Test nəticələri aydın göstərilir.",
        "Dizayn təmiz və anlaşıqlıdır."],
    3: ["Bəzi bölmələri tapmaq çətin oldu.", "Tutor bəzən materialda olmayan suala cavab vermir — bu normaldır, amma alternativ göstərsin."],
    2: ["Fayl yükləyərkən xəta aldım.", "Bəzi düymələr kiçikdir."],
    1: ["Səhifə yavaş açıldı."],
}


def seed(c, uid: dict, t0):
    """Demo tickets and feedback. Everything here is synthetic (synthetic=1)."""
    from .store import iso, rows
    rng = random.Random(42)
    staff_admin = uid.get("admin") or next(iter(uid.values()))
    staff_office = uid.get("nigar") or staff_admin

    def ticket(user, cat, prio, subject, body, status, created, msgs=(), rating=None, assignee=None, synthetic=0, page=""):
        closed = iso(created + timedelta(days=1)) if status in ("resolved", "closed") else None
        tid = c.execute("INSERT INTO support_tickets(user_id,category,priority,subject,body,page,status,assignee_id,rating,created_at,updated_at,closed_at,synthetic)"
                        " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (user, cat, prio, subject, body, page, status, assignee, rating, iso(created),
                         iso(created + timedelta(hours=len(msgs) * 3 + 1)), closed, synthetic)).lastrowid
        for i, (author, text, internal) in enumerate(msgs):
            c.execute("INSERT INTO support_messages(ticket_id,author_id,text,internal,created_at) VALUES(?,?,?,?,?)",
                      (tid, author, text, 1 if internal else 0, iso(created + timedelta(hours=2 + i * 3))))
        return tid

    aysel, rauf = uid.get("aysel"), uid.get("rauf")
    if aysel:
        ticket(aysel, "ai", "normal", "Tutor cavabında mənbəyə keçid açılmır",
               "Elektrik dövrələri fənnində tutorun cavabındakı [2] mənbəsinə klik edəndə pəncərə açılmır.", "resolved",
               t0 - timedelta(days=9), [(staff_admin, "Salam, Aysel xanım. Problem aradan qaldırıldı — mənbə indi yan paneldə açılır. Bildirdiyiniz üçün təşəkkür edirik.", False)],
               rating=5, assignee=staff_admin, page="/student/tutor/1")
        ticket(aysel, "services", "high", "Arayışda ata adım səhv yazılıb",
               "Bank üçün aldığım arayışda ata adım səhv göstərilib. Düzəliş etmək mümkündürmü?", "in_progress",
               t0 - timedelta(hours=26), [(staff_office, "Məlumatlarınızı reyestrlə tutuşdururuq. Düzəliş edilmiş arayış 1 iş günü ərzində hazır olacaq.", False),
                                          (staff_office, "Reyestrdə ata adı düzgündür — sənəd şablonunda yoxlama aparılır.", True)],
               assignee=staff_office, page="/student/requests")
    if rauf:
        ticket(rauf, "learning", "normal", "PPTX faylından mətn tam çıxarılmır",
               "“Dəyişən cərəyan” mühazirəsini PPTX formatında yüklədim, amma bəzi slaydların mətni tutorda görünmür.", "waiting",
               t0 - timedelta(days=2), [(staff_admin, "Görünür, həmin slaydlarda mətn şəkil kimi yerləşdirilib. Faylı DOCX formatında yükləyə bilərsinizmi? Nəticəni bizə yazın.", False)],
               assignee=staff_admin, page="/teacher/courses")

    synth_users = [r["id"] for r in rows(c, "SELECT id FROM users WHERE synthetic=1 AND role IN ('student','teacher') LIMIT 80")]
    for i, (cat, prio, subject, body) in enumerate(_SYN_TICKETS):
        if not synth_users:
            break
        status = rng.choice(["open", "open", "in_progress", "waiting", "resolved", "resolved", "closed"])
        created = t0 - timedelta(days=rng.uniform(0.2, 20))
        msgs = []
        assignee = None
        if status != "open":
            assignee = staff_office if cat in ("services", "university") else staff_admin
            msgs.append((assignee, "Müraciətiniz qəbul olundu, araşdırırıq.", False))
        ticket(rng.choice(synth_users), cat, prio, subject, body, status, created, msgs,
               rating=rng.choice([4, 5, 5]) if status in ("resolved", "closed") else None, assignee=assignee, synthetic=1)

    voters = rows(c, "SELECT id, role FROM users WHERE synthetic=1 AND role IN ('student','teacher')")
    areas = [a for a, _ in AREAS]
    for i in range(140):
        if not voters:
            break
        v = rng.choice(voters)
        score = rng.choices([5, 4, 3, 2, 1], weights=[48, 32, 12, 5, 3])[0]
        nps = max(0, min(10, round(score * 2 + rng.uniform(-1.5, 0.6)))) if rng.random() < 0.7 else None
        comment = rng.choice(_SYN_COMMENTS[score]) if rng.random() < 0.35 else ""
        area = rng.choice(areas[1:]) if rng.random() < 0.75 else "overall"
        when = t0 - timedelta(days=rng.uniform(0, 56), hours=rng.uniform(0, 10))
        c.execute("INSERT INTO feedback(user_id,role,area,score,nps,comment,page,lang,created_at,synthetic) VALUES(?,?,?,?,?,?,?,?,?,1)",
                  (v["id"], v["role"], area, score, nps, comment, "", "az", iso(when)))
