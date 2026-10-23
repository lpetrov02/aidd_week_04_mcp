import os
import tempfile
import unittest
from pathlib import Path

from todo.web import create_app


class WebTest(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.path = os.path.join(self._dir.name, "db.json")
        self.c = create_app(self.path, key="test").test_client()

    def tearDown(self):
        self._dir.cleanup()

    def add(self, **kw):
        return self.c.post("/api/tasks", json=kw)

    def test_index_page(self):
        r = self.c.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertIn("TODO demo", r.get_data(as_text=True))

    def test_add_scenario_from_lecture(self):
        r = self.add(title="  Подготовить отчет  ")
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.get_json()["title"], "Подготовить отчет")
        self.assertEqual([t["title"] for t in self.c.get("/api/tasks").get_json()], ["Подготовить отчет"])

    def test_empty_title_400(self):
        for bad in ({"title": "   "}, {"title": None}, {}, {"title": 5}):
            with self.subTest(bad=bad):
                r = self.add(**bad)
                self.assertEqual(r.status_code, 400)
                self.assertIn("error", r.get_json())
        self.assertEqual(self.c.get("/api/tasks").get_json(), [])

    def test_body_not_json_object(self):
        for kw in ({"data": "x", "content_type": "text/plain"}, {"json": [1]}, {}):
            with self.subTest(kw=kw):
                self.assertEqual(self.c.post("/api/tasks", **kw).status_code, 400)

    def test_get_and_missing(self):
        self.add(title="a")
        self.assertEqual(self.c.get("/api/tasks/1").get_json()["title"], "a")
        self.assertEqual(self.c.get("/api/tasks/99").status_code, 404)
        self.assertEqual(self.c.get("/api/tasks/abc").status_code, 404)

    def test_patch(self):
        self.add(title="a")
        r = self.c.patch("/api/tasks/1", json={"title": "b", "priority": "high", "done": True})
        self.assertEqual({k: r.get_json()[k] for k in ("title", "priority", "done")}, {"title": "b", "priority": "high", "done": True})
        self.assertEqual(self.c.patch("/api/tasks/1", json={}).status_code, 400)
        self.assertEqual(self.c.patch("/api/tasks/1", json={"priority": "zzz"}).status_code, 400)
        self.assertEqual(self.c.patch("/api/tasks/9", json={"title": "x"}).status_code, 404)

    def test_complete_and_filter(self):
        self.add(title="a"); self.add(title="b")
        self.assertEqual(self.c.post("/api/tasks/1/complete").status_code, 200)
        self.assertEqual([t["id"] for t in self.c.get("/api/tasks?done=true").get_json()], [1])
        self.assertEqual([t["id"] for t in self.c.get("/api/tasks?done=false").get_json()], [2])
        self.assertEqual(self.c.get("/api/tasks?done=maybe").status_code, 400)

    def test_delete(self):
        self.add(title="a"); self.add(title="b")
        r = self.c.delete("/api/tasks/1")
        self.assertEqual(r.status_code, 200)
        self.assertEqual((r.get_json()["status"], r.get_json()["task"]["title"]), ("deleted", "a"))
        self.assertEqual([t["id"] for t in self.c.get("/api/tasks").get_json()], [2])
        self.assertEqual(self.c.delete("/api/tasks/1").status_code, 404)  # повторно — 404

    def test_delete_missing_task_404(self):
        self.assertEqual(self.c.delete("/api/tasks/7").status_code, 404)

    def test_tampered_db_gives_500_and_not_overwritten(self):
        self.add(title="a")
        with open(self.path, "a") as f:
            f.write(" ")
        # пробел в конце JSON валиден, подпись по payload цела: подделкой это не считается
        self.assertEqual(self.c.get("/api/tasks").status_code, 200)
        with open(self.path, "w") as f:
            f.write('{"payload": {"tasks": []}, "sig": "x"}')
        before = Path(self.path).read_text()
        r = self.c.get("/api/tasks")
        self.assertEqual(r.status_code, 500)
        self.assertIn("целостности", r.get_json()["error"])
        self.assertEqual(self.add(title="x").status_code, 500)
        self.assertEqual(Path(self.path).read_text(), before)

    def test_wrong_method(self):
        self.assertEqual(self.c.put("/api/tasks").status_code, 405)


if __name__ == "__main__":
    unittest.main()
