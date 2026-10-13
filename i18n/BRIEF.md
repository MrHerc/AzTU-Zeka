# Translation brief — Zəka (AzTU digital campus), Azerbaijani → English + Russian

You translate ONE chunk file of UI/content strings. Source language: Azerbaijani (the key). Product: AI-powered digital campus portal
for Azerbaijan Technical University (AzTU) — students, teachers, dean's office, leadership. Tone: professional, clear, concise,
natural for each language (never word-for-word). Same meaning and level of formality as the source.

## Files
- Input: `i18n\todo\<chunk>.json` (relative to the project root) — object `{ "<Azerbaijani source>": "<where it is used>" }`.
  The value is only context (file:line or content area) — do not translate it.
- Output (create both): `i18n\en\<chunk>.json` and `i18n\ru\<chunk>.json`
  Flat objects `{ "<exact Azerbaijani source key>": "<translation>" }` with **every** key of the input, keys byte-identical
  (copy them, do not retype or normalise quotes/dashes/spaces). UTF-8, valid JSON (escape `"` and `\n` correctly).
- Large chunks: write the file in 2–4 parts (create, then append by rewriting the file with more keys) if needed, but the final file
  must be one JSON object.

## Rules
1. Placeholders `{name}` must appear in the translation exactly as in the source (same names, same count). Never translate them.
2. Plurals: when the source contains `{n}` and a noun/verb depends on the number, output an object instead of a string:
   - English: `{"one": "{n} question", "other": "{n} questions"}`
   - Russian: `{"one": "{n} вопрос", "few": "{n} вопроса", "many": "{n} вопросов"}` (one: 1,21,31…; few: 2–4,22–24…; many: 0,5–20,25…)
   Every form must contain `{n}` if the source does. If no agreement is needed (e.g. "Qiymət: {n}") a plain string is fine.
3. Keep markdown and markup exactly: `**bold**` pairs, `*italic*`, `` `code` ``, `[1]` citations, `\n` line breaks, `→`, `·`, `—`,
   `…`, emojis, URLs, e-mail addresses, file extensions, keyboard keys (Ctrl, Esc, `[`).
4. Keep unchanged: brand and product names (AzTU, Zəka, Safarov Industries, ADEX, THE, QS, UI GreenMetric, Springer Nature, Moodle,
   CodeRunner, GitHub, Kahoot, Mentimeter, Falstad, GeoGebra, MATLAB, Python, LLM, SSO, LMS, NPS, CSV, PDF, QR, ECTS), course codes
   (ELM-2105…), group names (İT-25-1), people's names (keep Azerbaijani spelling: Aysel Məmmədova, Rauf Əliyev…), demo usernames.
   Translate academic titles: Dos. → Assoc. Prof. / доц.; Prof. → Prof. / проф.; Baş müəllim → Senior Lecturer / старший преподаватель.
5. Interface conventions
   - English (UK spelling: organise, enrol, centre, programme): buttons/menu actions = short imperative ("Send", "Save", "Cancel",
     "Open", "Download", "Print"), headings/tabs = nouns ("My requests"), sentences in plain professional English, sentence case.
   - Russian: buttons = infinitive ("Отправить", "Сохранить", "Отменить", "Открыть", "Скачать", "Печать"), instructions = formal
     imperative with lowercase "вы" ("Выберите файл", "Загрузите справку"), headings = nouns, sentence case, «ёлочки» for quotes.
   - Keep strings about the same length; UI labels must stay short. Keep trailing/leading punctuation and spaces as in the source.
6. Strings that are only a code, number, brand or symbol: copy unchanged.
7. Demo/synthetic content (news, sample tickets, academy lessons, tool descriptions, service descriptions, FAQ, guides) is real UI
   content for the demo — translate it fully and naturally. Course materials are not in your files.

## Glossary (AZ → EN → RU) — use consistently
fənn → course → дисциплина · fənlərim → my courses → мои дисциплины · test → test → тест · Test studiyası → Test Studio → Студия тестов
məşq testi → practice test → тренировочный тест · qiymətli test → graded test → оцениваемый тест · cəhd → attempt → попытка
e-xidmətlər → e-services → электронные услуги · müraciət → request → заявка · müraciətlərim → my requests → мои заявки
arayış → certificate (enrolment certificate) → справка · sənəd → document → документ · sənəd reyestri → document registry → реестр документов
dəstək xidməti → support → служба поддержки · dəstək sorğusu → support ticket → обращение в поддержку · rəy → feedback → отзыв
davamiyyət → attendance → посещаемость · qayıb → absence → пропуск · üzrlü → excused → по уважительной причине · həkim arayışı → medical certificate → медицинская справка
qiymətlər → grades → оценки · bal → points → баллы · qiymətləndirmə → assessment → оценивание · kollokvium → colloquium (midterm) → коллоквиум
dərs cədvəli → timetable → расписание · mühazirə → lecture → лекция · məşğələ → seminar → практическое занятие · laboratoriya → laboratory → лабораторная
dekanlıq → dean's office → деканат · tədris hissəsi → academic office → учебная часть · rəhbərlik → leadership → руководство · rektorluq → rector's office → ректорат
bildiriş → notification → уведомление · nailiyyətlər → achievements → достижения · əlaqə → contact → контакты
bələdçi → guide → гид · Bələdçi mərkəzi → Help centre → Справочный центр · səhifə bələdçisi → page guide → гид по странице · tanışlıq turu → welcome tour → ознакомительный тур
AI tutor → AI tutor → ИИ-тьютор · kampus köməkçisi → campus assistant → помощник по кампусу · Sokratik / İzah / Məşq → Socratic / Explain / Practice → Сократический / Объяснение / Практика
material → material → материал · sillabus → syllabus → силлабус · AI Akademiya → AI Academy → AI-академия · texnoloji həllər → tech tools → технологические решения
icra müddəti → deadline → срок исполнения · qaralama → draft → черновик · təsdiqlə → approve → утвердить · rədd et → reject → отклонить · dərc et → publish → опубликовать
tələbə → student → студент · müəllim → teacher → преподаватель · kafedra → department → кафедра · fakültə → faculty → факультет · ixtisas → programme (specialty) → специальность
semestr → semester → семестр · tədris ili → academic year → учебный год · kredit (AKTS) → credits (ECTS) → кредиты (ECTS)
Dövlət sifarişi → state-funded → бюджет · Ödənişli → fee-paying → платное обучение · Əyani → full-time → очная форма · Qiyabi → part-time → заочная форма
akademik məzuniyyət → academic leave → академический отпуск · yataqxana → dormitory → общежитие · təqaüd → scholarship → стипендия · tələbə bileti → student ID card → студенческий билет
təcili / yüksək / normal / aşağı (prioritet) → urgent / high / normal / low → срочный / высокий / обычный / низкий
Universitet hesabı (SSO) → university account (SSO) → учётная запись университета (SSO) · pilot mərhələsi → pilot phase → пилотный этап

## Done = 
Both output files exist, are valid JSON, contain every input key exactly, placeholders identical, plural objects where needed.
Validate with a small Python script (json.load + key set equality + `re.findall(r"\{(\w+)\}")` comparison per key) and report
counts. Do not edit any other file.
