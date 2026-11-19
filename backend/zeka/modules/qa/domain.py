"""The rules of a course forum (tasks/todo.md, Task 33). No I/O."""
from __future__ import annotations

from ...core.i18n import E, S_

ANONYMOUS = S_("Anonim tələbə")
FAQ_TITLE = S_("Fənnin FAQ-ı")


def topic_input(body) -> tuple[dict, dict | None]:
    v = {"title": " ".join(body.text("title", 300).split()), "text": body.text("text", 5000), "tag": " ".join(body.text("tag", 80).split()) or None,
         "anonymous": bool(body.get("anonymous") is True)}
    if not 5 <= len(v["title"]) <= 140:
        return v, E("Başlıq 5–140 simvol olmalıdır")
    if not 10 <= len(v["text"]) <= 4000:
        return v, E("Sualı 10–4000 simvolla yazın")
    if v["tag"] and len(v["tag"]) > 40:
        return v, E("Etiket ən çox 40 simvoldur")
    return v, None


def reply_input(body) -> tuple[str, dict | None]:
    text = body.text("text", 5000)
    return text, (None if 2 <= len(text) <= 4000 else E("Cavabı 2–4000 simvolla yazın"))


def report_input(body) -> tuple[str, dict | None]:
    reason = " ".join(body.text("reason", 400).split())
    return reason, (None if 3 <= len(reason) <= 300 else E("Şikayətin səbəbini 3–300 simvolla yazın"))


def faq_text(topic: dict, answer: str) -> str:
    """The FAQ section the tutor searches and cites: the question and the teacher's accepted answer."""
    return f"{topic['text'].strip()}\n\n{answer.strip()}"
