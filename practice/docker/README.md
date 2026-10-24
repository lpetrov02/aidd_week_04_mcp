# Запуск агента в Docker

Агент видит только смонтированные папки, а не весь ваш диск (см. часть 5 практики).

## Файлы

- `Dockerfile` — образ с Python, Node.js, Qwen Code и зависимостями MCP-сервера;
- `build.sh` — собирает образ `qwen-agent`;
- `run.sh` — запускает агента в контейнере;
- `settings.generated.json` — создаётся `run.sh` на лету из `practice/agent/.qwen/settings.json`, в git не попадает.

## Как пользоваться

```bash
# 1. собрать образ (один раз)
practice/docker/build.sh

# 2. запустить приложение на хосте (в отдельном терминале)
cd apps && python -m todo.web

# 3. задать ключ модели и запустить агента в контейнере
export MODEL_API_KEY=...
practice/docker/run.sh
```

`run.sh` берёт модель и ключ из `practice/agent/.qwen/settings.json`, подменяет только `mcpServers`
(путь к серверу внутри контейнера и `TODO_API_URL=http://host.docker.internal:5000`) и монтирует:

- `practice/agent` → `/workspace` — рабочая папка агента, всё созданное остаётся у вас на диске;
- `practice/mcp` → `/opt/todo-mcp` (только чтение) — агент запускает сервер, но не меняет его;
- сгенерированный settings → `/workspace/.qwen/settings.json` (только чтение).

Нужен python3 на хосте (для генерации настроек) — он есть в окружении `aidd-mcp`.
Проверено в Docker Desktop (macOS); флаги для Linux `run.sh` добавляет сам.
