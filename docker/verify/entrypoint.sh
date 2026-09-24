#!/usr/bin/env bash
# verify 一次性服务入口：任何一步失败立即以非零码退出。
set -euo pipefail

echo "== [1/5] 后端单元与差分测试 (pytest) =="
cd /work/backend
python -m pytest -q

echo "== [2/5] 前端依赖安装 =="
cd /work/frontend
npm ci --no-audit --no-fund

echo "== [3/5] 前端单元测试 (node --test) =="
npm test

echo "== [4/5] 前端生产构建检查 =="
npm run build

echo "== [5/5] HTTP 冒烟：对真实 API 发起裁决并断言契约 =="
ATTEMPTS=30
until curl -fsS "${API_BASE}/health" >/dev/null 2>&1; do
  ATTEMPTS=$((ATTEMPTS - 1))
  if [ "$ATTEMPTS" -le 0 ]; then
    echo "API 在预期时间内未通过健康检查" >&2
    exit 1
  fi
  sleep 1
done
echo "API 健康检查通过"
python /usr/local/bin/smoke.py

echo "全部复核步骤通过。"
