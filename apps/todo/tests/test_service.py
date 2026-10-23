import os
import tempfile
import unittest

from todo.service import MAX_TITLE_LEN, NotFound, TodoService
from todo.store import SignedJsonStore


def make_service(path):
    return TodoService(SignedJsonStore(path, b"test-key"))


class ServiceTest(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.path = os.path.join(self._dir.name, "db.json")
        self.svc = make_service(self.path)

    def tearDown(self):
        self._dir.cleanup()

    # --- add_task: примеры из week_01 ---
    def test_add_plain(self):
        t = self.svc.add_task("Купить продукты")
        self.assertEqual((t.id, t.title, t.done, t.priority, t.due), (1, "Купить продукты", False, "normal", None))

    def test_add_strips_spaces(self):
        self.assertEqual(self.svc.add_task("  Купить продукты  ").title, "Купить продукты")

    def test_add_invalid_raises_and_state_unchanged(self):
        for bad in ("", "   ", "\t\n", None, 123, ["a"]):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                self.svc.add_task(bad)
        self.assertEqual(self.svc.list_tasks(), [])
        self.assertFalse(os.path.exists(self.path))  # даже файл не создан

    def test_add_length_boundary(self):
        self.svc.add_task("a" * MAX_TITLE_LEN)
        with self.assertRaises(ValueError):
            self.svc.add_task("a" * (MAX_TITLE_LEN + 1))
        self.assertEqual(len(self.svc.list_tasks()), 1)

    def test_duplicates_allowed(self):
        self.assertNotEqual(self.svc.add_task("x").id, self.svc.add_task("x").id)

    def test_unicode_and_special_chars(self):
        for title in ("Отчёт 📊", "<script>alert(1)</script>", '"; DROP TABLE'):
            self.assertEqual(self.svc.add_task(title).title, title)

    def test_priority_and_due(self):
        t = self.svc.add_task("a", priority="high", due=" 2026-10-22 ")
        self.assertEqual((t.priority, t.due), ("high", "2026-10-22"))
        self.assertIsNone(self.svc.add_task("b", due="").due)

    def test_bad_priority_and_due(self):
        for kw in ({"priority": "urgent"}, {"priority": None}, {"due": "22.10.2026"},
                   {"due": "2026-02-30"}, {"due": 20261022}):
            with self.subTest(kw=kw), self.assertRaises(ValueError):
                self.svc.add_task("a", **kw)
        self.assertEqual(self.svc.list_tasks(), [])

    # --- get / ids ---
    def test_get_missing(self):
        with self.assertRaises(NotFound):
            self.svc.get_task(42)

    def test_bad_ids(self):
        for bad in ("1", None, 1.5, True):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                self.svc.get_task(bad)

    # --- list ---
    def test_list_empty_and_filters(self):
        self.assertEqual(self.svc.list_tasks(), [])
        a, b = self.svc.add_task("a"), self.svc.add_task("b")
        self.svc.complete_task(a.id)
        self.assertEqual([t.id for t in self.svc.list_tasks()], [a.id, b.id])
        self.assertEqual([t.id for t in self.svc.list_tasks(done=True)], [a.id])
        self.assertEqual([t.id for t in self.svc.list_tasks(done=False)], [b.id])

    # --- edit ---
    def test_edit_partial(self):
        t = self.svc.add_task("a", priority="high", due="2026-01-01")
        e = self.svc.edit_task(t.id, title="  b ")
        self.assertEqual((e.title, e.priority, e.due), ("b", "high", "2026-01-01"))
        self.assertIsNone(self.svc.edit_task(t.id, due=None).due)

    def test_edit_invalid_changes_nothing(self):
        t = self.svc.add_task("a")
        with self.assertRaises(ValueError):
            self.svc.edit_task(t.id, title="new", priority="bad")  # title валиден, но запись не должна пройти
        self.assertEqual(self.svc.get_task(t.id).title, "a")
        with self.assertRaises(ValueError):
            self.svc.edit_task(t.id, done="yes")

    def test_edit_missing(self):
        with self.assertRaises(NotFound):
            self.svc.edit_task(1, title="x")

    def test_complete_idempotent(self):
        t = self.svc.add_task("a")
        self.assertTrue(self.svc.complete_task(t.id).done)
        self.assertTrue(self.svc.complete_task(t.id).done)
        self.assertFalse(self.svc.edit_task(t.id, done=False).done)

    # --- удаление ---
    def test_delete(self):
        t = self.svc.add_task("a")
        self.assertEqual(self.svc.delete_task(t.id).title, "a")
        self.assertEqual(self.svc.list_tasks(), [])

    def test_delete_only_target(self):
        a, b = self.svc.add_task("a"), self.svc.add_task("b")
        self.svc.delete_task(a.id)
        self.assertEqual([t.id for t in self.svc.list_tasks()], [b.id])

    def test_delete_twice_or_missing_fails(self):
        t = self.svc.add_task("a")
        self.svc.delete_task(t.id)
        for bad in (t.id, 999):
            with self.assertRaises(NotFound):
                self.svc.delete_task(bad)

    def test_delete_bad_id(self):
        for bad in ("1", None, True):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                self.svc.delete_task(bad)

    def test_ids_not_reused_after_delete(self):
        a = self.svc.add_task("a")
        self.svc.delete_task(a.id)
        self.assertGreater(self.svc.add_task("b").id, a.id)

    def test_persistence_across_instances(self):
        self.svc.add_task("a")
        self.assertEqual([t.title for t in make_service(self.path).list_tasks()], ["a"])
