"""E-services: requests, validation, the dean's office workflow, documents, QR verification, attachments."""
import base64
import urllib.parse
from datetime import date, timedelta

import pytest

from app import store

CERT = {"purpose": "Səfirlik / viza", "lang": "İngilis dili", "copies": "1", "delivery": "Elektron (QR kodlu PDF)"}


def b64(data):
    return base64.b64encode(data).decode()


@pytest.fixture(scope="module")
def cert_request(student):
    r = student.post("/api/requests", {"type_code": "enrollment_certificate", "data": CERT})
    assert r.status == 200, r.text
    return r.json


def test_catalogue(student):
    svc = student.get("/api/services").json
    assert len(svc["types"]) == 13 and len(svc["categories"]) == 6
    t = next(t for t in svc["types"] if t["code"] == "absence_excuse")
    assert t["attachments"]["required"] is True and isinstance(t["fields"], list) and t["steps"]


@pytest.mark.parametrize("body, needle", [
    ({"type_code": "nope", "data": {}}, "tapılmadı"),
    ({"type_code": "enrollment_certificate", "data": {}}, "təyinat"),
    ({"type_code": "enrollment_certificate", "data": {**CERT, "purpose": "Digər"}}, "Təyinatı yazın"),
    ({"type_code": "enrollment_certificate", "data": {**CERT, "lang": "Klingon"}}, "yanlış seçim"),
    ({"type_code": "grade_appeal", "data": {"course": 999, "exam_type": "Test", "details": "x"}}, ""),
])
def test_validation_errors(student, body, needle):
    r = student.post("/api/requests", body)
    assert r.status == 400 and needle.lower() in r.json["error"].lower()


def test_date_rules_for_absence_and_leave(student):
    fut = (date.today() + timedelta(days=3)).isoformat()
    past = (date.today() - timedelta(days=3)).isoformat()
    assert student.post("/api/requests", {"type_code": "absence_excuse", "data": {"reason": "Xəstəlik", "period": {"from": fut, "to": fut}}}).status == 400
    assert student.post("/api/requests", {"type_code": "leave_permission", "data": {"reason": "Olimpiada / müsabiqə", "period": {"from": past, "to": past}}}).status == 400
    rev = {"from": past, "to": (date.today() - timedelta(days=5)).isoformat()}
    assert "əvvəl" in student.post("/api/requests", {"type_code": "absence_excuse", "data": {"reason": "Xəstəlik", "period": rev}}).json["error"]
    long_ = {"from": (date.today() - timedelta(days=80)).isoformat(), "to": past}
    assert "60" in student.post("/api/requests", {"type_code": "absence_excuse", "data": {"reason": "Xəstəlik", "period": long_}}).json["error"]


def test_create_and_view_a_request(student, cert_request):
    assert cert_request["status"] == "submitted" and cert_request["type_name"] and cert_request["sla_hours"] > 0
    full = student.get(f"/api/requests/{cert_request['id']}").json
    assert [e["action"] for e in full["events"]] == ["submitted"] and full["data_view"]
    assert full["data"]["purpose_other"] == "" and full["data"]["org"] == ""     # hidden/empty fields normalised
    assert any(r["id"] == cert_request["id"] for r in student.get("/api/requests").json)


def test_translated_option_labels_are_stored_canonically(student):
    en = student.get("/api/services", lang="en").json
    ec = next(t for t in en["types"] if t["code"] == "enrollment_certificate")
    vals = {f["name"]: f["options"][0] for f in ec["fields"] if f["type"] in ("radio", "select")}
    r = student.post("/api/requests", {"type_code": "enrollment_certificate", "data": {**vals, "copies": "1"}}, lang="en")
    assert r.status == 200
    data = student.get(f"/api/requests/{r.json['id']}").json["data"]
    assert data["purpose"] == "Hərbi komissarlıq" and data["lang"] == "Azərbaycan dili"


def test_office_queue_filters(office, cert_request):
    q = office.get("/api/requests?status=open").json
    assert any(r["id"] == cert_request["id"] for r in q) and all(r["status"] in ("submitted", "in_progress", "returned") for r in q)
    assert all(r["status"] in ("ready", "rejected", "cancelled") for r in office.get("/api/requests?status=done").json)
    assert all(r["type_code"] == "transcript" for r in office.get("/api/requests?status=all&type=transcript").json)
    assert all(r["category"] == "docs" for r in office.get("/api/requests?status=all&category=docs").json)
    assert office.get("/api/requests?status=all&q=" + urllib.parse.quote("Məmmədova")).json


def test_messages_return_and_resubmit(student, office, cert_request):
    rid = cert_request["id"]
    m = office.post(f"/api/requests/{rid}/messages", {"text": "Səfirliyin adını yazın, zəhmət olmasa."}).json
    assert len(m["thread"]) == 1 and any("Dekanlıqdan" in n["title"] for n in student.get("/api/notifications").json["items"])
    assert office.post(f"/api/requests/{rid}/action", {"action": "return"}).status == 400              # a reason is required
    assert office.post(f"/api/requests/{rid}/action", {"action": "return", "note": "Qurumu yazın"}).json["status"] == "returned"
    assert office.post(f"/api/requests/{rid}/action", {"action": "approve"}).status == 409
    student.post(f"/api/requests/{rid}/messages", {"text": "Almaniya səfirliyi"})
    r = student.post(f"/api/requests/{rid}/resubmit", {"data": {"org": "Almaniya səfirliyi"}}).json
    assert r["status"] == "submitted" and r["data"]["org"] == "Almaniya səfirliyi" and r["events"][-1]["action"] == "resubmitted"
    assert student.post(f"/api/requests/{rid}/resubmit", {}).status == 409


def test_issue_document_view_link_and_verify(app_db, student, office, cert_request):
    rid = cert_request["id"]
    office.post(f"/api/requests/{rid}/action", {"action": "approve"})
    r = office.post(f"/api/requests/{rid}/action", {"action": "issue"}).json
    assert r["status"] == "ready" and r["document"]["reg_no"].startswith("AzTU-ARY-") and r["events"][-1]["action"] == "issued"
    assert office.post(f"/api/requests/{rid}/action", {"action": "issue"}).status == 409            # closed
    doc = r["document"]
    page = office.get(f"/doc/{doc['id']}").text
    assert "CERTIFICATE OF ENROLMENT" in page and "Mammadova" in page and "<svg" in page and f"/verify/{doc['verify_code']}" in page
    assert 'hidden' in office.get(f"/doc/{doc['id']}?embed=1").text
    link = student.post(f"/api/documents/{doc['id']}/link").json["url"]
    assert app_db.client().get(link).status == 200 and app_db.client().get(link).status == 401
    v = app_db.client().get(f"/verify/{doc['verify_code'].lower()}").text
    assert "etibarlıdır" in v and "A. M." in v and "Məmmədova" not in v
    assert "valid" in app_db.client().get(f"/verify/{doc['verify_code']}?lang=en").text.lower()
    assert "tapılmadı" in app_db.client().get("/verify/ZZZZ-ZZZZ").text


def test_revoke_document(app_db, office, student):
    doc = next(d for d in office.get("/api/documents?q=" + urllib.parse.quote("Məmmədova")).json if d["status"] == "valid")
    assert office.post(f"/api/documents/{doc['id']}/revoke", {}).status == 400
    assert office.post("/api/documents/999999/revoke", {"reason": "x"}).status == 404
    assert office.post(f"/api/documents/{doc['id']}/revoke", {"reason": "Səhv məlumat"}).json == {"ok": True}
    assert "ləğv edilib" in app_db.client().get(f"/verify/{doc['verify_code']}").text
    assert "Səhv məlumat" in student.get(f"/doc/{doc['id']}").text
    assert student.post(f"/api/documents/{doc['id']}/revoke", {"reason": "x"}).status == 403


def test_absence_excuse_with_attachment_excuses_attendance(student, office, teacher, pdf_bytes):
    days = sorted({r["day"] for r in student.get("/api/attendance").json["records"] if r["status"] == "absent"})
    absn = student.get(f"/api/me/absences?from={days[0]}&to={days[-1]}").json
    data = {"reason": "Xəstəlik", "period": {"from": days[0], "to": days[-1]}, "absences": [a["lesson_id"] for a in absn]}
    r = student.post("/api/requests", {"type_code": "absence_excuse", "data": data})
    assert r.status == 400 and "yüklənməlidir" in r.json["error"]
    assert student.post("/api/requests", {"type_code": "absence_excuse", "data": {**data, "absences": [1]}}).status == 400  # not an absence
    assert student.post("/api/files", {"filename": "x.pdf", "content_b64": b64(b"not a pdf")}).status == 400
    f = student.post("/api/files", {"filename": "həkim arayışı.pdf", "content_b64": b64(pdf_bytes)}).json
    assert f["mime"] == "application/pdf"
    ex = student.post("/api/requests", {"type_code": "absence_excuse", "files": [f["id"]], "data": data}).json
    assert ex["files"] == 1
    assert student.post("/api/requests", {"type_code": "absence_excuse", "files": [f["id"]], "data": data}).status == 400   # file already used
    pending = [r for r in student.get("/api/attendance").json["records"] if r["status"] == "absent"]
    assert all(r["pending_request"] == ex["id"] for r in pending)
    assert student.get(f"/api/me/absences?from={days[0]}&to={days[-1]}").json == []               # already requested
    pv = student.get(f"/api/files/{f['id']}/preview").json
    assert pv["kind"] == "pdf" and "DEMO HEKIM ARAYISI" in " ".join(pv["pages"])
    assert office.get(f"/api/files/{f['id']}").headers["Content-Type"] == "application/pdf"
    assert "attachment" in office.get(f"/api/files/{f['id']}?download=1").headers["Content-Disposition"]
    assert teacher.get(f"/api/files/{f['id']}").status == 403
    office.post(f"/api/requests/{ex['id']}/action", {"action": "approve"})
    done = office.post(f"/api/requests/{ex['id']}/action", {"action": "issue"}).json
    assert done["status"] == "ready" and done["answer"]
    att = student.get("/api/attendance").json
    assert sum(c["excused"] for c in att["courses"]) == 6 and sum(c["absent"] for c in att["courses"]) == 0
    assert any("üzrlü" in n["title"] for n in teacher.get("/api/notifications").json["items"])
    assert teacher.get("/api/courses/1/attendance").json["excused"]


def test_leave_permission_notifies_teachers(student, office, app_db):
    fut = (date.today() + timedelta(days=10)).isoformat()
    cs = [c["id"] for c in student.get("/api/courses").json][:2]
    r = student.post("/api/requests", {"type_code": "leave_permission", "data": {"reason": "Olimpiada / müsabiqə", "period": {"from": fut, "to": fut}, "courses": cs,
                                                                     "details": "Respublika olimpiadası"}})
    assert r.status == 200, r.text
    rid = r.json["id"]
    while office.get(f"/api/requests/{rid}").json["status"] != "ready":
        st = office.get(f"/api/requests/{rid}").json
        action = "issue" if st["step"] >= len(st["steps"]) - 1 else "approve"
        assert office.post(f"/api/requests/{rid}/action", {"action": action}).status == 200
    assert any("icazə verilib" in n["title"] for n in app_db.client("teacher").get("/api/notifications").json["items"])


FREE = {"type_code": "free_application", "data": {"to": "Dekanlıq", "subject": "Kurs layihəsi", "body": "Mövzunu dəyişmək istəyirəm."}}


def test_student_card_needs_a_photo(student):
    r = student.post("/api/requests", {"type_code": "student_card", "data": {"reason": "İtib"}})
    assert r.status == 400 and "fotoşəkil" in r.json["error"]


def test_cancel_and_reject(student, office):
    r = student.post("/api/requests", FREE).json
    assert student.post(f"/api/requests/{r['id']}/cancel").json["status"] == "cancelled"
    assert student.post(f"/api/requests/{r['id']}/cancel").status == 409
    r2 = student.post("/api/requests", FREE).json
    assert office.post(f"/api/requests/{r2['id']}/action", {"action": "reject", "note": "Təkrar müraciət"}).json["status"] == "rejected"
    assert office.post(f"/api/requests/{r2['id']}/action", {"action": "teleport"}).status == 409            # closed first
    r3 = student.post("/api/requests", FREE).json
    assert office.post(f"/api/requests/{r3['id']}/action", {"action": "teleport"}).status == 400


def test_transcript_document_and_preview(student, office):
    tr = student.post("/api/requests", {"type_code": "transcript", "data": {"purpose": "Magistraturaya qəbul", "lang": "Azərbaycan dili",
                                                                             "scope": "Bütün semestrlər", "delivery": "Elektron (QR kodlu PDF)"}}).json
    pv = office.get(f"/api/requests/{tr['id']}/preview").text
    assert "AKADEMİK GÖSTƏRİCİLƏR" in pv and "••••" in pv
    office.post(f"/api/requests/{tr['id']}/action", {"action": "approve"})
    doc = office.post(f"/api/requests/{tr['id']}/action", {"action": "issue"}).json["document"]
    page = office.get(f"/doc/{doc['id']}").text
    assert "AKADEMİK GÖSTƏRİCİLƏR" in page and "Diskret riyaziyyat" in page
    free = student.post("/api/requests", {"type_code": "free_application", "data": {"to": "Dekanlıq", "subject": "Mövzu", "body": "Mətn"}}).json
    assert office.get(f"/api/requests/{free['id']}/preview").status == 400        # no document for this service
    assert student.get(f"/api/requests/{tr['id']}/preview").status == 403


def test_office_summary_and_documents(office):
    s = office.get("/api/office/summary").json
    assert {"new", "in_progress", "returned", "overdue", "issued_week", "avg_hours", "by_category", "categories"} <= set(s)
    assert s["issued_week"] >= 1 and len(s["categories"]) == 6
    docs = office.get("/api/documents").json
    assert docs and all({"reg_no", "verify_code", "holder", "status"} <= set(d) for d in docs)
    assert office.get("/api/documents?q=AzTU-ARY").json


def test_file_upload_rules(student):
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 20
    assert student.post("/api/files", {"filename": "a.png", "content_b64": b64(png), "accept": "image"}).status == 200
    assert student.post("/api/files", {"filename": "a.pdf", "content_b64": b64(store.demo_pdf(["x"])), "accept": "image"}).status == 400
    assert student.post("/api/files", {"filename": "a.pdf", "content_b64": "%%%"}).status == 400
    f = student.post("/api/files", {"filename": "a.png", "content_b64": b64(png)}).json
    assert student.get(f"/api/files/{f['id']}/preview").json["kind"] == "image"
    link = student.post(f"/api/files/{f['id']}/link").json["url"]
    assert link.startswith(f"/api/files/{f['id']}?k=")
    assert student.get("/api/files/99999").status == 404
