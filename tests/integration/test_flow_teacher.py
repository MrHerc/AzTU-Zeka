"""Teacher workspace: home, materials, AI Academy and certificates, tech tools, syllabus assistant."""
import base64
import io
import zipfile

MD = ("# Test\n\n## Əsas anlayışlar\n- **Transformator** — dəyişən cərəyanın gərginliyini çevirən qurğudur.\n"
      "- **Generator** — mexaniki enerjini elektrik enerjisinə çevirən maşındır.\n")


def b64(s):
    return base64.b64encode(s if isinstance(s, bytes) else s.encode()).decode()


def docx(paragraphs):
    xml = ('<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'
           + "".join(f"<w:p><w:r><w:t>{p}</w:t></w:r></w:p>" for p in paragraphs) + "</w:body></w:document>")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("word/document.xml", xml)
    return buf.getvalue()


def test_teacher_home(teacher):
    h = teacher.get("/api/teacher/home").json
    assert [c["code"] for c in h["courses"]] == ["ELM-2105"] and h["courses"][0]["insights"]["questions_total"] > 0
    assert h["open_questions"] == 3 and h["academy"]["total"] >= 20 and h["academy"]["done"] == 7


def test_course_insights_for_teachers(teacher):
    ins = teacher.get("/api/courses/1").json["insights"]
    assert len(ins["weekly"]) == 8 and ins["top_topics"] and 0 <= ins["cited_rate"] <= 100 and ins["gaps"]


def test_material_upload_markdown_docx_and_delete(teacher, student):
    md = teacher.post("/api/courses/1/materials", {"filename": "test.md", "content_b64": b64(MD)}).json
    assert md["terms"] == 2 and md["chunks"] == 1 and md["title"] == "test"
    d = teacher.post("/api/courses/1/materials", {"filename": "mühazirə.docx", "title": "DOCX mühazirə",
                                                 "content_b64": b64(docx(["Alternator sinxron generatordur və elektrik enerjisi verir.",
                                                                          "Rotor fırlanan hissədir, stator isə hərəkətsiz hissədir."]))}).json
    assert d["title"] == "DOCX mühazirə" and d["chunks"] >= 1
    hits = student.post("/api/tutor/1/ask", {"message": "Alternator nədir?", "mode": "explain"}).json["answer"]
    assert any(c["material"] == "DOCX mühazirə" for c in hits["cites"])
    assert teacher.delete(f"/api/materials/{d['id']}").json == {"ok": True}
    assert teacher.get(f"/api/materials/{d['id']}").status == 404
    assert student.delete(f"/api/materials/{md['id']}").status == 403


def test_material_upload_rejections(teacher):
    assert teacher.post("/api/courses/1/materials", {"filename": "a.md", "content_b64": ""}).status == 400
    assert teacher.post("/api/courses/1/materials", {"filename": "a.md", "content_b64": b64("qısa")}).status == 400
    assert teacher.post("/api/courses/1/materials", {"filename": "a.exe", "content_b64": b64("x" * 100)}).status == 400
    assert teacher.post("/api/courses/1/materials", {"filename": "a.docx", "content_b64": b64("not a zip" * 10)}).status == 400
    assert teacher.post("/api/courses/2/materials", {"filename": "a.md", "content_b64": b64(MD)}).status == 403


def test_academy_overview(teacher):
    ac = teacher.get("/api/academy").json
    ai = next(t for t in ac["tracks"] if t["key"] == "ai")
    assert len(ac["tracks"]) == 7 and ai["done"] == 5 and ai["next"] and ac["recommended"] and ac["hours"] > 0
    assert ac["self_assessment"] and ac["assessment"]["ai"] == 3


def test_module_quiz_hides_answers_and_completion_issues_certificate(app_db, teacher):
    ai = next(t for t in teacher.get("/api/academy").json["tracks"] if t["key"] == "ai")
    m = teacher.get(f"/api/academy/module/{ai['next']}").json
    assert m["quiz"] and all("a" not in x for x in m["quiz"]) and m["track"]["key"] == "ai" and m["count"] == ai["total"]
    failed = teacher.post(f"/api/academy/module/{ai['next']}/complete", {"answers": [9] * len(m["quiz"])}).json
    assert failed["passed"] is False and failed["certificate"] is None
    done = teacher.post(f"/api/academy/module/{ai['next']}/complete", {"answers": failed["correct"]}).json
    assert done["passed"] is True and done["score"] == 100 and done["certificate"]["reg_no"].startswith("AzTU-SRT-")
    again = teacher.post(f"/api/academy/module/{ai['next']}/complete", {"answers": failed["correct"]}).json
    assert again["certificate"] is None                                                   # one certificate per track
    ac = teacher.get("/api/academy").json
    assert any(c["track"] for c in ac["certificates"]) and next(t for t in ac["tracks"] if t["key"] == "ai")["percent"] == 100
    page = teacher.get(f"/doc/{done['certificate']['id']}").text
    assert "SERTİFİKAT" in page and "Rauf Əliyev" in page
    assert "etibarlıdır" in app_db.client().get(f"/verify/{done['certificate']['verify_code']}").text
    assert teacher.get("/api/academy/module/99999").status == 404


def test_module_navigation(teacher):
    first = teacher.get("/api/academy").json["tracks"][1]["modules"][0]["id"]
    m = teacher.get(f"/api/academy/module/{first}").json
    assert m["prev"] is None and m["next"] and m["phrases"] is not None


def test_self_assessment(teacher):
    ac = teacher.put("/api/academy/assessment", {"values": {"ai": 9, "emi": 1, "unknown": 3}}).json
    assert ac["assessment"]["ai"] == 5 and ac["assessment"]["emi"] == 1 and "unknown" not in ac["assessment"]
    assert ac["recommended"][0] == "emi"


def test_tools_catalogue_and_course_toggle(teacher):
    tl = teacher.get("/api/tools").json
    assert len(tl["tools"]) >= 20 and tl["my_areas"] == ["electrical"] and tl["courses"][0]["tools"]
    assert {t["price_tone"] for t in tl["tools"]} == {"free", "paid", "other"}
    on = teacher.post("/api/courses/1/tools", {"tool_key": "phet"}).json
    assert on["on"] is True and "phet" in on["tools"]
    assert teacher.post("/api/courses/1/tools", {"tool_key": "phet"}).json["on"] is False
    assert teacher.post("/api/courses/1/tools", {"tool_key": "nope"}).status == 400


def test_syllabus_assistant(app_db, teacher, admin):
    assert teacher.get("/api/syllabus/1").json == {"saved": None, "updated_at": None}
    syl = teacher.post("/api/syllabus/1/generate", {"weeks": 30}).json
    assert len(syl["plan"]) == 18 and len(syl["outcomes"]) >= 3 and sum(p for _, p in syl["assessment"]) == 100
    assert syl["plan"][6]["topic"] == "Kollokvium 1" and syl["workload"]["total"] == syl["course"]["credits"] * 30
    syl["outcomes"][0] = "Redaktə olunmuş nəticə"
    assert teacher.put("/api/syllabus/1", {"data": syl}).status == 200
    assert teacher.get("/api/syllabus/1").json["saved"]["outcomes"][0] == "Redaktə olunmuş nəticə"
    url = teacher.post("/api/syllabus/1/link").json["url"]
    page = app_db.client().get(url).text
    assert "Təlim nəticələri" in page and "Redaktə olunmuş nəticə" in page
    assert "Redaktə olunmuş nəticə" in admin.get("/syllabus/1").text
    assert teacher.post("/api/syllabus/2/generate", {}).status == 403
