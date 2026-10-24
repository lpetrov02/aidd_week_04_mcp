#!/usr/bin/env bash
# Запускает агента Qwen Code в контейнере.
#
# Контейнер видит только три смонтированные папки — рабочую папку агента,
# MCP-сервер (только для чтения) и сгенерированный settings.json. Файла базы
# todo_db.json, ключа ~/.todo_demo/secret.key, вашего $HOME и остального диска
# в контейнере нет. shell-команды агента выполняются внутри контейнера.
#
# Перед запуском:
#   1) соберите образ:   ./build.sh
#   2) запустите приложение на хосте (python -m todo.web)
#   3) задайте ключ модели:  export MODEL_API_KEY=...
set -euo pipefail

APP_PORT=${APP_PORT:-5000}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
AGENT_DIR="$REPO_ROOT/practice/agent"
MCP_DIR="$REPO_ROOT/practice/mcp"

: "${MODEL_API_KEY:?Задайте ключ модели: export MODEL_API_KEY=...}"

if ! docker image inspect qwen-agent >/dev/null 2>&1; then
  echo "Образ qwen-agent не найден. Сначала соберите его: $SCRIPT_DIR/build.sh" >&2
  exit 1
fi

# Внутри контейнера другие пути к MCP-серверу, поэтому settings.json для
# контейнера генерируем из practice/agent/.qwen/settings.json, подменяя только
# mcpServers. Так модель и ключ настраиваются один раз в settings.json.
GEN_SETTINGS="$SCRIPT_DIR/settings.generated.json"
trap 'rm -f "$GEN_SETTINGS"' EXIT
python3 - "$AGENT_DIR/.qwen/settings.json" "$GEN_SETTINGS" <<'PY'
import json, sys
src, dst = sys.argv[1], sys.argv[2]
s = json.load(open(src, encoding="utf-8"))
s["mcpServers"] = {
    "todo": {
        "command": "python",
        "args": ["/opt/todo-mcp/server.py"],
        "env": {"TODO_API_URL": "http://host.docker.internal:${APP_PORT}"},
    }
}
json.dump(s, open(dst, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
PY

# На Linux host.docker.internal не резолвится по умолчанию, а файлы агента
# создаются от root — чиним и то, и другое.
EXTRA=()
if [ "$(uname -s)" = "Linux" ]; then
  EXTRA+=(--add-host=host.docker.internal:host-gateway --user "$(id -u):$(id -g)")
fi

docker run --rm -it \
  -v "$AGENT_DIR:/workspace" \
  -v "$MCP_DIR:/opt/todo-mcp:ro" \
  -v "$GEN_SETTINGS:/workspace/.qwen/settings.json:ro" \
  -e MODEL_API_KEY \
  ${EXTRA[@]+"${EXTRA[@]}"} \
  qwen-agent "$@"
