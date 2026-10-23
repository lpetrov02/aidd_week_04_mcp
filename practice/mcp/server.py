"""MCP-сервер для TODO-приложения (stdio).

Сервер не трогает БД сам, а ходит в REST API веб-приложения (apps/todo),
поэтому все проверки остаются в одном месте, а задачи сразу видны в UI.
Адрес API: переменная окружения TODO_API_URL (по умолчанию http://127.0.0.1:5000).
TODO_DELETE_WITHOUT_ELICITATION=1 — разрешить удаление клиентам без поддержки Elicitation
(например, Qwen Code); тогда подтверждение остаётся за самим клиентом (запрос на вызов tool).
"""
import asyncio
import json
import os
import sys
from datetime import datetime
import urllib.error
import urllib.request

from typing import Optional
from urllib.parse import urlencode

try:  # SDK 2.x: FastMCP переименован в MCPServer, McpError в MCPError
    from mcp.server.mcpserver import Context, MCPServer as FastMCP
    from mcp.server.mcpserver.exceptions import ResourceError, ToolError
    from mcp.shared.exceptions import MCPError as McpError
except ImportError:  # SDK 1.x (как в лекции)
    from mcp.server.fastmcp import Context, FastMCP
    from mcp.server.fastmcp.exceptions import ResourceError, ToolError
    from mcp.shared.exceptions import McpError
from pydantic import BaseModel, Field

API_URL = os.environ.get("TODO_API_URL", "http://127.0.0.1:5000").rstrip("/")
TIMEOUT = 5

mcp = FastMCP("todo")


class TodoError(ToolError, ResourceError, ValueError):
    """Ожидаемая ошибка: её текст показывается агенту. Любое другое исключение SDK 2.x прячет
    за «Error executing tool …», и модель не поймёт, что исправить."""


def _log(msg: str) -> None:
    """Лог в stderr (stdout занят протоколом) и, если задан TODO_MCP_LOG, в файл: клиент может прятать stderr."""
    line = f"{datetime.now().strftime('%H:%M:%S.%f')[:-3]} [todo] {msg}"
    print(line, file=sys.stderr, flush=True)
    path = os.environ.get("TODO_MCP_LOG")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")


def _call(req: urllib.request.Request):
    """Выполняет запрос к API и переводит ошибки в понятные модели исключения."""
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as e:
        try:
            message = json.load(e).get("error")
        except ValueError:
            message = None
        # 4xx — ошибка ввода: покажем модели текст API, чтобы она могла исправить вызов
        raise TodoError(message or f"API вернул ошибку {e.code}") from None
    except (urllib.error.URLError, TimeoutError) as e:
        raise TodoError(
            f"TODO-приложение недоступно по адресу {API_URL} ({getattr(e, 'reason', e)}). "
            "Запустите его: python -m todo.web"
        ) from None


def _get(path: str):
    return _call(urllib.request.Request(API_URL + path, method="GET"))


def _post(path: str, payload: dict) -> dict:
    return _call(urllib.request.Request(
        API_URL + path,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    ))


def _delete(path: str):
    return _call(urllib.request.Request(API_URL + path, method="DELETE"))


@mcp.tool()
def add_task(title: str, priority: str = "normal", due: Optional[str] = None) -> dict:
    """Добавляет задачу в TODO. Пробелы по краям названия удаляются,
    пустое название запрещено, максимум 200 символов.

    priority: low, normal или high. due: срок в формате YYYY-MM-DD (необязательно).
    Возвращает созданную задачу с её id.
    """
    return _post("/api/tasks", {"title": title, "priority": priority, "due": due})


@mcp.tool()
def list_tasks(done: Optional[bool] = None) -> list:
    """Возвращает полный список задач.

    done: true — только выполненные, false — только невыполненные, не задано — все.
    """
    # TODO: GET /api/tasks [?urlencode({"done": "true"/"false"})]
    raise NotImplementedError


@mcp.tool()
def complete_task(task_id: int) -> dict:
    """Отмечает задачу выполненной. Повторный вызов для уже выполненной задачи не ошибка."""
    # TODO: POST /api/tasks/{task_id}/complete
    raise NotImplementedError


class ConfirmDelete(BaseModel):
    """Форма подтверждения для Elicitation: только простые поля."""
    confirm: bool = Field(description="Да, удалить задачу")


@mcp.tool()
async def delete_task(task_id: int, ctx: Context) -> dict:
    """Удаляет задачу. Перед удалением спрашивает подтверждение у пользователя (Elicitation);
    при отказе задача остаётся на месте."""
    task = _get(f"/api/tasks/{task_id}")  # заодно проверяем, что задача существует
    try:
        result = await asyncio.wait_for(
            ctx.elicit(f"Удалить задачу «{task['title']}» (id {task_id})?", ConfirmDelete),
            timeout=float(os.environ.get("TODO_ELICIT_TIMEOUT", "60")))
    except asyncio.TimeoutError:
        _log(f"delete_task({task_id}): таймаут, ответа нет")
        return {"status": "cancelled",
                "message": "Пользователь не ответил на запрос подтверждения вовремя, задача не удалена"}
    except McpError:
        if os.environ.get("TODO_DELETE_WITHOUT_ELICITATION") != "1":
            raise TodoError(
                "Клиент не поддерживает Elicitation, поэтому подтвердить удаление нельзя. "
                "Задача не удалена. Сообщите об этом пользователю и не пытайтесь удалить задачу другим способом.") from None
        return _delete(f"/api/tasks/{task_id}")
    if result.action != "accept" or not result.data.confirm:
        return {"status": "cancelled", "message": "Пользователь отказался от удаления"}
    return _delete(f"/api/tasks/{task_id}")


# --- Resources: данные для контекста (host/пользователь кладёт их в контекст, например по @) ---

@mcp.resource("todo://tasks/{task_id}", mime_type="application/json")
def task_resource(task_id: str) -> str:
    """Одна задача по id: todo://tasks/42."""
    try:
        number = int(task_id)
    except ValueError:
        raise TodoError(f"id задачи должен быть целым числом, получено: {task_id!r}") from None
    return json.dumps(_get(f"/api/tasks/{number}"), ensure_ascii=False, indent=2)


# --- Prompts: готовые сценарии, которые вызывает пользователь (в клиентах это slash-команда) ---

@mcp.prompt()
def do_something() -> str:
    # TODO: придумываем сценарий
    # например: пометить сделанными все задачи со словом W, срок по которым истёк более N дней назад
    raise NotImplementedError()    


if __name__ == "__main__":
    mcp.run()  # stdio
