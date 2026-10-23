"""Добавляет в запущенное TODO-приложение N случайных задач (разные сроки, приоритеты, статусы).

    python seed.py 20                  # 20 задач в приложение на http://127.0.0.1:5000
    python seed.py 50 --seed 1         # воспроизводимый набор
    python seed.py 10 --url http://127.0.0.1:5001
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import urllib.error
import urllib.request
from datetime import date, timedelta
from typing import List, Optional

MAX_N = 1000
VERBS = ["Подготовить", "Отправить", "Проверить", "Обновить", "Купить", "Позвонить по поводу", "Согласовать",
         "Оплатить", "Записаться на", "Разобрать", "Написать", "Забронировать", "Починить", "Заказать",
         "Прочитать", "Спланировать", "Закрыть", "Распечатать", "Протестировать", "Доработать"]
OBJECTS = ["отчёт за квартал", "договор", "презентацию", "счёт за интернет", "молоко и хлеб", "визит к врачу",
           "резервную копию", "документацию", "билеты на поезд", "ревью кода", "план на неделю", "подарок коллеге",
           "заявку на отпуск", "обновления системы", "список покупок", "встречу с командой", "доклад для лекции",
           "анкету", "посылку", "тесты для приложения"]
PRIORITIES = ["low", "normal", "high"]


def generate(n: int, rng: random.Random, today: Optional[date] = None) -> List[dict]:
    """n случайных задач: срок от -10 до +30 дней (у ~20% срока нет), ~35% уже выполнены."""
    today = today or date.today()
    tasks = []
    for _ in range(n):
        due = None if rng.random() < 0.2 else (today + timedelta(days=rng.randint(-10, 30))).isoformat()
        tasks.append({
            "title": f"{rng.choice(VERBS)} {rng.choice(OBJECTS)}",
            "priority": rng.choice(PRIORITIES),
            "due": due,
            "done": rng.random() < 0.35,
        })
    return tasks


def _request(method: str, url: str, payload: Optional[dict] = None) -> dict:
    req = urllib.request.Request(
        url, method=method, data=None if payload is None else json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=5) as resp:
        return json.load(resp)


def seed(base_url: str, tasks: List[dict]) -> int:
    base_url = base_url.rstrip("/")
    for t in tasks:
        created = _request("POST", f"{base_url}/api/tasks",
                           {"title": t["title"], "priority": t["priority"], "due": t["due"]})
        if t["done"]:
            _request("POST", f"{base_url}/api/tasks/{created['id']}/complete")
    return len(tasks)


def positive_int(value: str) -> int:
    n = int(value)
    if not 1 <= n <= MAX_N:
        raise argparse.ArgumentTypeError(f"N должно быть от 1 до {MAX_N}")
    return n


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Добавить случайные задачи в TODO-приложение")
    p.add_argument("n", type=positive_int, help=f"сколько задач добавить (1..{MAX_N})")
    p.add_argument("--url", default="http://127.0.0.1:5000", help="адрес приложения")
    p.add_argument("--seed", type=int, help="seed генератора для воспроизводимого результата")
    args = p.parse_args(argv)
    try:
        count = seed(args.url, generate(args.n, random.Random(args.seed)))
    except urllib.error.HTTPError as e:
        print(f"Ошибка: приложение отклонило запрос ({e.code})", file=sys.stderr)
        return 1
    except (urllib.error.URLError, TimeoutError) as e:
        print(f"Ошибка: приложение недоступно по адресу {args.url} ({getattr(e, 'reason', e)}). "
              "Запустите его: python -m todo.web", file=sys.stderr)
        return 1
    print(f"Добавлено задач: {count}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
