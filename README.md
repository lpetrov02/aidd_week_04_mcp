# Домашнее задание: MCP, Tools, Skills и AI Automation

Домашнее задание к теме «MCP, Tools, Skills и AI Automation». Опирается на то же TODO-приложение и MCP-сервер, что и практика.
Сами задания — в [HOMEWORK.md](HOMEWORK.md). Этот файл — про то, **как подготовить окружение** и запустить всё, что для ДЗ нужно.

```
apps/todo/               TODO-приложение: UI на / и REST API на /api/*, тесты в tests/
apps/seed.py             генерация случайных задач
practice/mcp/server.py   MCP-сервер (stdio), ходит в REST API приложения
practice/agent/.qwen/    настройки Qwen Code (модель и подключение MCP-серверов)
practice/docker/         запуск агента в контейнере (по желанию)
environment.yml          conda-окружение
requirements.txt         pip-зависимости (для варианта с venv)
HOMEWORK.md              сами задания
```

## 1. Требования к системе

| Что | Зачем | Проверка |
|---|---|---|
| **Python 3.11+** (рекомендуется 3.12) | приложение, MCP-сервер, skill-скрипт | `python3 --version` |
| **Node.js 20+ с npm** | Qwen Code и MCP Inspector (`npx`) | `node --version`, `npm --version` |
| **Доступ к LLM** по OpenAI-совместимому API | агент Qwen Code | адрес, имя модели и ключ |
| **Docker** (по желанию) | запуск агента в контейнере | `docker --version` |
| **Инстанс n8n** (cloud или self-hosted) — для задания 3 | автоматизация | см. <https://n8n.io> |

npm ставится вместе с Node.js. Если его нет — поставьте Node.js с [nodejs.org](https://nodejs.org) (LTS) или через conda (см. вариант Б ниже).

## 2. Настройка окружения

Python-зависимости собраны в `requirements.txt` / `environment.yml`: Flask, SDK `mcp`, `openpyxl` (для `.xlsx`) и
`excel-mcp-server` (готовый MCP-сервер для Excel). Выберите **один** из двух вариантов.

### Вариант А. `python -m venv` + pip

Нужен установленный Python 3.11+ и Node.js 20+ (npm).

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows (PowerShell): .venv\Scripts\Activate.ps1
pip install --upgrade pip
pip install -r requirements.txt
npm install -g @qwen-code/qwen-code
```

### Вариант Б. conda

Ставит в одно окружение сразу всё: Python, Node.js (с npm), `uv` и pip-зависимости.

```bash
conda env create -f environment.yml
conda activate aidd-mcp
npm install -g @qwen-code/qwen-code   # попадёт в окружение, не в систему
```

### Проверка окружения

```bash
python --version            # 3.11+
npm --version               # есть
qwen --version              # Qwen Code установлен
excel-mcp-server --help     # сторонний MCP-сервер для Excel на месте
python -c "import flask, mcp, openpyxl"   # ключевые пакеты импортируются
```

Дальше все команды выполняются **в активированном окружении** и из корня репозитория, если не сказано иное.
Предупреждение npm про `audio-capture` можно игнорировать.

## 3. Запуск приложения, сервера и агента

**TODO-приложение** (отдельный терминал, должно работать всё время):

```bash
cd apps
python -m todo.web          # http://127.0.0.1:5000; --port 5001 меняет порт
python seed.py 30 --seed 42 # добавить задачи (--seed 42 даёт один и тот же набор)
```

На macOS порт 5000 часто занят AirPlay — тогда запускайте с `--port 5001` и используйте этот порт везде (в том числе в `TODO_API_URL`).

**Ключ модели — через переменную окружения.** В [practice/agent/.qwen/settings.json](practice/agent/.qwen/settings.json)
подставьте имя модели и адрес API, а ключ не пишите в файл: в `envKey` указано имя переменной `MODEL_API_KEY`, Qwen читает ключ из неё.

```bash
export MODEL_API_KEY=...    # ключ не попадёт в settings.json и в git
```

**Агент и MCP-сервер.** Запуск агента:

```bash
cd practice/agent
qwen
```

Чтобы агент работал с задачами через MCP, добавьте сервер `todo` в `mcpServers` файла `settings.json`
(абсолютные пути, порт вашего приложения):

```json
"mcpServers": {
  "todo": {
    "command": "/абсолютный/путь/к/python",
    "args": ["/абсолютный/путь/practice/mcp/server.py"],
    "env": { "TODO_API_URL": "http://127.0.0.1:5000", "TODO_DELETE_WITHOUT_ELICITATION": "1" }
  }
}
```

Пути возьмите из `which python` и `echo "$PWD/practice/mcp/server.py"`. В `qwen` команда `/mcp` показывает подключённые серверы и их tools.
Проверить сервер без агента можно в Inspector: `npx @modelcontextprotocol/inspector "$(which python)" "$PWD/practice/mcp/server.py"`.

Агента можно запускать и в контейнере — скрипты в [practice/docker/](practice/docker/).

## 4. Задания

Полные условия, подсказки и критерии — в [HOMEWORK.md](HOMEWORK.md).

| № | Задание | Баллы |
|---|---|---|
| 1 | **Отчёт по задачам.** Делегировать агенту Excel-отчёт; вынести детерминированную часть в skill `make_report`; сравнить прогоны со skill и без, поэкспериментировать с `description` | 4 |
| 2 | **Prompt injection.** Заставить агента выполнить инструкцию, спрятанную в данных; добиться отправки наружу через `curl`; закрыть это hook'ом | 2 + 1 |
| 3 | **Автоматизация в n8n.** Воркфлоу: текст → AI-классификация в JSON → ветвление → сохранение. Задание на официальном сайте <https://n8n.io> | 3 + до 2 |

## 5. Тесты и отладка

```bash
# тесты приложения
cd apps && python -m unittest discover -s todo/tests -t .

# тесты MCP-сервера (поднимают приложение и проверяют сервер напрямую и через stdio-протокол)
python -m unittest discover -s practice/mcp -p test_server.py -t practice/mcp
```

| Проблема | Что проверить |
|---|---|
| `qwen: command not found` | выполнили `npm install -g @qwen-code/qwen-code` в активированном окружении |
| `spawn ... ENOENT` | в `command` и `args` сервера `todo` абсолютные пути; окружение активно |
| `TODO-приложение недоступно` | `python -m todo.web` запущен, порт совпадает с `TODO_API_URL` |
| В `/mcp` сервер `Disconnected` | пути в `settings.json` верные; `python -c "import mcp"` не падает |
| `excel-mcp-server` не найден | переустановите окружение (`pip install -r requirements.txt`) |
| `проверка целостности БД не пройдена` | `todo_db.json` изменён вручную или создан с другим ключом; удалите файл, чтобы начать с пустой базы |
