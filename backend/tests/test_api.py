"""API 层测试：健康检查、裁决契约、输入校验与错误响应。"""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_meta_constants():
    r = client.get("/api/meta")
    assert r.status_code == 200
    body = r.json()
    assert body["events_min"] == 2 and body["events_max"] == 80
    assert body["time_max"] == 10**12


def _payload(**over):
    body = {
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
                {"time": 0, "code": "A"},
                {"time": 10, "code": "B"},
                {"time": 13, "code": "C"},
                {"time": 23, "code": "D"},
            ]
        },
        "offset_min": -50,
        "offset_max": 50,
        "jump": 7,
        "min_hits": 3,
    }
    body.update(over)
    return body


def test_adjudicate_plus_jump_contract():
    r = client.post("/api/adjudicate", json=_payload())
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "optimal"
    assert body["matched_count"] == 4
    assert body["uniqueness"] == "unique"
    sol = body["solution"]
    assert sol["initial_offset"] == 0
    assert sol["jump_direction"] == "plus"
    assert sol["offset_after"] == 7
    assert sol["pairs_before_jump"] == 2
    phases = [p["phase"] for p in sol["pairs"]]
    assert phases == ["before", "before", "after", "after"]
    # 逐对核对：时间、事件码、跳变前后偏移
    for p in sol["pairs"][:2]:
        assert p["time_a"] - p["time_b"] == p["offset"] == 0
        assert p["phase"] == "before"
    for p in sol["pairs"][2:]:
        assert p["time_a"] - p["time_b"] == p["offset"] == 7
        assert p["phase"] == "after"
    # 每对两侧事件码一致
    assert all(p["code"] in ("A", "B", "C", "D") for p in sol["pairs"])
    # 索引严格递增
    ia = [p["index_a"] for p in sol["pairs"]]
    ib = [p["index_b"] for p in sol["pairs"]]
    assert ia == sorted(ia) and len(set(ia)) == 4
    assert ib == sorted(ib) and len(set(ib)) == 4


def test_adjudicate_no_solution_reason():
    body = _payload(min_hits=5)
    r = client.post("/api/adjudicate", json=body)
    assert r.status_code == 200
    out = r.json()
    assert out["status"] == "no_solution"
    assert out["solution"] is None
    assert "最低命中数" in out["reason"]


def test_validation_times_must_strictly_increase():
    bad = _payload(
        stream_a={
            "events": [
                {"time": 10, "code": "A"},
                {"time": 10, "code": "B"},
            ]
        }
    )
    r = client.post("/api/adjudicate", json=bad)
    assert r.status_code == 422


def test_validation_stream_length_bounds():
    bad = _payload(
        stream_a={
            "events": [{"time": 1, "code": "A"}]
        }
    )
    r = client.post("/api/adjudicate", json=bad)
    assert r.status_code == 422

    big = _payload(
        stream_a={
            "events": [{"time": i + 1, "code": "A"} for i in range(81)]
        }
    )
    assert client.post("/api/adjudicate", json=big).status_code == 422


def test_validation_code_pattern():
    bad = _payload(
        stream_a={
            "events": [
                {"time": 0, "code": "abc"},
                {"time": 1, "code": "B"},
            ]
        }
    )
    assert client.post("/api/adjudicate", json=bad).status_code == 422

    bad2 = _payload(
        stream_a={
            "events": [
                {"time": 0, "code": ""},
                {"time": 1, "code": "B"},
            ]
        }
    )
    assert client.post("/api/adjudicate", json=bad2).status_code == 422

    bad3 = _payload(
        stream_a={
            "events": [
                {"time": 0, "code": "TOOLONG12"},
                {"time": 1, "code": "B"},
            ]
        }
    )
    assert client.post("/api/adjudicate", json=bad3).status_code == 422


def test_validation_time_bounds_and_range():
    bad = _payload(
        stream_a={
            "events": [
                {"time": -1, "code": "A"},
                {"time": 10**12 + 1, "code": "B"},
            ]
        }
    )
    assert client.post("/api/adjudicate", json=bad).status_code == 422

    bad_range = _payload(offset_min=10, offset_max=1)
    assert client.post("/api/adjudicate", json=bad_range).status_code == 422

    bad_jump = _payload(jump=0)
    assert client.post("/api/adjudicate", json=bad_jump).status_code == 422


def test_ambiguous_response_contains_witness():
    # d=0 与 d=100 各两对同分
    body = _payload(
        stream_a={
            "events": [
                {"time": 0, "code": "A"},
                {"time": 10, "code": "B"},
                {"time": 200, "code": "C"},
                {"time": 210, "code": "D"},
            ]
        },
        stream_b={
            "events": [
                {"time": 0, "code": "A"},
                {"time": 10, "code": "B"},
                {"time": 100, "code": "C"},
                {"time": 110, "code": "D"},
            ]
        },
        jump=5,
        min_hits=1,
        offset_min=-200,
        offset_max=200,
    )
    r = client.post("/api/adjudicate", json=body)
    out = r.json()
    assert out["status"] == "optimal"
    assert out["uniqueness"] == "ambiguous"
    assert out["solution"]["initial_offset"] == 0
    assert out["witness"]["initial_offset"] == 100


# ---------- 缓变校时（漂移）模式 ----------

def _drift_payload(**over):
    body = {
        "stream_a": {
            "events": [
                {"time": 0, "code": "A"},
                {"time": 10, "code": "B"},
                {"time": 20, "code": "C"},
                {"time": 30, "code": "D"},
            ]
        },
        # 逐对偏移 -2, 0, +2, +4：静态/一次跳变模型无法四对全中。
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
    body.update(over)
    return body


def test_drift_adjudicate_contract():
    r = client.post("/api/adjudicate", json=_drift_payload())
    assert r.status_code == 200
    body = r.json()
    assert body["mode"] == "drift"
    assert body["status"] == "optimal"
    assert body["matched_count"] == 4
    assert body["uniqueness"] == "unique"
    sol = body["solution"]
    assert sol["initial_offset"] == -2
    assert sol["max_offset_change"] == 2
    pairs = sol["pairs"]
    assert [p["offset"] for p in pairs] == [-2, 0, 2, 4]
    # 首对变化为 null，其后给出相对上一对的变化
    assert [p["offset_change"] for p in pairs] == [None, 2, 2, 2]
    # 逐对偏移等于真实时间差
    assert all(p["time_a"] - p["time_b"] == p["offset"] for p in pairs)
    # 漂移模式不返回跳变字段
    assert "phase" not in pairs[0]
    assert "jump_direction" not in sol


def test_drift_does_not_require_jump():
    body = _drift_payload()
    assert "jump" not in body
    r = client.post("/api/adjudicate", json=body)
    assert r.status_code == 200
    assert r.json()["status"] == "optimal"


def test_drift_requires_max_offset_change():
    body = _drift_payload()
    del body["max_offset_change"]
    r = client.post("/api/adjudicate", json=body)
    assert r.status_code == 422


def test_drift_max_offset_change_must_be_nonnegative():
    r = client.post("/api/adjudicate", json=_drift_payload(max_offset_change=-1))
    assert r.status_code == 422


def test_drift_no_solution_when_change_too_small():
    r = client.post(
        "/api/adjudicate", json=_drift_payload(max_offset_change=1, min_hits=2)
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "no_solution"
    assert body["matched_count"] == 1
    assert "最低命中数" in body["reason"]


def test_drift_ambiguous_witness_contract():
    # d=0 与 d=3 各有一条长度 2 的链（max_change=0 时互不相通）。
    body = _drift_payload(
        stream_a={
            "events": [
                {"time": 0, "code": "A"},
                {"time": 10, "code": "B"},
                {"time": 100, "code": "C"},
                {"time": 110, "code": "D"},
            ]
        },
        stream_b={
            "events": [
                {"time": 0, "code": "A"},
                {"time": 10, "code": "B"},
                {"time": 97, "code": "C"},
                {"time": 107, "code": "D"},
            ]
        },
        offset_min=-5,
        offset_max=5,
        max_offset_change=0,
        min_hits=2,
    )
    r = client.post("/api/adjudicate", json=body)
    body = r.json()
    assert r.status_code == 200
    assert body["uniqueness"] == "ambiguous"
    assert body["solution"]["initial_offset"] == 0
    witness = body["witness"]
    assert witness["initial_offset"] == 3
    # 见证同样逐对给出偏移与相对变化
    assert [p["offset"] for p in witness["pairs"]] == [3, 3]
    assert [p["offset_change"] for p in witness["pairs"]] == [None, 0]


def test_drift_diagnostics():
    r = client.post("/api/adjudicate", json=_drift_payload())
    diag = r.json()["diagnostics"]
    assert diag["candidates_evaluated"] >= 4
    assert diag["offsets_evaluated"] >= 1


def test_static_mode_request_without_drift_fields_unchanged():
    # 旧客户端：只发原有字段，响应结构保持不变。
    body = _payload()
    assert "drift_mode" not in body and "max_offset_change" not in body
    r = client.post("/api/adjudicate", json=body)
    assert r.status_code == 200
    data = r.json()
    # 静态响应不引入新模式字段
    assert "mode" not in data
    sol = data["solution"]
    assert set(sol) == {
        "initial_offset",
        "jump_direction",
        "jump_amount",
        "offset_after",
        "pairs_before_jump",
        "matched_count",
        "pairs",
    }
    assert set(sol["pairs"][0]) == {
        "index_a",
        "index_b",
        "time_a",
        "time_b",
        "code",
        "phase",
        "offset",
    }


def test_jump_still_required_in_static_mode():
    body = _payload()
    del body["jump"]
    r = client.post("/api/adjudicate", json=body)
    assert r.status_code == 422


def test_drift_mode_explicitly_off_keeps_static_behavior():
    body = _payload(drift_mode=False, max_offset_change=99)
    r = client.post("/api/adjudicate", json=body)
    assert r.status_code == 200
    sol = r.json()["solution"]
    # 仍是一次跳变 +7 的既有首解；漂移参数被忽略
    assert sol["jump_direction"] == "plus"
    assert sol["offset_after"] == 7
