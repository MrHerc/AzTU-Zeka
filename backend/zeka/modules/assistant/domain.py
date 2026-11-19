"""The rules of a knowledge base article (tasks/todo.md, Task 32). No I/O."""
from __future__ import annotations

from datetime import date

from ...core.i18n import E

STATUSES = ("published", "draft", "archived")


def kb_input(body, request_codes: set[str]) -> tuple[dict, dict | None]:
    """(values, problem) of an article: a heading, a text, the source document (and its clause), an optional e-service
    the answer offers with its button label, a date by which it is reviewed again, and its status."""
    v = {"heading": " ".join(body.text("heading", 400).split()), "text": body.text("text", 9000),
         "request": body.text("request", 60) or None, "action_label": " ".join(body.text("action_label", 120).split()) or None,
         "source": " ".join(body.text("source", 400).split()) or None, "source_ref": " ".join(body.text("source_ref", 200).split()) or None,
         "review_at": body.text("review_at", 20) or None, "status": body.text("status", 20) or "published"}
    if not 3 <= len(v["heading"]) <= 200:
        return v, E("Başlıq 3–200 simvol olmalıdır")
    if not 20 <= len(v["text"]) <= 8000:
        return v, E("Mətn 20–8000 simvol olmalıdır")
    if not v["source"] or len(v["source"]) > 200:
        return v, E("Mənbə sənədi göstərilməlidir (ən çox 200 simvol)")
    if v["source_ref"] and len(v["source_ref"]) > 120:
        return v, E("Bənd ən çox 120 simvoldur")
    if v["request"] and v["request"] not in request_codes:
        return v, E("Belə e-xidmət yoxdur")
    if v["action_label"] and (not v["request"] or len(v["action_label"]) > 60):
        return v, E("Düymənin adı yalnız e-xidmətlə və ən çox 60 simvol olur")
    if v["review_at"]:
        try:
            date.fromisoformat(v["review_at"])
        except ValueError:
            return v, E("Yenidən baxış tarixi YYYY-MM-DD formatında olmalıdır")
    if v["status"] not in STATUSES:
        return v, E("Status düzgün deyil")
    return v, None
