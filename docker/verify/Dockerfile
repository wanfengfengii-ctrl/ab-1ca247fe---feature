# 一次性复核服务：代码测试 + 前端构建检查 + 对真实运行中的 API 做 HTTP 冒烟，
# 全部通过才以 0 退出。构建上下文为仓库根目录。
FROM node:22-bookworm-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 python3-venv curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /work

# 后端依赖（含 pytest/httpx）
COPY backend/requirements.txt backend/requirements-dev.txt /work/backend/
RUN python3 -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir -r /work/backend/requirements.txt -r /work/backend/requirements-dev.txt

# 全部源码（node_modules / .venv / dist 由根 .dockerignore 排除）
COPY backend /work/backend
COPY frontend /work/frontend
COPY docker/verify/smoke.py /usr/local/bin/smoke.py
COPY docker/verify/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

ENV PATH="/opt/venv/bin:$PATH" \
    API_BASE="http://api:8000"

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
