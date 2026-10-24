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

# путь к settings.json, который Qwen будет использовать (абсолютный)
export QWEN_CODE_SYSTEM_SETTINGS_PATH="$PWD/practice/agent/.qwen/settings.json"
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
| 2 | **Prompt injection.** Через инъекцию в данных заставить агента выполнить `curl` и отправить что-то наружу; закрыть это hook'ом | 3 |
| 3 | **Бонус: свой Prompt.** Реализовать `@mcp.prompt()` в `server.py` для сценария, где простой подстановки в шаблон мало (обработка данных, походы в API) | +1 |
| 4 | **Автоматизация в n8n.** Один сценарий в трёх реализациях: workflow, workflow + LLM-шаг, workflow + AI Agent (<https://n8n.io>) | 3 |

Больше **10 баллов** за ДЗ не получить, но бонусом (задание 3) можно компенсировать потери в других пунктах.
