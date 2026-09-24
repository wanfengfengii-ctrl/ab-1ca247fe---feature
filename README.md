# 加速器束流事件流复核台

两块采集卡在束流实验中会**漏记脉冲**，且其中一块可能发生**一次永久计数跳变**。
逐条就近配对会把重复出现的事件码接错，从而掩盖真实对时关系。初步对时后还可能
发现时钟并非一次突跳，而是在连续命中间**缓慢漂移**：固定偏移与单次跳变量模型
会把真实同码事件拒之门外。本系统是一个 React + FastAPI 全栈复核台：工程师在
页面上编辑（或文本导入）两条事件流，选择裁决模式并设定参数，经真实业务 API
发起裁决，并逐对核对时间、事件码以及各对的实际偏移。

## 业务规则

每条事件流含 **2–80** 个事件：

- 时间：`0 … 10^12` 的整数，且**严格递增**；
- 事件码：1–8 位大写字母或数字（`[A-Z0-9]{1,8}`）。

### 模式一：静态偏移 / 一次跳变（默认）

一个方案选出若干配对 `(i, j)`：

1. 两侧事件码必须相同；
2. 两侧索引都严格递增（保持顺序），未匹配事件允许跳过；
3. 跳变前每对满足 `tA_i − tB_j = d`，初始偏移 `d` 为
   `[offset_min, offset_max]` 内的整数；
4. 至多在两个**已匹配事件之间**发生一次永久跳变：跳变后每对满足
   `tA_i − tB_j = d + s·J`（`J` 为固定跳变量，`s ∈ {-1, 0, +1}`），
   跳变前后各至少有一对；
5. 匹配后的时间必须完全相等（整数相等，不做近似）。

同分裁决键：① 最大匹配数；② 初始偏移 `d`；③ 跳变方向（无跳变 → 减（`−J`）
→ 加（`+J`））；④ 跳变前匹配数 `k`；⑤ 配对索引序列字典序。

### 模式二：缓变校时（漂移，可选）

请求中置 `"drift_mode": true` 并填写 `max_offset_change`（每相邻已匹配事件
允许的**最大整数偏移变化**，≥0），不再使用固定跳变量（无需也不应提供 `jump`）。
方案仍沿用两条事件流、`[offset_min, offset_max]` 偏移范围与最低命中数：

1. 两侧事件码必须相同；
2. 两侧索引都严格递增，未匹配事件允许跳过；
3. **每一对**的实际偏移 `tA_i − tB_j` 都必须落在偏移范围内；
4. 相邻两对的实际偏移之差满足
   `|Δᵢ − Δᵢ₋₁| ≤ max_offset_change`（首对无此约束）。

同分裁决键：① 最大命中数；② 初始偏移（首对实际偏移）；③ 配对索引序列
`((i0,j0),(i1,j1),…)` 字典序。响应逐对给出实际偏移与**相对上一对的变化**
（首对为 `null`），供工程师判断漂移是否连续。`max_offset_change = 0` 时退化为
恒定偏移匹配。

### 唯一 / 歧义 / 无解（两种模式一致）

- **先最大化命中数**；最大匹配数未达最低命中数即判 **无解**。
- 规范首解按上述同分键升序确定；准确区分**唯一**与**歧义**。
- 歧义时响应里附带规范序下的**第二份见证方案**。

> 算法依据：
>
> - 跳变模式：时间严格递增 ⇒ 对固定时间差，桶内配对按 A 索引排序时 B 索引也
>   严格递增，因此每个 `(d, 方向, k)` 至多对应一条配对链，候选方案可被完整
>   枚举并精确排序（见 `backend/app/engine.py` 顶部说明）。
> - 漂移模式：把每个可行配对视为有向无环图节点、索引递增且偏移变化不越界则
>   连边，按 A 索引倒序做最长路动态规划（每列差值建区间最大值线段树支持窗口
>   查询），首解逐位贪心取字典序最小，见证取与首解最晚分叉的最小方案
>   （见 `backend/app/drift.py` 顶部说明）。

## 目录结构

```
backend/            FastAPI 裁决服务
  app/engine.py     静态偏移 / 一次跳变裁决（枚举候选、规范序、唯一/歧义、见证）
  app/drift.py      缓变校时裁决（DAG 最长路 DP + 线段树窗口查询、最晚分叉见证）
  app/schemas.py    Pydantic 输入校验与两种模式的响应契约
  app/main.py       /health、/api/meta、/api/adjudicate（按 drift_mode 分流）
  tests/            847 项测试（含两种模式各数百组对暴力枚举的随机差分测试）
frontend/           React + Vite 前端
  src/components/   事件流编辑器、参数面板（模式切换）、逐对核对结果面板
  src/streamio.*    文本导入/导出解析器及单测
  src/params.*      两种模式的表单校验与请求体构造及单测
docker/verify/      一次性 verify 服务（测试 + 构建 + HTTP 冒烟）
docker-compose.yml  api / frontend / verify 三个服务
```

## 快速启动（Docker Compose）

```bash
cp .env.example .env        # 可选：调整宿主机端口与健康检查参数
docker compose up -d --build
```

- 前端复核台： http://localhost:8080
- API 健康检查： http://localhost:8000/health
- OpenAPI 文档： http://localhost:8000/docs

前端容器内的 nginx 会把 `/api` 与 `/health` 反代到 API 容器，页面为同源访问。

### 可配置项（`.env`）

| 变量 | 默认值 | 含义 |
| --- | --- | --- |
| `FRONTEND_HOST_PORT` | `8080` | 前端宿主机端口 |
| `API_HOST_PORT` | `8000` | API 宿主机端口 |
| `FRONTEND_INTERNAL_PORT` | `80` | 前端容器内监听端口 |
| `API_INTERNAL_PORT` | `8000` | API 容器内监听端口 |
| `HEALTH_INTERVAL` / `HEALTH_TIMEOUT` / `HEALTH_RETRIES` / `HEALTH_START_PERIOD` | `10s/3s/5/5s` | Compose 与容器健康检查参数 |
| `CORS_ORIGINS` | `*` | 允许跨域来源（逗号分隔） |

## 一次性复核服务 `verify`

`verify` 服务完成代码测试、构建检查与 HTTP 冒烟后**自行退出**，并以退出码
报告结果（0 = 全部通过）。它依赖 API 健康检查通过后才启动：

```bash
docker compose run --build --rm verify
echo $?        # 0 表示全部通过
```

执行步骤：

1. 后端 `pytest`（两种模式的引擎手工用例 + 数百组随机差分测试 + API 契约/兼容测试）；
2. 前端依赖安装与 `node --test` 单元测试；
3. 前端生产构建检查（`vite build`）；
4. 等待 `GET /health` 通过；
5. HTTP 冒烟：对**真实运行中的 API** 发起裁决，断言静态跳变对时、逐对偏移、
   未达最低命中的无解、422 校验、歧义见证等旧契约保持不变，并覆盖缓变校时的
   漂移识别、逐对偏移变化、失败边界、输入校验与歧义见证。

## 本地开发（不用 Docker）

```bash
# 后端
cd backend
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
uvicorn app.main:app --reload --port 8000
pytest -q

前端另开终端：

```bash
cd frontend
npm install
npm run dev      # http://localhost:5173 ，/api 与 /health 自动代理到 :8000
npm test
npm run build
```

## API 摘要

`POST /api/adjudicate`

**静态偏移 / 一次跳变（默认，请求省略 `drift_mode` 或为 `false`）：**

```json
{
  "stream_a": {"events": [{"time": 0, "code": "TRIG"}, ...]},
  "stream_b": {"events": [...]},
  "offset_min": -50,
  "offset_max": 50,
  "jump": 100,
  "min_hits": 2
}
```

响应 `status` 为 `optimal` 时给出 `solution`（含 `initial_offset`、
`jump_direction`、`offset_after`、`pairs_before_jump` 与逐对的
`time_a/time_b/code/phase/offset`）；`uniqueness` 为 `ambiguous` 时
另附 `witness`。`no_solution` 时给出 `reason` 与当前最大匹配数。
旧客户端的请求与该模式的响应均保持原样（不新增任何字段）。

**缓变校时（`"drift_mode": true`，不使用 `jump`）：**

```json
{
  "stream_a": {"events": [{"time": 0, "code": "TRIG"}, ...]},
  "stream_b": {"events": [...]},
  "offset_min": -50,
  "offset_max": 50,
  "drift_mode": true,
  "max_offset_change": 5,
  "min_hits": 2
}
```

响应示例：

```json
{
  "mode": "drift",
  "status": "optimal",
  "matched_count": 4,
  "min_hits": 2,
  "uniqueness": "unique",
  "solution": {
    "initial_offset": -2,
    "max_offset_change": 5,
    "matched_count": 4,
    "pairs": [
      {"index_a": 0, "index_b": 0, "time_a": 0, "time_b": 2,
       "code": "TRIG", "offset": -2, "offset_change": null},
      {"index_a": 2, "index_b": 1, "time_a": 200, "time_b": 197,
       "code": "TRIG", "offset": 3, "offset_change": 5}
    ]
  },
  "witness": null,
  "reason": null,
  "diagnostics": {"offsets_evaluated": 7, "candidates_evaluated": 12}
}
```

逐对 `offset` 为该对实际偏移 `tA − tB`，`offset_change` 为相对上一对的变化
（首对为 `null`）；歧义时 `witness` 为同结构的第二份方案，`no_solution` 时
给出 `reason` 与当前最大匹配数。
