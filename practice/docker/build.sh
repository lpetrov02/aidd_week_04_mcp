#!/usr/bin/env bash
# Собирает образ qwen-agent (один раз, ~1-2 минуты).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
docker build -t qwen-agent "$SCRIPT_DIR"
echo "Готово. Запуск: $SCRIPT_DIR/run.sh"
