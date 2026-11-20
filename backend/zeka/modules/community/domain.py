"""The rules of clubs and channels (tasks/todo.md, Task 35). No I/O."""
from __future__ import annotations

from ...core.i18n import E, S_

DEFAULT_CHANNELS = ((S_("Ümumi"), "chat"), (S_("Elanlar"), "announce"))
MAX_MESSAGE = 2000
PAGE = 100                       # messages per poll
MAX_MUTE_MIN = 30 * 24 * 60


def club_input(body) -> tuple[dict, dict | None]:
    v = {"name": " ".join(body.text("name", 200).split()), "description": body.text("description", 2000)}
    if not 3 <= len(v["name"]) <= 80:
        return v, E("Klubun adı 3–80 simvol olmalıdır")
    if not 10 <= len(v["description"]) <= 1000:
        return v, E("Təsvir 10–1000 simvol olmalıdır")
    return v, None


def message_input(body) -> tuple[str, dict | None]:
    text = body.text("text", MAX_MESSAGE + 100)
    return text, (None if 1 <= len(text) <= MAX_MESSAGE else E("Mesaj 1–2000 simvol olmalıdır"))


def mute_input(body) -> tuple[dict, dict | None]:
    v = {"minutes": body.integer("minutes", 0), "reason": " ".join(body.text("reason", 400).split())}
    if not 5 <= v["minutes"] <= MAX_MUTE_MIN:
        return v, E("Susdurma 5 dəqiqədən 30 günə qədərdir")
    if not 3 <= len(v["reason"]) <= 300:
        return v, E("Səbəbi 3–300 simvolla yazın")
    return v, None


def reason_input(body) -> tuple[str, dict | None]:
    reason = " ".join(body.text("reason", 400).split())
    return reason, (None if 3 <= len(reason) <= 300 else E("Səbəbi 3–300 simvolla yazın"))
