"""Ядро TODO: вся бизнес-логика. Не знает про HTTP.

Контракт (см. week_01): ошибки ввода — ValueError / NotFound, при ошибке состояние не меняется.
Удаление выполняется сразу: подтверждение у пользователя спрашивает MCP-сервер (Elicitation).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import List, Optional

from .store import SignedJsonStore

MAX_TITLE_LEN = 200
PRIORITIES = ("low", "normal", "high")
_UNSET = object()


class NotFound(ValueError):
    def __init__(self, what: str, obj_id):
        super().__init__(f"{what} {obj_id} не найдена")
        self.obj_id = obj_id


def TaskNotFound(task_id):
    return NotFound("задача", task_id)


@dataclass(frozen=True)
class Task:
    id: int
    title: str
    done: bool
    priority: str
    due: Optional[str]
    created_at: str

    def as_dict(self) -> dict:
        return dict(self.__dict__)


def normalize_title(title) -> str:
    if not isinstance(title, str):
        raise ValueError("название задачи должно быть строкой")
    title = title.strip()
    if not title:
        raise ValueError("название задачи не может быть пустым")
    if len(title) > MAX_TITLE_LEN:
        raise ValueError(f"название задачи не может быть длиннее {MAX_TITLE_LEN} символов")
    return title


def normalize_priority(priority) -> str:
    if priority not in PRIORITIES:
        raise ValueError(f"приоритет должен быть одним из: {', '.join(PRIORITIES)}")
    return priority


def normalize_due(due) -> Optional[str]:
    if due is None or (isinstance(due, str) and not due.strip()):
        return None
    if not isinstance(due, str):
        raise ValueError("срок должен быть строкой YYYY-MM-DD")
    try:
        return date.fromisoformat(due.strip()).isoformat()
    except ValueError:
        raise ValueError("срок должен быть корректной датой в формате YYYY-MM-DD") from None


def _check_id(obj_id) -> int:
    if isinstance(obj_id, bool) or not isinstance(obj_id, int):
        raise ValueError("id должен быть целым числом")
    return obj_id


def _task(d: dict) -> Task:
    return Task(d["id"], d["title"], d["done"], d["priority"], d["due"], d["created_at"])


class TodoService:
    def __init__(self, store: SignedJsonStore):
        self._store = store

    # --- внутреннее: транзакция «загрузить → изменить → сохранить» ---
    @staticmethod
    def _empty() -> dict:
        return {"next_id": 1, "tasks": []}

    def _load(self) -> dict:
        return self._store.load(self._empty())

    def _find(self, db: dict, task_id) -> dict:
        task_id = _check_id(task_id)
        for t in db["tasks"]:
            if t["id"] == task_id:
                return t
        raise TaskNotFound(task_id)

    # --- задачи ---
    def add_task(self, title, priority="normal", due=None) -> Task:
        title, priority, due = normalize_title(title), normalize_priority(priority), normalize_due(due)
        with self._store.lock:
            db = self._load()
            t = {"id": db["next_id"], "title": title, "done": False, "priority": priority,
                 "due": due, "created_at": datetime.now().isoformat(timespec="seconds")}
            db["next_id"] += 1
            db["tasks"].append(t)
            self._store.save(db)
            return _task(t)

    def get_task(self, task_id) -> Task:
        with self._store.lock:
            return _task(self._find(self._load(), task_id))

    def list_tasks(self, done: Optional[bool] = None) -> List[Task]:
        with self._store.lock:
            tasks = [_task(t) for t in self._load()["tasks"]]
        return [t for t in tasks if done is None or t.done == done]

    def edit_task(self, task_id, title=_UNSET, priority=_UNSET, due=_UNSET, done=_UNSET) -> Task:
        """Меняет только переданные поля. Всё валидируется до записи."""
        changes = {}
        if title is not _UNSET:
            changes["title"] = normalize_title(title)
        if priority is not _UNSET:
            changes["priority"] = normalize_priority(priority)
        if due is not _UNSET:
            changes["due"] = normalize_due(due)
        if done is not _UNSET:
            if not isinstance(done, bool):
                raise ValueError("done должно быть true или false")
            changes["done"] = done
        with self._store.lock:
            db = self._load()
            t = self._find(db, task_id)
            t.update(changes)
            self._store.save(db)
            return _task(t)

    def complete_task(self, task_id) -> Task:
        """Идемпотентно."""
        return self.edit_task(task_id, done=True)

    def delete_task(self, task_id) -> Task:
        """Удаляет задачу и возвращает её (удобно для сообщения пользователю)."""
        with self._store.lock:
            db = self._load()
            t = self._find(db, task_id)
            db["tasks"].remove(t)
            self._store.save(db)
            return _task(t)
