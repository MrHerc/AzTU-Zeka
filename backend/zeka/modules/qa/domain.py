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


# ---------------------------------------------------------------- office hours (Task 34)
SLOT_MINUTES = (10, 15, 20, 30, 45, 60)
BOOK_AHEAD_DAYS = 14
MAX_OPEN_PER_TEACHER = 2          # future bookings a student holds with one teacher: nobody takes a whole week


def _minutes(hhmm: str) -> int | None:
    try:
        h, m = hhmm.split(":")
        if len(h) == 2 and len(m) == 2 and 0 <= int(h) < 24 and 0 <= int(m) < 60:
            return int(h) * 60 + int(m)
    except (ValueError, AttributeError):
        pass
    return None


def _hhmm(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def hours_input(body) -> tuple[dict, dict | None]:
    v = {"weekday": body.integer("weekday", 0), "start": body.text("start", 5), "end": body.text("end", 5), "slot_min": body.integer("slot_min", 15),
         "place": " ".join(body.text("place", 120).split()) or None, "online_url": body.text("online_url", 400) or None}
    a, b = _minutes(v["start"]), _minutes(v["end"])
    if not 1 <= v["weekday"] <= 6:
        return v, E("Həftənin günü bazar ertəsindən şənbəyə qədərdir")
    if a is None or b is None or b <= a or b - a > 360:
        return v, E("Vaxt aralığı SS:DD formatında, ən çox 6 saat olmalıdır")
    if v["slot_min"] not in SLOT_MINUTES or (b - a) < v["slot_min"]:
        return v, E("Görüşün müddəti 10, 15, 20, 30, 45 və ya 60 dəqiqədir və aralığa sığmalıdır")
    if not (v["place"] or v["online_url"]):
        return v, E("Otaq və ya onlayn keçid göstərin")
    if v["place"] and len(v["place"]) > 80:
        return v, E("Otaq ən çox 80 simvoldur")
    if v["online_url"] and (len(v["online_url"]) > 300 or not v["online_url"].startswith("https://")):
        return v, E("Onlayn keçid https:// ilə başlamalıdır")
    return v, None


def slots_of(h: dict) -> list[tuple[str, str]]:
    """The (start, end) slots of one weekly range."""
    a, b = _minutes(h["start"]) or 0, _minutes(h["end"]) or 0
    return [(_hhmm(m), _hhmm(m + h["slot_min"])) for m in range(a, b - h["slot_min"] + 1, h["slot_min"])]


def free_slots(hours: list[dict], booked: set[tuple[str, str]], today, hhmm: str, days: int = BOOK_AHEAD_DAYS) -> list[dict]:
    """The slots from today (later than ``hhmm``) to ``days`` ahead that nobody booked: {hours_id, day, start, end, place,
    online_url}. ``booked``: (day, start) of the teacher's booked slots."""
    from datetime import timedelta
    out = []
    for i in range(days + 1):
        day = today + timedelta(days=i)
        for h in hours:
            if h["weekday"] != day.isoweekday():
                continue
            for start, end in slots_of(h):
                if (day == today and start <= hhmm) or (day.isoformat(), start) in booked:
                    continue
                out.append({"hours_id": h["id"], "day": day.isoformat(), "start": start, "end": end, "place": h["place"], "online_url": h["online_url"]})
    return sorted(out, key=lambda x: (x["day"], x["start"]))
