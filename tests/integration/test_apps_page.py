"""The apps page (tasks/todo.md, Task 37): the administrator sets tiles per role; each role sees only its own."""
from zeka.legacy import store


def test_each_role_sees_only_its_tiles_and_only_the_administrator_sets_them(app_db):
    admin, student, teacher = app_db.client("admin"), app_db.client("student"), app_db.client("teacher")
    tiles = [{"title": "Kitabxana", "url": "https://lib.aztu.edu.az", "roles": ["student"]},
             {"title": "Kadrlar", "url": "https://hr.aztu.edu.az", "roles": ["teacher"]}]
    assert teacher.put("/api/apps", {"apps": tiles}).status == 403
    for bad in ({**tiles[0], "url": "http://lib.aztu.edu.az"}, {**tiles[0], "url": "javascript:alert(1)"}, {**tiles[0], "roles": ["root"]},
                {**tiles[0], "roles": []}, {**tiles[0], "title": "x"}):
        assert admin.put("/api/apps", {"apps": [bad]}).status == 400, bad
    assert admin.put("/api/apps", {"apps": tiles}).status == 200
    mine = student.get("/api/apps").json
    assert [a["title"] for a in mine["apps"]] == ["Kitabxana"] and mine["all"] is None
    assert [a["title"] for a in teacher.get("/api/apps").json["apps"]] == ["Kadrlar"]
    assert [a["title"] for a in admin.get("/api/apps").json["all"]] == ["Kitabxana", "Kadrlar"]
    c = store.connect()
    try:
        assert store.row(c, "SELECT 1 FROM audit WHERE action='apps_saved' AND detail=?",   # TM-E14: what was saved, not just how many
                         ("2 tiles: https://lib.aztu.edu.az https://hr.aztu.edu.az",))
    finally:
        c.close()
