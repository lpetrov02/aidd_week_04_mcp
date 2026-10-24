FROM node:22-bookworm-slim

# Python для MCP-сервера + зависимости (mcp, flask, uv) в отдельном venv
RUN apt-get update \
 && apt-get install -y --no-install-recommends python3 python3-venv ca-certificates \
 && rm -rf /var/lib/apt/lists/*
RUN python3 -m venv /opt/venv \
 && /opt/venv/bin/pip install --no-cache-dir "mcp>=1.9,<3" "flask>=3.0" uv
ENV PATH="/opt/venv/bin:$PATH"

# Агент Qwen Code
RUN npm install -g @qwen-code/qwen-code

USER node
WORKDIR /workspace
ENTRYPOINT ["qwen"]
