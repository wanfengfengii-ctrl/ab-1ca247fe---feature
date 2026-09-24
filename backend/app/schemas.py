"""复核 API 的请求 / 响应模型与输入校验。"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

TIME_MIN = 0
TIME_MAX = 10**12
EVENTS_MIN = 2
EVENTS_MAX = 80
OFFSET_BOUND = TIME_MAX  # 时间差只可能落在 [-10^12, 10^12]
JUMP_MAX = 2 * TIME_MAX
MIN_HITS_MAX = EVENTS_MAX


class EventIn(BaseModel):
    time: int = Field(..., ge=TIME_MIN, le=TIME_MAX)
    code: str = Field(..., min_length=1, max_length=8)

    @field_validator("code")
    @classmethod
    def _code_uppercase_alnum(cls, v: str) -> str:
        # 仅允许 1–8 位大写字母或数字。
        if not all(("A" <= c <= "Z") or ("0" <= c <= "9") for c in v):
            raise ValueError("事件码只能包含 1–8 位大写字母 A–Z 或数字 0–9")
        return v


class StreamIn(BaseModel):
    events: list[EventIn] = Field(..., min_length=EVENTS_MIN, max_length=EVENTS_MAX)

    @model_validator(mode="after")
    def _strictly_increasing(self) -> "StreamIn":
        prev = None
        for ev in self.events:
            if prev is not None and ev.time <= prev:
                raise ValueError("事件时间必须严格递增")
            prev = ev.time
        return self


class AdjudicateRequest(BaseModel):
    stream_a: StreamIn
    stream_b: StreamIn
    offset_min: int = Field(..., ge=-OFFSET_BOUND, le=OFFSET_BOUND)
    offset_max: int = Field(..., ge=-OFFSET_BOUND, le=OFFSET_BOUND)
    # 静态偏移 / 单次跳变模式必填；缓变校时模式下不再使用（传入亦被忽略）。
    jump: Optional[int] = Field(None, ge=1, le=JUMP_MAX)
    min_hits: int = Field(..., ge=1, le=MIN_HITS_MAX)
    # 缓变校时：启用后不再使用固定跳变量，改为约束每相邻已匹配事件的
    # 整数偏移变化不超过 max_drift。
    drift_mode: bool = False
    max_drift: Optional[int] = Field(None, ge=0, le=JUMP_MAX)

    @model_validator(mode="after")
    def _check_ranges(self) -> "AdjudicateRequest":
        if self.offset_min > self.offset_max:
            raise ValueError("允许偏移范围下界不能大于上界")
        if self.drift_mode:
            if self.max_drift is None:
                raise ValueError(
                    "启用缓变校时时必须填写每相邻事件允许的最大整数偏移变化 max_drift"
                )
        elif self.jump is None:
            raise ValueError("未启用缓变校时时必须填写固定跳变量 jump")
        return self


class PairOut(BaseModel):
    index_a: int
    index_b: int
    time_a: int
    time_b: int
    code: str
    phase: Literal["before", "after"]  # 跳变前 / 跳变后
    offset: int  # 该对成立时使用的偏移 tA - tB


class SolutionOut(BaseModel):
    initial_offset: int
    jump_direction: Literal["none", "minus", "plus"]
    jump_amount: int
    offset_after: Optional[int]
    pairs_before_jump: int
    matched_count: int
    pairs: list[PairOut]


class DriftPairOut(BaseModel):
    index_a: int
    index_b: int
    time_a: int
    time_b: int
    code: str
    offset: int  # 该对实际偏移 tA - tB
    offset_change: Optional[int]  # 相对上一对偏移的变化；首对为 null


class DriftSolutionOut(BaseModel):
    initial_offset: int  # 首对偏移 d0
    matched_count: int
    pairs: list[DriftPairOut]


class AdjudicateResponse(BaseModel):
    status: Literal["optimal", "no_solution"]
    matched_count: int
    min_hits: int
    uniqueness: Optional[Literal["unique", "ambiguous"]]
    solution: Optional[SolutionOut]
    witness: Optional[SolutionOut]
    reason: Optional[str]
    diagnostics: dict
    # —— 缓变校时模式专用字段；静态模式响应不携带这些键（保持原有契约） ——
    mode: Literal["jump", "drift"] = "jump"
    drift_solution: Optional[DriftSolutionOut] = None
    drift_witness: Optional[DriftSolutionOut] = None
