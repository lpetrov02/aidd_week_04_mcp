import io
import os
import random
import sys
import tempfile
import threading
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import date

from werkzeug.serving import make_server

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))

import seed  # noqa: E402
from todo.web import create_app  # noqa: E402


class GenerateTest(unittest.TestCase):
    def test_count_and_valid_fields(self):
        tasks = seed.generate(200, random.Random(1), today=date(2026, 10, 23))
        self.assertEqual(len(tasks), 200)
        for t in tasks:
            self.assertTrue(0 < len(t["title"]) <= 200)
            self.assertIn(t["priority"], seed.PRIORITIES)
            if t["due"] is not None:
                self.assertTrue(date(2026, 10, 13) <= date.fromisoformat(t["due"]) <= date(2026, 11, 22))

    def test_variety(self):
        tasks = seed.generate(200, random.Random(1), today=date(2026, 10, 23))
        self.assertEqual({t["priority"] for t in tasks}, set(seed.PRIORITIES))
        self.assertEqual({t["done"] for t in tasks}, {True, False})
        self.assertIn(None, {t["due"] for t in tasks})
        self.assertTrue(any(t["due"] and t["due"] < "2026-10-23" for t in tasks))  # есть просроченные
        self.assertTrue(any(t["due"] and t["due"] > "2026-10-23" for t in tasks))

    def test_seed_reproducible(self):
        a = seed.generate(10, random.Random(5), today=date(2026, 1, 1))
        b = seed.generate(10, random.Random(5), today=date(2026, 1, 1))
        self.assertEqual(a, b)


class SeedIntoAppTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.http = make_server("127.0.0.1", 0, create_app(os.path.join(cls.tmp.name, "db.json"), key="test"))
        cls.url = f"http://127.0.0.1:{cls.http.server_port}"
        threading.Thread(target=cls.http.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown()
        cls.tmp.cleanup()

    def run_main(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = seed.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def test_adds_n_tasks_with_statuses(self):
        before = len(seed._request("GET", self.url + "/api/tasks"))
        code, out, _ = self.run_main("30", "--url", self.url, "--seed", "3")
        self.assertEqual((code, out), (0, "Добавлено задач: 30\n"))
        tasks = seed._request("GET", self.url + "/api/tasks")
        self.assertEqual(len(tasks) - before, 30)
        self.assertTrue({t["done"] for t in tasks} == {True, False})

    def test_app_down(self):
        code, _, err = self.run_main("3", "--url", "http://127.0.0.1:1")
        self.assertEqual(code, 1)
        self.assertIn("недоступно", err)

    def test_bad_n(self):
        for bad in ("0", "-5", "abc", "1001", "2.5"):
            with self.subTest(n=bad), redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as cm:
                seed.main([bad, "--url", self.url])
            self.assertEqual(cm.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
