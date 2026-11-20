"""HTTP routes of the accreditation evidence (tasks/todo.md, Task 39); the dashboard's tiles reach it in /api/analytics."""
from __future__ import annotations

from ...core.web import Response
from ...legacy.common import R
from . import service


@R("GET", "/api/insight/evidence", roles=("leader", "admin"))
def evidence(req):
    """The live counts per accreditation indicator; ``?format=csv`` for a spreadsheet."""
    if req.query.get("format") != "csv":
        return service.evidence(req.db, req.user["role"])
    return Response(service.evidence_csv(req.db, req.user["role"], req.lang), 200, "text/csv; charset=utf-8",
                    [("Content-Disposition", 'attachment; filename="akkreditasiya-subutu.csv"'), ("Cache-Control", "private, no-store")])
