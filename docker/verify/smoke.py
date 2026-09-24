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

        print("== 静态模式响应契约保持不变（无 drift/mode 字段）==")
        r = cli.post("/api/adjudicate", json=sample)
        body = r.json()
        check("响应不含 mode 字段", "mode" not in body)
        sol = body.get("solution") or {}
        check(
            "solution 字段集合与旧契约一致",
            set(sol.keys())
            == {
                "initial_offset",
                "jump_direction",
                "jump_amount",
                "offset_after",
                "pairs_before_jump",
                "matched_count",
                "pairs",
            },
            str(sorted(sol.keys())),
        )
        check(
            "逐对字段集合与旧契约一致",
            set(sol["pairs"][0].keys())
            == {"index_a", "index_b", "time_a", "time_b", "code", "phase", "offset"},
        )

        # ---- 缓变校时（漂移）模式 ----
        print("== POST 缓变校时：逐对偏移 -2,0,+2,+4（静态模型无法全中）==")
        drift_sample = {
            "stream_a": {
                "events": [
                    {"time": 0, "code": "A"},
                    {"time": 10, "code": "B"},
                    {"time": 20, "code": "C"},
                    {"time": 30, "code": "D"},
                ]
            },
            "stream_b": {
                "events": [
                    {"time": 2, "code": "A"},
                    {"time": 10, "code": "B"},
                    {"time": 18, "code": "C"},
                    {"time": 26, "code": "D"},
                ]
            },
            "offset_min": -10,
            "offset_max": 10,
            "drift_mode": True,
            "max_offset_change": 2,
            "min_hits": 2,
        }
        r = cli.post("/api/adjudicate", json=drift_sample)
        check("drift 200", r.status_code == 200, str(r.status_code))
        body = r.json()
        sol = body.get("solution") or {}
        pairs = sol.get("pairs", [])
        check("drift 顶层 mode=drift", body.get("mode") == "drift")
        check("drift optimal", body.get("status") == "optimal")
        check("drift matched 4", body.get("matched_count") == 4, str(body.get("matched_count")))
        check("drift unique", body.get("uniqueness") == "unique")
        check("drift initial -2", sol.get("initial_offset") == -2)
        check("drift max_offset_change 2", sol.get("max_offset_change") == 2)
        check(
            "drift 逐对实际偏移",
            [p.get("offset") for p in pairs] == [-2, 0, 2, 4],
        )
        check(
            "drift 相对上一对变化（首对 null）",
            [p.get("offset_change") for p in pairs] == [None, 2, 2, 2],
        )
        check(
            "drift 偏移等于真实时间差",
            all(p["time_a"] - p["time_b"] == p["offset"] for p in pairs),
        )
        check("drift 不含跳变字段", "jump_direction" not in sol and "phase" not in pairs[0])
        check(
            "drift 诊断计数",
            isinstance(body.get("diagnostics", {}).get("candidates_evaluated"), int),
        )

        print("== 同样数据在静态/一次跳变模型下被拒（对照）==")
        static_equiv = {
            **{k: v for k, v in drift_sample.items()
               if k not in ("drift_mode", "max_offset_change")},
            "jump": 100,
            "min_hits": 2,
        }
        r = cli.post("/api/adjudicate", json=static_equiv)
        body = r.json()
        check(
            "静态模型无解（最大仅 1 对）",
            body.get("status") == "no_solution" and body.get("matched_count") == 1,
            f"{body.get('status')}/{body.get('matched_count')}",
        )

        print("== 缓变校时失败边界：变化上限过小 ==")
        r = cli.post(
            "/api/adjudicate",
            json={**drift_sample, "max_offset_change": 1, "min_hits": 2},
        )
        body = r.json()
        check(
            "上限 1 无解且给出最大匹配数",
            body.get("status") == "no_solution" and body.get("matched_count") == 1,
            f"{body.get('status')}/{body.get('matched_count')}",
        )
        r = cli.post(
            "/api/adjudicate",
            json={**drift_sample, "max_offset_change": 2, "min_hits": 5},
        )
        check("最低命中 5 无解", r.json().get("status") == "no_solution")

        print("== 缓变校时输入校验 ==")
        bad = {k: v for k, v in drift_sample.items() if k != "max_offset_change"}
        r = cli.post("/api/adjudicate", json=bad)
        check("缺少 max_offset_change → 422", r.status_code == 422, str(r.status_code))
        r = cli.post(
            "/api/adjudicate", json={**drift_sample, "max_offset_change": -1}
        )
        check("负的 max_offset_change → 422", r.status_code == 422, str(r.status_code))
        no_jump = {k: v for k, v in static_equiv.items() if k != "jump"}
        r = cli.post("/api/adjudicate", json=no_jump)
        check("静态模式缺少 jump → 422", r.status_code == 422, str(r.status_code))

        print("== 缓变校时歧义 → 附第二份见证（逐对变化）==")
        drift_amb = {
            "stream_a": {
                "events": [
                    {"time": 0, "code": "A"},
                    {"time": 10, "code": "B"},
                    {"time": 100, "code": "C"},
                    {"time": 110, "code": "D"},
                ]
            },
            "stream_b": {
                "events": [
                    {"time": 0, "code": "A"},
                    {"time": 10, "code": "B"},
                    {"time": 97, "code": "C"},
                    {"time": 107, "code": "D"},
                ]
            },
            "offset_min": -5,
            "offset_max": 5,
            "drift_mode": True,
            "max_offset_change": 0,
            "min_hits": 2,
        }
        r = cli.post("/api/adjudicate", json=drift_amb)
        body = r.json()
        check("drift ambiguous", body.get("uniqueness") == "ambiguous")
        check("drift 首解 d=0", (body.get("solution") or {}).get("initial_offset") == 0)
        witness = body.get("witness") or {}
        check("drift 见证 d=3", witness.get("initial_offset") == 3)
        check(
            "见证逐对偏移与变化",
            [p["offset"] for p in witness.get("pairs", [])] == [3, 3]
            and [p["offset_change"] for p in witness.get("pairs", [])] == [None, 0],
        )

    if failures:
        print(f"\n冒烟失败 {len(failures)} 项：{failures}", file=sys.stderr)
        return 1
    print("\n冒烟全部通过。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
