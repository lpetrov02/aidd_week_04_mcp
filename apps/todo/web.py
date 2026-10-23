"""Flask-приложение: REST API (/api/...) + одностраничный UI (/).

Запуск: python -m todo.web [--port 5000] [--db todo_db.json]
Удаление выполняется сразу; подтверждение спрашивает MCP-сервер (Elicitation), а не приложение.
"""
from __future__ import annotations

import argparse

from flask import Flask, jsonify, render_template, request

from .service import NotFound, TodoService
from .store import DEFAULT_DB, SignedJsonStore, StoreTamperedError, load_key


def create_app(db_path: str = DEFAULT_DB, key: "str | None" = None) -> Flask:
    app = Flask(__name__)
    service = TodoService(SignedJsonStore(db_path, load_key(key)))
    app.config["service"] = service

    def err(message: str, status: int):
        return jsonify({"error": message}), status

    @app.errorhandler(NotFound)
    def _nf(e):
        return err(str(e), 404)

    @app.errorhandler(ValueError)
    def _bad(e):
        return err(str(e), 400)

    @app.errorhandler(StoreTamperedError)
    def _tampered(e):
        return err(str(e), 500)

    @app.errorhandler(404)
    def _404(e):
        return err("не найдено", 404)

    @app.errorhandler(405)
    def _405(e):
        return err("метод не поддерживается", 405)

    def body() -> dict:
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            raise ValueError("тело запроса должно быть JSON-объектом")
        return data

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/api/tasks")
    def list_tasks():
        flag = request.args.get("done")
        if flag not in (None, "true", "false"):
            raise ValueError("параметр done должен быть true или false")
        done = None if flag is None else flag == "true"
        return jsonify([t.as_dict() for t in service.list_tasks(done)])

    @app.post("/api/tasks")
    def add_task():
        d = body()
        t = service.add_task(d.get("title"), d.get("priority", "normal"), d.get("due"))
        return jsonify(t.as_dict()), 201

    @app.get("/api/tasks/<int:task_id>")
    def get_task(task_id):
        return jsonify(service.get_task(task_id).as_dict())

    @app.patch("/api/tasks/<int:task_id>")
    def edit_task(task_id):
        d = body()
        fields = {k: d[k] for k in ("title", "priority", "due", "done") if k in d}
        if not fields:
            raise ValueError("нет полей для изменения (title, priority, due, done)")
        return jsonify(service.edit_task(task_id, **fields).as_dict())

    @app.post("/api/tasks/<int:task_id>/complete")
    def complete_task(task_id):
        return jsonify(service.complete_task(task_id).as_dict())

    @app.delete("/api/tasks/<int:task_id>")
    def delete_task(task_id):
        return jsonify({"status": "deleted", "task": service.delete_task(task_id).as_dict()})

    return app


def main() -> None:
    p = argparse.ArgumentParser(description="TODO web demo")
    p.add_argument("--port", type=int, default=5000)
    p.add_argument("--db", default=DEFAULT_DB)
    args = p.parse_args()
    create_app(args.db).run(host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
