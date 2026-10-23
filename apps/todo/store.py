"""Хранилище: JSON-файл с HMAC-подписью.

Файл = {"payload": {...}, "sig": "<hex HMAC-SHA256>"}. Ключ лежит ВНЕ проекта
(env TODO_SECRET_KEY или ~/.todo_demo/secret.key, права 0600). Кто не знает ключ,
не может подделать файл: любая ручная правка ломает подпись, приложение отказывается
читать такую БД и НЕ перезаписывает её. Это защита от подделки, не шифрование.
Не защищает от подмены файла на старую валидную копию (rollback).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import tempfile
import threading
from pathlib import Path

DEFAULT_DB = "todo_db.json"
DEFAULT_KEY_FILE = Path.home() / ".todo_demo" / "secret.key"


class StoreTamperedError(RuntimeError):
    """Файл БД повреждён или изменён вне приложения."""


def load_key(key: "str | None" = None, key_file: Path = DEFAULT_KEY_FILE) -> bytes:
    key = key or os.environ.get("TODO_SECRET_KEY")
    if key:
        return key.encode("utf-8")
    key_file = Path(key_file)
    if not key_file.exists():
        key_file.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(key_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(secrets.token_hex(32))
    return key_file.read_text().strip().encode("utf-8")


def _canonical(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


class SignedJsonStore:
    def __init__(self, path: str, key: bytes):
        if not key:
            raise ValueError("пустой ключ подписи")
        self.path = Path(path)
        self._key = key
        self.lock = threading.RLock()

    def _sign(self, payload: dict) -> str:
        return hmac.new(self._key, _canonical(payload), hashlib.sha256).hexdigest()

    def load(self, default: dict) -> dict:
        if not self.path.exists():
            return default
        try:
            doc = json.loads(self.path.read_text(encoding="utf-8"))
            payload, sig = doc["payload"], doc["sig"]
            ok = isinstance(payload, dict) and isinstance(sig, str)
        except (ValueError, KeyError, TypeError, OSError):
            ok = False
        if not ok or not hmac.compare_digest(sig, self._sign(payload)):
            raise StoreTamperedError(
                f"проверка целостности БД {self.path} не пройдена: файл изменён вне приложения или повреждён")
        return payload

    def save(self, payload: dict) -> None:
        doc = {"payload": payload, "sig": self._sign(payload)}
        # атомарная запись: временный файл + rename, чтобы не оставить половину файла
        fd, tmp = tempfile.mkstemp(dir=self.path.parent or ".", prefix=".todo_", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(doc, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self.path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
