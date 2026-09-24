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


# ---------- 缓变校时（drift）模式 ----------


def _drift_payload(**over):
    body = {
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
    body.update(over)
    return body


def test_drift_mode_contract():
    r = client.post("/api/adjudicate", json=_drift_payload())
    assert r.status_code == 200
    body = r.json()
    assert body["mode"] == "drift"
    assert body["status"] == "optimal"
    assert body["matched_count"] == 4
    assert body["uniqueness"] == "unique"
    assert body["solution"] is None and body["witness"] is None
    sol = body["drift_solution"]
    assert sol["initial_offset"] == -5
    assert sol["matched_count"] == 4
    # 逐对实际偏移与相对上一对的变化
    assert [p["offset"] for p in sol["pairs"]] == [-5, -3, -1, 1]
    assert [p["offset_change"] for p in sol["pairs"]] == [None, 2, 2, 2]
    for p in sol["pairs"]:
        assert p["time_a"] - p["time_b"] == p["offset"]
    ia = [p["index_a"] for p in sol["pairs"]]
    ib = [p["index_b"] for p in sol["pairs"]]
    assert ia == sorted(ia) and len(set(ia)) == 4
    assert ib == sorted(ib) and len(set(ib)) == 4
    assert body["diagnostics"]["pairs_evaluated"] == 4
    assert body["diagnostics"]["max_drift"] == 2


def test_drift_mode_static_model_would_reject_same_data():
    # 同一数据在单次跳变模型下最大匹配不足 → no_solution（兼容对照）
    body = _drift_payload()
    static_body = {
        "stream_a": body["stream_a"],
        "stream_b": body["stream_b"],
        "offset_min": -10,
        "offset_max": 10,
        "jump": 2,
        "min_hits": 4,
    }
    r = client.post("/api/adjudicate", json=static_body)
    out = r.json()
    assert out["status"] == "no_solution"
    assert "mode" not in out and "drift_solution" not in out


def test_drift_mode_requires_max_drift():
    body = _drift_payload()
    del body["max_drift"]
    assert client.post("/api/adjudicate", json=body).status_code == 422


def test_drift_mode_max_drift_bounds():
    assert client.post("/api/adjudicate", json=_drift_payload(max_drift=-1)).status_code == 422
    assert (
        client.post("/api/adjudicate", json=_drift_payload(max_drift=2 * 10**12 + 1)).status_code
        == 422
    )
    # 边界值合法
    assert client.post("/api/adjudicate", json=_drift_payload(max_drift=0)).status_code == 200
    assert (
        client.post("/api/adjudicate", json=_drift_payload(max_drift=2 * 10**12)).status_code
        == 200
    )


def test_drift_mode_ignores_jump_field():
    # 缓变模式不再使用固定跳变量：不传 jump 即可裁决；传入亦被忽略
    body = _drift_payload()
    assert "jump" not in body
    r1 = client.post("/api/adjudicate", json=body)
    assert r1.status_code == 200
    r2 = client.post("/api/adjudicate", json={**body, "jump": 7})
    assert r2.status_code == 200
    assert r2.json() == r1.json()


def test_static_mode_requires_jump():
    body = _drift_payload()
    del body["drift_mode"]
    del body["max_drift"]
    assert client.post("/api/adjudicate", json=body).status_code == 422


def test_static_mode_response_shape_unchanged():
    # 关闭缓变模式时响应不携带任何新增字段
    r = client.post("/api/adjudicate", json=_payload())
    out = r.json()
    assert set(out.keys()) == {
        "status",
        "matched_count",
        "min_hits",
        "uniqueness",
        "solution",
        "witness",
        "reason",
        "diagnostics",
    }
    # 显式 drift_mode=false 与省略完全等价
    r2 = client.post("/api/adjudicate", json={**_payload(), "drift_mode": False})
    assert r2.json() == out


def test_drift_mode_ambiguous_witness():
    body = _drift_payload(
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
        offset_min=-200,
        offset_max=200,
        max_drift=5,
        min_hits=1,
    )
    r = client.post("/api/adjudicate", json=body)
    out = r.json()
    assert out["status"] == "optimal"
    assert out["uniqueness"] == "ambiguous"
    assert out["drift_solution"]["initial_offset"] == 0
    assert out["drift_witness"]["initial_offset"] == 100
    assert out["drift_witness"]["matched_count"] == out["drift_solution"]["matched_count"]


def test_drift_mode_no_solution_reason():
    r = client.post("/api/adjudicate", json=_drift_payload(min_hits=5))
    out = r.json()
    assert out["status"] == "no_solution"
    assert "最低命中数" in out["reason"]
    assert out["drift_solution"] is None
    assert out["mode"] == "drift"
