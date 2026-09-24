"""束流事件流复核台 API。

端点
----
``GET  /health``         健康检查（供 Docker / Compose 探活）。
``GET  /api/meta``       返回业务常量，供前端做一致的校验提示。
``POST /api/adjudicate`` 对两条事件流发起裁决。
"""

from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import drift, engine, schemas
from .schemas import (
    DRIFT_CHANGE_MAX,
    EVENTS_MAX,
    EVENTS_MIN,
    JUMP_MAX,
    TIME_MAX,
    TIME_MIN,
    AdjudicateRequest,
)

app = FastAPI(title="束流事件流复核台 API", version="1.0.0")

# 前端与 API 分容器部署，开发/同源反代两种形态都放开同源策略；
# 允许的来源可由环境变量 CORS_ORIGINS 配置（逗号分隔）。
_origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "adjudication-api"}


@app.get("/api/meta")
def meta() -> dict[str, Any]:
    return {
        "time_min": TIME_MIN,
        "time_max": TIME_MAX,
        "events_min": EVENTS_MIN,
        "events_max": EVENTS_MAX,
        "jump_max": JUMP_MAX,
        "drift_change_max": DRIFT_CHANGE_MAX,
        "code_pattern": "^[A-Z0-9]{1,8}$",
        "sign_order": ["none", "minus", "plus"],
    }


def _serialize_solution(
    sol: engine.Solution,
    stream_a: list[tuple[int, str]],
    stream_b: list[tuple[int, str]],
    jump: int,
) -> dict[str, Any]:
    d = sol.initial_offset
    offset_after = None if sol.sign == engine.SIGN_NONE else d + sol.sign * jump
    pairs_out: list[dict[str, Any]] = []
    for pos, (i, j) in enumerate(sol.sequence):
        ta, ca = stream_a[i]
        tb, cb = stream_b[j]
        phase = "before" if pos < sol.pairs_before_jump else "after"
        used_offset = d if phase == "before" else (offset_after if offset_after is not None else d)
        pairs_out.append(
            {
                "index_a": i,
                "index_b": j,
                "time_a": ta,
                "time_b": tb,
                "code": ca,
                "phase": phase,
                "offset": used_offset,
            }
        )
    return {
        "initial_offset": d,
        "jump_direction": engine.SIGN_NAME[sol.sign],
        "jump_amount": jump if sol.sign != engine.SIGN_NONE else 0,
        "offset_after": offset_after,
        "pairs_before_jump": sol.pairs_before_jump,
        "matched_count": sol.matched_count,
        "pairs": pairs_out,
    }


def _serialize_drift_solution(
    sol: drift.DriftSolution,
    stream_a: list[tuple[int, str]],
    stream_b: list[tuple[int, str]],
    max_change: int,
) -> dict[str, Any]:
    pairs_out: list[dict[str, Any]] = []
    for pos, ((i, j), used_offset) in enumerate(zip(sol.sequence, sol.offsets)):
        ta, ca = stream_a[i]
        tb, cb = stream_b[j]
        change = None if pos == 0 else used_offset - sol.offsets[pos - 1]
        pairs_out.append(
            {
                "index_a": i,
                "index_b": j,
                "time_a": ta,
                "time_b": tb,
                "code": ca,
                "offset": used_offset,
                "offset_change": change,
            }
        )
    return {
        "initial_offset": sol.initial_offset,
        "max_offset_change": max_change,
        "matched_count": sol.matched_count,
        "pairs": pairs_out,
    }


@app.post("/api/adjudicate")
def adjudicate(req: AdjudicateRequest) -> JSONResponse:
    stream_a = [(e.time, e.code) for e in req.stream_a.events]
    stream_b = [(e.time, e.code) for e in req.stream_b.events]

    if req.drift_mode:
        return _adjudicate_drift(req, stream_a, stream_b)

    assert req.jump is not None  # 模型校验已保证
    result = engine.adjudicate(
        stream_a,
        stream_b,
        req.offset_min,
        req.offset_max,
        req.jump,
        req.min_hits,
    )

    body: dict[str, Any] = {
        "status": result.status,
        "matched_count": result.matched_count,
        "min_hits": result.min_hits,
        "uniqueness": result.uniqueness,
        "solution": None,
        "witness": None,
        "reason": None,
        "diagnostics": {
            "offsets_evaluated": result.offsets_evaluated,
            "groups_evaluated": result.groups_evaluated,
        },
    }

    if result.status == "no_solution":
        if result.matched_count == 0:
            body["reason"] = "偏移范围内不存在任何同码配对"
        else:
            body["reason"] = (
                f"最大匹配数 {result.matched_count} 未达到最低命中数 {result.min_hits}"
            )
    else:
        assert result.solution is not None
        body["solution"] = _serialize_solution(result.solution, stream_a, stream_b, req.jump)
        if result.witness is not None:
            body["witness"] = _serialize_solution(
                result.witness, stream_a, stream_b, req.jump
            )

    # 经 schemas 再校验一遍，保证对外契约严格成立。
    payload = schemas.AdjudicateResponse.model_validate(body).model_dump()
    return JSONResponse(payload)


def _adjudicate_drift(
    req: AdjudicateRequest,
    stream_a: list[tuple[int, str]],
    stream_b: list[tuple[int, str]],
) -> JSONResponse:
    """缓变校时模式分支：不使用固定跳变量。"""
    assert req.max_offset_change is not None  # 模型校验已保证
    result = drift.adjudicate_drift(
        stream_a,
        stream_b,
        req.offset_min,
        req.offset_max,
        req.max_offset_change,
        req.min_hits,
    )

    body: dict[str, Any] = {
        "status": result.status,
        "matched_count": result.matched_count,
        "min_hits": result.min_hits,
        "uniqueness": result.uniqueness,
        "solution": None,
        "witness": None,
        "reason": None,
        "diagnostics": {
            "offsets_evaluated": result.offsets_evaluated,
            "candidates_evaluated": result.candidates_evaluated,
        },
    }

    if result.status == "no_solution":
        if result.matched_count == 0:
            body["reason"] = "偏移范围内不存在任何同码配对"
        else:
            body["reason"] = (
                f"最大匹配数 {result.matched_count} 未达到最低命中数 {result.min_hits}"
            )
    else:
        assert result.solution is not None
        body["solution"] = _serialize_drift_solution(
            result.solution, stream_a, stream_b, req.max_offset_change
        )
        if result.witness is not None:
            body["witness"] = _serialize_drift_solution(
                result.witness, stream_a, stream_b, req.max_offset_change
            )

    payload = schemas.DriftAdjudicateResponse.model_validate(body).model_dump()
    return JSONResponse(payload)
