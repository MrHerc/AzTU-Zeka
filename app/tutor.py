"""Conversational layer of the demo AI: grounded tutor / campus answers and practice prompts.

All user-facing phrasing goes through ``S()`` so it is available in Azerbaijani, English and Russian.
Quotations from course material stay in the material's own language (and are always cited).
"""
from __future__ import annotations

import re

from .engine import (Cites, _NUM_EXAMPLE, _is_example, _pick, _socratic_level, code_blocks, formulas, glossary,
                     llm_chat, plain, split_sentences, terms, top_sentences)
from .i18n import L, S, S_

_DIRECT = re.compile(r"(cavab\w* (de|yaz|ver|göstər)|hazır cavab|həll\w* (yaz|ver|de|göstər)|sadəcə cavab|tam həll|"
                     r"give me the answer|just (give|tell)( me)? the answer|full solution|solve it for me|"
                     r"дай(те)? ответ|просто ответ|полное решение|реши(те)? (за меня|задачу)|скажи(те)? ответ)", re.I)
_GREET = re.compile(r"^(salam|hello|hi|hey|good (morning|afternoon|evening)|sabahınız xeyir|günortanız xeyir|axşamınız xeyir|"
                    r"привет|здравствуй(те)?|добрый (день|вечер)|доброе утро)\b", re.I)
_THANKS = re.compile(r"(sağ ol|təşəkkür|thank|спасибо|благодарю)", re.I)
LANG_NAME = {"az": "Azerbaijani", "en": "English", "ru": "Russian"}
LETTERS = "ABCD"


def compose_tutor(mode: str, question: str, hits: list[dict], history: list[dict], course: dict, lang: str = "az") -> dict:
    """Offline grounded answer. hits: [{id, heading, text, material, score}]"""
    s = lambda text, **k: S(text, lang, **k)  # noqa: E731
    q = question.strip()
    if _GREET.match(q) and len(q) < 40:
        return {"text": s("Salam! Mən **{course}** fənni üzrə AI tutorunuzam.\n\n"
                          "- Cavablarım yalnız müəllimin yüklədiyi materiallara əsaslanır və hər birində mənbə göstərilir.\n"
                          "- **Sokratik** rejimdə hazır cavab vermirəm — mövzunu addım-addım birlikdə araşdırırıq.\n"
                          "- **İzah** rejimi mövzunu qısa izah edir, **Məşq** rejimi isə sual verib cavabınızı yoxlayır.\n\n"
                          "Hansı mövzudan başlayaq?", course=L(course["name"], lang)),
                "cites": [], "meta": {"mode": mode, "kind": "greeting"}}
    if _THANKS.search(q) and len(q) < 60:
        return {"text": s("Buyurun. Başqa sualınız olarsa, kömək etməyə hazıram. Mövzunu möhkəmləndirmək üçün **Məşq** rejimindən istifadə edə bilərsiniz."),
                "cites": [], "meta": {"mode": mode, "kind": "thanks"}}
    if not hits or hits[0]["score"] < 1.2:
        return {"text": s("Bu sualın cavabını fənn materiallarında tapmadım.\n\n"
                          "Dəqiqliyi qorumaq üçün yalnız müəllimin yüklədiyi materiallara əsaslanıram. "
                          "Sualı başqa sözlərlə yazın və ya **“Müəllimə göndər”** düyməsi ilə müəllimə ünvanlayın."),
                "cites": [], "meta": {"mode": mode, "no_source": True}}

    # Concept passages first; worked examples are kept for the later hint step.
    concept = [h for h in hits if not _is_example(h)]
    examples = [h for h in hits if _is_example(h)]
    ordered = (concept + examples) or hits
    c = Cites(ordered)
    top = ordered[0]
    topic = re.sub(r"\s*\(\d+\)$", "", top["heading"])
    sents = top_sentences(ordered, q, 3)
    fs = [(i, f) for i, h in enumerate(ordered[:2]) for f in formulas(h["text"]) if not _is_example(h)]
    codes = [(i, cb) for i, h in enumerate(ordered[:2]) for cb in code_blocks(h["text"])]
    gl = [g for h in ordered[:2] for g in glossary(h["text"])]
    qset = set(terms(q))
    term = next((t for t, _ in gl if set(terms(t)) & qset), gl[0][0] if gl else None)

    if mode == "explain":
        parts = [s("**{topic}** — materiallar əsasında qısa izah:", topic=topic) + "\n"]
        for hi, sent in sents:
            parts.append(f"- {sent} {c.ref(hi)}")
        if fs:
            hi, f = fs[0]
            parts.append("\n" + s("Əsas düstur:") + f"\n\n> {f}\n\n" + s("Mənbə: {ref}", ref=c.ref(hi)))
        elif codes:
            hi, cb = codes[0]
            parts.append("\n" + s("Nümunə kod {ref}:", ref=c.ref(hi)) + f"\n\n```python\n{cb}\n```")
        if len(gl) >= 2:
            check = s("**{a}** ilə **{b}** arasındakı fərqi öz sözlərinizlə izah edə bilərsinizmi?", a=gl[0][0], b=gl[1][0])
        elif fs:
            check = s("Düsturdakı kəmiyyətlərdən biri iki dəfə artarsa, nəticə necə dəyişər?")
        else:
            check = s("Mövzunu bir nümunə ilə izah etməyə çalışın, sonra **Məşq** rejimində özünüzü yoxlayın.")
        parts.append("\n" + s("**Özünüzü yoxlayın:** {check}", check=check))
        return {"text": "\n".join(parts), "cites": c.order, "meta": {"mode": mode, "topic": topic}}

    # --- Socratic (default)
    level = _socratic_level(history, topic)
    direct = bool(_DIRECT.search(q))
    problem = bool(re.search(r"\d", q))
    intro = s("Sokratik rejimdə hazır cavab vermirəm — məqsəd məsələni özünüzün həll etməyinizdir. Gəlin addım-addım irəliləyək.") + "\n\n" if direct else ""
    hint_pool = [x for x in sents if not _NUM_EXAMPLE.search(x[1])] or sents
    hi, key = hint_pool[0] if hint_pool else (0, plain(top["text"])[:220])
    if level == 0:
        if problem:
            ask = s("Məsələdə hansı kəmiyyətlər verilib və hansını tapmaq lazımdır? Onları ayrıca yazın və hansı qanunun tətbiq olunduğunu düşünün.")
        else:
            cw = term or topic
            ask = _pick([s("Sizcə, burada hansı qanun və ya qayda tətbiq olunur? **{c}** ilə necə bağlıdır?", c=cw),
                         s("**{c}** anlayışını öz sözlərinizlə necə izah edərdiniz?", c=cw),
                         s("**{c}** haqqında artıq nə bilirsiniz? Bir-iki cümlə ilə yazın.", c=cw)], q)
        text = intro + s("Gəlin birlikdə düşünək.\n\n**1-ci addım.** {ask}\n\n**İpucu.** Materialda deyilir: “{key}” {ref}\n\n"
                         "Cavabınızı yazın — sonra növbəti addıma keçəcəyik.", ask=ask, key=key, ref=c.ref(hi))
    elif level == 1:
        if fs:
            fhi, f = fs[0]
            text = intro + s("Davam edək. **2-ci addım.** Mövzunun əsas əlaqəsi:\n\n> {f}\n\nMənbə: {ref}\n\n"
                             "Məlum qiymətləri yerinə qoysanız, nə alınır? Vahidlərə diqqət edin.", f=f, ref=c.ref(fhi))
        else:
            nxt = hint_pool[1] if len(hint_pool) > 1 else (hi, key)
            text = intro + s("Davam edək. **2-ci addım.** Bu fikrə diqqət edin: “{s}” {ref}\n\n"
                             "Bu, sizin məsələnizə necə tətbiq olunur? Həll addımınızı yazın.", s=nxt[1], ref=c.ref(nxt[0]))
    elif level == 2:
        if examples:
            ei = ordered.index(examples[0])
            exs = " ".join(split_sentences(examples[0]["text"])[:2])
            text = intro + s("**3-cü addım.** Materialdakı oxşar nümunənin şərtinə baxın: “{ex}” {ref}\n\n"
                             "Həllə baxmadan əvvəl eyni məntiqi öz məsələnizə tətbiq edin və nəticəni yazın — birlikdə yoxlayaq.",
                             ex=exs, ref=c.ref(ei))
        else:
            text = intro + s("**3-cü addım.** Əldə etdiklərinizi birləşdirib yekun nəticəni yazın. Vahidlərin uyğunluğunu və "
                             "qiymətin realistik olduğunu yoxlayın. Mənbəyə yenidən baxa bilərsiniz: {ref}", ref=c.ref(0))
    else:
        text = s("Yaxşı irəliləyirsiniz. Hələ əmin deyilsinizsə, həllinizi **“Müəllimə göndər”** düyməsi ilə müəllimə göndərin — "
                 "o, yoxlayıb şərh edəcək. Mövzunun qısa izahı üçün **İzah** rejiminə keçə bilərsiniz. {ref}", ref=c.ref(0))
    return {"text": text, "cites": c.order, "meta": {"mode": "socratic", "topic": topic, "level": level, "guardrail": direct}}


def compose_campus(question: str, hits: list[dict], lang: str = "az") -> dict:
    s = lambda text, **k: S(text, lang, **k)  # noqa: E731
    q = question.strip()
    if _GREET.match(q) and len(q) < 40:
        return {"text": s("Salam! Mən AzTU-nun kampus köməkçisiyəm. Arayışlar, qiymətləndirmə, akademik məzuniyyət, təqaüd və "
                          "digər qaydalar barədə suallarınızı cavablandırıram."), "cites": [], "actions": [], "meta": {}}
    if not hits or hits[0]["score"] < 1.0:
        return {"text": s("Bu barədə universitetin bilik bazasında məlumat tapılmadı. Sualınızı tədris hissəsinə **sərbəst ərizə** ilə göndərə bilərsiniz."),
                "cites": [], "actions": [{"type": "request", "code": "free_application", "label": s("Sərbəst ərizə yaz")}],
                "meta": {"no_source": True}}
    c = Cites(hits)
    top = hits[0]
    parts = [f"**{top['heading']}**\n"]
    for hi, sent in top_sentences(hits[:2], q, 3):
        parts.append(f"- {sent} {c.ref(hi)}")
    actions = []
    if top.get("request"):
        actions.append({"type": "request", "code": top["request"], "label": top.get("action_label") or s("Müraciət et")})
        parts.append("\n" + s("Müraciəti buradan onlayn göndərə bilərsiniz:"))
    return {"text": "\n".join(parts), "cites": c.order, "actions": actions, "meta": {}}


def llm_tutor(mode: str, question: str, hits: list[dict], history: list[dict], course: dict, lang: str = "az") -> dict:
    style = {"socratic": "Use the Socratic method: NEVER give the final answer to an assignment or problem. Give one hint at a time, "
                         "ask a guiding question and let the student reason.",
             "explain": "Explain the topic clearly and briefly (3-6 bullet points) and finish with one self-check question."}.get(mode, "")
    src = "\n\n".join(f"[{i + 1}] ({h['material']} — {h['heading']})\n{h['text'][:1500]}" for i, h in enumerate(hits[:4]))
    system = (f"You are the AI tutor for the course '{L(course['name'], 'en')}' at Azerbaijan Technical University. "
              "Use ONLY the sources below; never invent facts that are not in them and say so when you do not know. "
              "Cite the source after every factual claim as [n]. Address the student formally. "
              f"Answer in {LANG_NAME.get(lang, 'Azerbaijani')}. {style} Teacher's rules: {course.get('tutor_rules') or '-'}\n\nSOURCES:\n{src}")
    msgs = [{"role": m["role"], "content": m["content"]} for m in history[-6:]]
    msgs.append({"role": "user", "content": question})
    text = llm_chat(system, msgs)
    used = sorted({int(n) for n in re.findall(r"\[(\d)\]", text) if 0 < int(n) <= len(hits[:4])})
    order = [hits[n - 1]["id"] for n in used] or [hits[0]["id"]]
    mapping = {str(n): str(i + 1) for i, n in enumerate(used)}
    text = re.sub(r"\[(\d)\]", lambda m: f"[{mapping.get(m.group(1), m.group(1))}]", text)
    return {"text": text, "cites": order, "meta": {"mode": mode, "topic": hits[0]["heading"], "engine": "llm"}}


def format_practice(q: dict, lang: str = "az") -> str:
    s = lambda text, **k: S(text, lang, **k)  # noqa: E731
    head = f"**{s('Məşq sualı')}** · {q.get('topic') or ''} · {s(q.get('bloom') or '')}\n\n{q['text']}\n"
    if q["qtype"] == "mcq":
        opts = "\n".join(f"- **{LETTERS[i]})** {o}" for i, o in enumerate(q["options"]))
        return f"{head}\n{opts}\n\n" + s("Cavabın hərfini yazın (məsələn, **B**).")
    if q["qtype"] == "tf":
        return f"{head}\n" + s("Cavabınızı yazın: **Doğru** və ya **Yanlış**.")
    return f"{head}\n" + (s("Cavabı ədəd kimi yazın ({unit}).", unit=q["unit"]) if q.get("unit") else s("Cavabı ədəd kimi yazın."))


NEXT_RX = re.compile(r"(davam|novbeti|bir de|yeni sual|sual ver|basla|mesq|next|continue|another|more|далее|дальше|ещ[её]|следующ|продолж)", re.I)
VOCAB = [S_("Doğru"), S_("Yanlış")]
MODES = {"socratic": S_("Sokratik"), "explain": S_("İzah"), "practice": S_("Məşq")}

# English / Russian keywords -> Azerbaijani terms used in the campus knowledge base (retrieval is Azerbaijani-aware).
_XLANG = [
    (r"certificate|reference letter|справк", "arayış"), (r"transcript|транскрипт|выписк", "transkript"),
    (r"academic leave|академическ", "akademik məzuniyyət"), (r"dormitor|hostel|общежит", "yataqxana"),
    (r"scholarship|stipend|стипенд", "təqaüd"), (r"absen|missed class|пропуск|прогул", "qayıb üzrlü"),
    (r"medical|sick|doctor|больни|медицин|врач", "həkim arayışı"), (r"exam|экзамен", "imtahan"),
    (r"resched|postpone|перенос", "imtahanın vaxtının dəyişdirilməsi"), (r"appeal|апелляц", "apellyasiya"),
    (r"student card|id card|студенческ", "tələbə bileti"), (r"tuition|fee|payment|оплат|плат", "təhsil haqqı"),
    (r"grade|score|mark|оценк|балл", "qiymətləndirmə bal"), (r"attendance|посещ", "davamiyyət"),
    (r"transfer|перевод", "köçürmə"), (r"leave|permission|отпуст|разрешен", "icazə"), (r"library|библиотек", "kitabxana"),
]


def expand_query(q: str) -> str:
    low = q.lower()
    extra = [az for rx, az in _XLANG if re.search(rx, low)]
    return q + (" " + " ".join(extra) if extra else "")
