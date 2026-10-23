"""Тесты MCP-сервера: настоящее Flask-приложение во временном потоке + вызов через MCP-протокол."""
import asyncio
import os
import re
import sys
import tempfile
import threading
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
APPS = os.path.join(HERE, "..", "..", "apps")
sys.path.insert(0, APPS)
sys.path.insert(0, HERE)

from mcp import ClientSession, StdioServerParameters, types  # noqa: E402
from mcp.client.stdio import stdio_client  # noqa: E402
from werkzeug.serving import make_server  # noqa: E402

import server  # noqa: E402
from todo.web import create_app  # noqa: E402


def g(obj, name):
    """Поле результата клиента SDK: в 1.x camelCase (isError), в 2.x snake_case (is_error)."""
    snake = re.sub(r"([A-Z])", lambda m: "_" + m.group(1).lower(), name)
    return getattr(obj, name) if hasattr(obj, name) else getattr(obj, snake)


class ToolTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.db = os.path.join(cls.tmp.name, "db.json")
        cls.http = make_server("127.0.0.1", 0, create_app(cls.db, key="test"))
        cls.url = f"http://127.0.0.1:{cls.http.server_port}"
        threading.Thread(target=cls.http.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown()
        cls.tmp.cleanup()

    def setUp(self):
        server.API_URL = self.url

    def test_add_task(self):
        t = server.add_task("  Купить молоко  ", priority="high", due="2026-10-23")
        self.assertEqual((t["title"], t["priority"], t["due"], t["done"]), ("Купить молоко", "high", "2026-10-23", False))

    def test_invalid_input_gives_api_message(self):
        for kw, text in (({"title": "   "}, "пустым"), ({"title": "a", "priority": "urgent"}, "приоритет"),
                         ({"title": "a", "due": "завтра"}, "YYYY-MM-DD"), ({"title": "a" * 201}, "200")):
            with self.subTest(kw=kw), self.assertRaisesRegex(ValueError, text):
                server.add_task(**kw)

    def test_get_helper(self):
        server.add_task("для списка")
        self.assertIn("для списка", [t["title"] for t in server._get("/api/tasks")])
        with self.assertRaisesRegex(ValueError, "не найдена"):
            server._get("/api/tasks/999999")

    def test_api_down(self):
        server.API_URL = "http://127.0.0.1:1"
        with self.assertRaisesRegex(server.TodoError, "недоступно"):
            server.add_task("a")

    def test_through_mcp_protocol(self):
        """Реальный stdio-запуск сервера: список tools и вызов, включая ошибку."""
        async def scenario():
            params = StdioServerParameters(command=sys.executable, args=[os.path.join(HERE, "server.py")],
                                           env={**os.environ, "TODO_API_URL": self.url})
            async with stdio_client(params) as (r, w):
                async with ClientSession(r, w) as s:
                    await s.initialize()
                    tools = (await s.list_tools()).tools
                    ok = await s.call_tool("add_task", {"title": "Через MCP"})
                    bad = await s.call_tool("add_task", {"title": " "})
                    missing = await s.call_tool("add_task", {})
                    return tools, ok, bad, missing

        tools, ok, bad, missing = asyncio.run(asyncio.wait_for(scenario(), 30))
        self.assertIn("add_task", [t.name for t in tools])  # остальные tools студенты добавляют сами
        self.assertEqual(g(tools[0], "inputSchema")["required"], ["title"])
        self.assertFalse(g(ok, "isError"))
        self.assertIn("Через MCP", ok.content[0].text)
        self.assertTrue(g(bad, "isError"))
        self.assertIn("пустым", bad.content[0].text)
        self.assertTrue(g(missing, "isError"))

    def test_delete_no_answer_times_out_without_deleting(self):
        t = server.add_task("молчание")
        os.environ["TODO_ELICIT_TIMEOUT"] = "0.5"
        try:
            res, _ = self._delete_via_mcp(t["id"], ("accept", {"confirm": True}), delay=3)
        finally:
            del os.environ["TODO_ELICIT_TIMEOUT"]
        self.assertIn("не ответил", res.content[0].text)
        self.assertTrue(self._exists(t["id"]))

    # --- Resources через MCP-протокол ---
    def _session(self, fn):
        async def scenario():
            sp = StdioServerParameters(command=sys.executable, args=[os.path.join(HERE, "server.py")],
                                       env={**os.environ, "TODO_API_URL": self.url})
            async with stdio_client(sp) as (r, w):
                async with ClientSession(r, w) as s:
                    await s.initialize()
                    return await fn(s)
        return asyncio.run(asyncio.wait_for(scenario(), 30))

    def test_resource_task_by_id(self):
        import json
        t = server.add_task("для ресурса")

        async def fn(s):
            tpl = g(await s.list_resource_templates(), "resourceTemplates")
            body = await s.read_resource(f"todo://tasks/{t['id']}")
            return tpl, body
        tpl, body = self._session(fn)
        self.assertIn("todo://tasks/{task_id}", [g(x, "uriTemplate") for x in tpl])
        self.assertEqual(json.loads(body.contents[0].text)["title"], "для ресурса")

    def test_resource_errors(self):
        for uri in ("todo://tasks/999999", "todo://tasks/abc"):
            with self.subTest(uri=uri):
                async def fn(s, uri=uri):
                    try:
                        await s.read_resource(uri)
                    except Exception as e:  # McpError разных версий SDK
                        return str(e)
                    return None
                self.assertIsNotNone(self._session(fn))

    def _delete_via_mcp(self, task_id, answer, delay=0):
        """Вызывает delete_task через MCP; answer — ответ «пользователя» на Elicitation (None — клиент не умеет)."""
        asked = []

        async def on_elicit(context, params):
            asked.append(params.message)
            await asyncio.sleep(delay)
            return types.ElicitResult(action=answer[0], content=answer[1])

        async def scenario():
            sp = StdioServerParameters(command=sys.executable, args=[os.path.join(HERE, "server.py")],
                                       env={**os.environ, "TODO_API_URL": self.url})
            async with stdio_client(sp) as (r, w):
                async with ClientSession(r, w, elicitation_callback=on_elicit if answer else None) as s:
                    await s.initialize()
                    return await s.call_tool("delete_task", {"task_id": task_id})

        res = asyncio.run(asyncio.wait_for(scenario(), 30))
        return res, asked

    def _exists(self, task_id):
        return task_id in [t["id"] for t in server._get("/api/tasks")]

    def test_delete_confirmed(self):
        t = server.add_task("удалить меня")
        res, asked = self._delete_via_mcp(t["id"], ("accept", {"confirm": True}))
        self.assertFalse(g(res, "isError"))
        self.assertIn("удалить меня", asked[0])
        self.assertFalse(self._exists(t["id"]))

    def test_delete_refused_does_nothing(self):
        for answer in (("decline", None), ("cancel", None), ("accept", {"confirm": False})):
            with self.subTest(answer=answer):
                t = server.add_task("оставить")
                res, _ = self._delete_via_mcp(t["id"], answer)
                self.assertIn("cancelled", res.content[0].text)
                self.assertTrue(self._exists(t["id"]))

    def test_delete_without_elicitation_support_does_not_delete(self):
        t = server.add_task("без форм")
        res, _ = self._delete_via_mcp(t["id"], None)
        self.assertTrue(g(res, "isError"))
        self.assertIn("Elicitation", res.content[0].text)
        self.assertTrue(self._exists(t["id"]))

    def test_delete_without_elicitation_with_opt_in(self):
        t = server.add_task("qwen")
        os.environ["TODO_DELETE_WITHOUT_ELICITATION"] = "1"
        try:
            res, _ = self._delete_via_mcp(t["id"], None)
        finally:
            del os.environ["TODO_DELETE_WITHOUT_ELICITATION"]
        self.assertFalse(g(res, "isError"))
        self.assertFalse(self._exists(t["id"]))

    def test_delete_missing_task_error_before_asking(self):
        res, asked = self._delete_via_mcp(999999, ("accept", {"confirm": True}))
        self.assertTrue(g(res, "isError"))
        self.assertEqual(asked, [])


if __name__ == "__main__":
    unittest.main()
