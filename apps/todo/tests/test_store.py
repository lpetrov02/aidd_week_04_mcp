import json
import os
import tempfile
import unittest
from pathlib import Path

from todo.service import TodoService
from todo.store import SignedJsonStore, StoreTamperedError, load_key


class StoreTest(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.path = os.path.join(self._dir.name, "db.json")
        self.svc = TodoService(SignedJsonStore(self.path, b"k1"))
        self.svc.add_task("секрет")

    def tearDown(self):
        self._dir.cleanup()

    def read(self):
        with open(self.path, encoding="utf-8") as f:
            return json.load(f)

    def write(self, doc):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(doc, f)

    def assert_rejected_and_untouched(self):
        before = Path(self.path).read_bytes()
        with self.assertRaises(StoreTamperedError):
            self.svc.list_tasks()
        with self.assertRaises(StoreTamperedError):
            self.svc.add_task("x")  # запись поверх подделки запрещена
        self.assertEqual(Path(self.path).read_bytes(), before)

    def test_edited_payload_rejected(self):
        doc = self.read()
        doc["payload"]["tasks"][0]["title"] = "подделка"
        self.write(doc)
        self.assert_rejected_and_untouched()

    def test_agent_rewrites_whole_file_rejected(self):
        self.write({"payload": {"next_id": 1, "next_deletion_id": 1, "tasks": [], "deletions": []}, "sig": "0" * 64})
        self.assert_rejected_and_untouched()

    def test_unsigned_or_garbage_rejected(self):
        for raw in ('{"tasks": []}', "not json", "", "[]", '{"payload": 1, "sig": 2}'):
            with self.subTest(raw=raw):
                with open(self.path, "w") as f:
                    f.write(raw)
                self.assert_rejected_and_untouched()

    def test_wrong_key_rejected(self):
        with self.assertRaises(StoreTamperedError):
            TodoService(SignedJsonStore(self.path, b"other")).list_tasks()

    def test_empty_key_refused(self):
        with self.assertRaises(ValueError):
            SignedJsonStore(self.path, b"")

    def test_no_temp_files_left(self):
        self.assertEqual(os.listdir(self._dir.name), ["db.json"])

    def test_key_file_created_with_private_mode(self):
        kf = os.path.join(self._dir.name, "sub", "secret.key")
        k1 = load_key(key_file=kf) if not os.environ.get("TODO_SECRET_KEY") else None
        if k1 is not None:
            self.assertEqual(os.stat(kf).st_mode & 0o777, 0o600)
            self.assertEqual(load_key(key_file=kf), k1)
