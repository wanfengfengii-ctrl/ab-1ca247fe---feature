#!/usr/bin/env python
"""verify 服务的 HTTP 冒烟脚本：对真实运行中的 API 发起请求并断言业务契约。

任何断言失败以非零退出码结束，供 Compose 一次性服务上报结果。
"""

from __future__ import annotations

import os
import sys

import httpx

BASE = os.environ.get("API_BASE", "http://api:8000").rstrip("/")
failures: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}{(' — ' + detail) if detail and not cond else ''}")
    if not cond:
        failures.append(name)


def main() -> int:
    with httpx.Client(base_url=BASE, timeout=10) as cli:
        print("== GET /health ==")
        r = cli.get("/health")
        check("health 200", r.status_code == 200, str(r.status_code))
        check("health body", r.json().get("status") == "ok")

        print("== GET /api/meta ==")
        r = cli.get("/api/meta")
        meta = r.json()
        check("meta 200", r.status_code == 200)
        check("events 2..80", meta.get("events_min") == 2 and meta.get("events_max") == 80)
        check("time max 1e12", meta.get("time_max") == 10**12)

        print("== POST /api/adjudicate（跳变示例：d=-5 → +100 → d=95）==")
        sample = {
            "stream_a": {
                "events": [
                    {"time": 0, "code": "TRIG"},
                    {"time": 100, "code": "U"},
                    {"time": 200, "code": "TRIG"},
                    {"time": 300, "code": "V"},
                ]
            },
            "stream_b": {
                "events": [
                    {"time": 5, "code": "TRIG"},
                    {"time": 105, "code": "TRIG"},
                    {"time": 205, "code": "V"},
                ]
            },
            "offset_min": -50,
            "offset_max": 50,
            "jump": 100,
            "min_hits": 2,
        }
        r = cli.post("/api/adjudicate", json=sample)
        check("adjudicate 200", r.status_code == 200, str(r.status_code))
        body = r.json()
        sol = body.get("solution") or {}
        check("status optimal", body.get("status") == "optimal")
        check("matched 3", body.get("matched_count") == 3, str(body.get("matched_count")))
        check("unique", body.get("uniqueness") == "unique")
        check("initial offset -5", sol.get("initial_offset") == -5)
        check("direction plus", sol.get("jump_direction") == "plus")
        check("offset after 95", sol.get("offset_after") == 95)
        check("k=1", sol.get("pairs_before_jump") == 1)
        pairs = sol.get("pairs", [])
        check(
            "重复 TRIG 未被就近错配",
            [ (p["index_a"], p["index_b"]) for p in pairs ] == [(0, 0), (2, 1), (3, 2)],
        )
        offsets_ok = all(p["time_a"] - p["time_b"] == p["offset"] for p in pairs)
        check("逐对偏移与时间差完全相等", offsets_ok)
        check(
            "跳变前后相位偏移正确",
            [p["offset"] for p in pairs] == [-5, 95, 95]
            and [p["phase"] for p in pairs] == ["before", "after", "after"],
        )
        check("每对事件码相同", all(p["code"] in ("TRIG", "V") for p in pairs))

        print("== POST 未达最低命中数 → no_solution ==")
        r = cli.post("/api/adjudicate", json={**sample, "min_hits": 4})
        body = r.json()
        check("no_solution", r.status_code == 200 and body.get("status") == "no_solution")
        check("给出原因", bool(body.get("reason")))

        print("== POST 非法输入（时间未严格递增）→ 422 ==")
        bad = {
            **sample,
            "stream_a": {"events": [{"time": 1, "code": "A"}, {"time": 1, "code": "B"}]},
        }
        r = cli.post("/api/adjudicate", json=bad)
        check("422", r.status_code == 422, str(r.status_code))

        print("== POST 歧义场景 → 附见证 ==")
        amb = {
            **sample,
            "stream_a": {
                "events": [
                    {"time": 0, "code": "A"},
                    {"time": 10, "code": "B"},
                    {"time": 200, "code": "C"},
                    {"time": 210, "code": "D"},
                ]
            },
            "stream_b": {
                "events": [
                    {"time": 0, "code": "A"},
                    {"time": 10, "code": "B"},
                    {"time": 100, "code": "C"},
                    {"time": 110, "code": "D"},
                ]
            },
            "offset_min": -200,
            "offset_max": 200,
            "jump": 5,
            "min_hits": 1,
        }
        r = cli.post("/api/adjudicate", json=amb)
        body = r.json()
        check("ambiguous", body.get("uniqueness") == "ambiguous")
        check(
            "witness d=100",
            (body.get("witness") or {}).get("initial_offset") == 100,
        )

        print("== POST 缓变校时模式：连续漂移对时（d: -5 → -3 → -1 → +1）==")
        drift = {
            "stream_a": {
                "events": [
                    {"time": 0, "code": "TRIG"},
                    {"time": 100, "code": "U"},
                    {"time": 200, "code": "TRIG"},
                    {"time": 300, "code": "V"},
                ]
            },
            "stream_b": {
                "events": [
                    {"time": 5, "code": "TRIG"},
                    {"time": 103, "code": "U"},
                    {"time": 201, "code": "TRIG"},
                    {"time": 299, "code": "V"},
                ]
            },
            "offset_min": -10,
            "offset_max": 10,
            "drift_mode": True,
            "max_drift": 2,
            "min_hits": 4,
        }
        r = cli.post("/api/adjudicate", json=drift)
        check("drift 200", r.status_code == 200, str(r.status_code))
        body = r.json()
        dsol = body.get("drift_solution") or {}
        check("mode drift", body.get("mode") == "drift")
        check("status optimal", body.get("status") == "optimal")
        check("matched 4", body.get("matched_count") == 4, str(body.get("matched_count")))
        check("unique", body.get("uniqueness") == "unique")
        check("静态 solution 字段为空", body.get("solution") is None)
        check("initial offset -5", dsol.get("initial_offset") == -5)
        dpairs = dsol.get("pairs", [])
        check(
            "逐对实际偏移 -5,-3,-1,+1",
            [p["offset"] for p in dpairs] == [-5, -3, -1, 1],
        )
        check(
            "逐对相对变化 —,+2,+2,+2",
            [p["offset_change"] for p in dpairs] == [None, 2, 2, 2],
        )
        check(
            "逐对偏移与时间差完全相等",
            all(p["time_a"] - p["time_b"] == p["offset"] for p in dpairs),
        )
        check(
            "配对索引两侧递增",
            [(p["index_a"], p["index_b"]) for p in dpairs]
            == [(0, 0), (1, 1), (2, 2), (3, 3)],
        )

        print("== 同一数据在单次跳变模型下被拒（兼容对照） ==")
        r = cli.post(
            "/api/adjudicate",
            json={
                "stream_a": drift["stream_a"],
                "stream_b": drift["stream_b"],
                "offset_min": -10,
                "offset_max": 10,
                "jump": 2,
                "min_hits": 4,
            },
        )
        body = r.json()
        check("静态模型 no_solution", body.get("status") == "no_solution")
        check(
            "静态响应无 drift 字段",
            "mode" not in body and "drift_solution" not in body,
        )

        print("== 缓变模式：相邻变化超限 → 链断裂 ==")
        r = cli.post("/api/adjudicate", json={**drift, "max_drift": 1, "min_hits": 2})
        body = r.json()
        check("no_solution", body.get("status") == "no_solution")
        check("最大匹配 1", body.get("matched_count") == 1, str(body.get("matched_count")))

        print("== 缓变模式：歧义附见证 ==")
        amb_drift = {
            **drift,
            "stream_a": {
                "events": [
                    {"time": 0, "code": "A"},
                    {"time": 10, "code": "B"},
                    {"time": 200, "code": "C"},
                    {"time": 210, "code": "D"},
                ]
            },
            "stream_b": {
                "events": [
                    {"time": 0, "code": "A"},
                    {"time": 10, "code": "B"},
                    {"time": 100, "code": "C"},
                    {"time": 110, "code": "D"},
                ]
            },
            "offset_min": -200,
            "offset_max": 200,
            "max_drift": 5,
            "min_hits": 1,
        }
        r = cli.post("/api/adjudicate", json=amb_drift)
        body = r.json()
        check("ambiguous", body.get("uniqueness") == "ambiguous")
        check("首解 d0=0", (body.get("drift_solution") or {}).get("initial_offset") == 0)
        check("见证 d0=100", (body.get("drift_witness") or {}).get("initial_offset") == 100)

        print("== 缓变模式：参数校验失败边界 ==")
        no_max = {k: v for k, v in drift.items() if k != "max_drift"}
        r = cli.post("/api/adjudicate", json=no_max)
        check("缺 max_drift → 422", r.status_code == 422, str(r.status_code))
        r = cli.post("/api/adjudicate", json={**drift, "max_drift": -1})
        check("max_drift 为负 → 422", r.status_code == 422)
        r = cli.post("/api/adjudicate", json={**drift, "max_drift": 2 * 10**12 + 1})
        check("max_drift 越界 → 422", r.status_code == 422)
        no_jump = {k: v for k, v in sample.items() if k != "jump"}
        r = cli.post("/api/adjudicate", json=no_jump)
        check("静态模式缺 jump → 422", r.status_code == 422, str(r.status_code))

        print("== 兼容：省略 drift_mode 与显式 false 响应一致 ==")
        r1 = cli.post("/api/adjudicate", json=sample)
        r2 = cli.post("/api/adjudicate", json={**sample, "drift_mode": False})
        check("响应逐字节一致", r1.text == r2.text)
        body1 = r1.json()
        check(
            "响应不携带新增字段",
            "mode" not in body1 and "drift_solution" not in body1,
        )

    if failures:
        print(f"\n冒烟失败 {len(failures)} 项：{failures}", file=sys.stderr)
        return 1
    print("\n冒烟全部通过。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
