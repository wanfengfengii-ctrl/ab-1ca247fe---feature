"""缓变校时引擎：手工用例 + 对暴力枚举全部有序配对方案的差分测试。

暴力枚举规模：n,m ≤ 6 时有序配对方案数至多 Σ C(n,k)C(m,k) ≤ 924，
足以覆盖同码冲突、漂移窗口断裂、同分排序与歧义见证等全部结构。
"""

from __future__ import annotations

import itertools
import random

import pytest

from app.engine import adjudicate_drift


def S(pairs):
    """[(time, code), ...] 简写。"""
    return pairs


def drift_key(sol):
    """方案规范键：(初始偏移, 配对索引序列)。"""
    return (sol.offsets[0], sol.sequence)


# ---------- 手工用例 ----------


def test_drift_basic_gradual_offsets():
    # 时钟逐对漂移 +2：偏移 -5,-3,-1,+1；max_drift=2 时全部接受
    a = S([(0, "TRIG"), (100, "U"), (200, "TRIG"), (300, "V")])
    b = S([(5, "TRIG"), (103, "U"), (201, "TRIG"), (299, "V")])
    r = adjudicate_drift(a, b, -10, 10, max_drift=2, min_hits=4)
    assert r.status == "optimal"
    assert r.matched_count == 4
    assert r.uniqueness == "unique"
    assert r.solution.initial_offset == -5
    assert r.solution.offsets == (-5, -3, -1, 1)
    assert r.solution.sequence == ((0, 0), (1, 1), (2, 2), (3, 3))
    assert r.pairs_evaluated == 4


def test_drift_exceeding_max_breaks_chain():
    # 相邻偏移变化 2 > max_drift=1：任何相邻两对不能共存，最长链为 1
    a = S([(0, "TRIG"), (100, "U"), (200, "TRIG"), (300, "V")])
    b = S([(5, "TRIG"), (103, "U"), (201, "TRIG"), (299, "V")])
    r = adjudicate_drift(a, b, -10, 10, max_drift=1, min_hits=2)
    assert r.status == "no_solution"
    assert r.matched_count == 1
    # min_hits=1 时单对即解，首解取最小初始偏移
    r1 = adjudicate_drift(a, b, -10, 10, max_drift=1, min_hits=1)
    assert r1.status == "optimal"
    assert r1.matched_count == 1
    assert r1.solution.initial_offset == -5
    assert r1.solution.sequence == ((0, 0),)


def test_drift_zero_max_equals_static_offset():
    # max_drift=0 退化为固定偏移：链上所有对偏移相同
    a = S([(0, "A"), (10, "B"), (20, "C"), (30, "D")])
    b = S([(5, "A"), (15, "B"), (26, "C"), (35, "D")])
    # 偏移：-5,-5,-6,-5 → d=-5 链 (0,0),(1,1),(3,3) 长 3
    r = adjudicate_drift(a, b, -10, 10, max_drift=0, min_hits=1)
    assert r.status == "optimal"
    assert r.matched_count == 3
    assert r.solution.offsets == (-5, -5, -5)
    assert r.solution.sequence == ((0, 0), (1, 1), (3, 3))


def test_drift_offsets_must_be_in_range():
    a = S([(0, "A"), (10, "B")])
    b = S([(100, "A"), (110, "B")])
    r = adjudicate_drift(a, b, 0, 10, max_drift=5, min_hits=1)
    assert r.status == "no_solution"
    assert r.matched_count == 0
    assert r.pairs_evaluated == 0


def test_drift_skips_unmatched_events():
    # 未匹配事件允许跳过；码不同者不参与配对
    a = S([(0, "A"), (5, "X"), (9, "C"), (30, "D")])
    b = S([(100, "A"), (105, "Y"), (109, "C"), (131, "D")])
    # 可配：A -100、C -100、D -101；X/Y 码不同不可配
    r = adjudicate_drift(a, b, -1000, 1000, max_drift=1, min_hits=3)
    assert r.status == "optimal"
    assert r.matched_count == 3
    assert r.solution.sequence == ((0, 0), (2, 2), (3, 3))
    assert r.solution.offsets == (-100, -100, -101)


def test_drift_codes_must_match_even_within_window():
    # 同位置同偏移但码不同：不得配对
    a = S([(0, "A"), (10, "B")])
    b = S([(5, "A"), (15, "Z")])
    r = adjudicate_drift(a, b, -10, 10, max_drift=10, min_hits=2)
    assert r.status == "no_solution"
    assert r.matched_count == 1


def test_drift_canonical_prefers_smaller_initial_offset():
    # 两条等长链：d0=0 与 d0=100 → 首解取 d0=0，见证 d0=100
    a = S([(0, "A"), (10, "B"), (200, "C"), (210, "D")])
    b = S([(0, "A"), (10, "B"), (100, "C"), (110, "D")])
    r = adjudicate_drift(a, b, -200, 200, max_drift=5, min_hits=1)
    assert r.status == "optimal"
    assert r.matched_count == 2
    assert r.uniqueness == "ambiguous"
    assert r.solution.initial_offset == 0
    assert r.solution.sequence == ((0, 0), (1, 1))
    assert r.witness is not None
    assert r.witness.initial_offset == 100
    assert r.witness.sequence == ((2, 2), (3, 3))


def test_drift_same_d0_lexicographic_order_and_witness():
    # 同 d0=0 的两条等长链：序列字典序更小者为首解，另一份为见证
    a = S([(0, "X"), (10, "X"), (20, "X")])
    b = S([(0, "X"), (10, "X")])
    # 节点：(0,0)d0 (0,1)d-10 (1,0)d10 (1,1)d0 (2,1)d10（(2,0)d20 超范围）
    # 长 2 链：((0,0),(1,1))、((0,0),(2,1))（d0=0）与 ((1,0),(2,1))（d0=10）
    r = adjudicate_drift(a, b, -10, 10, max_drift=20, min_hits=1)
    assert r.status == "optimal"
    assert r.matched_count == 2
    assert r.uniqueness == "ambiguous"
    assert r.solution.sequence == ((0, 0), (1, 1))
    assert r.solution.offsets == (0, 0)
    assert r.witness.sequence == ((0, 0), (2, 1))
    assert r.witness.offsets == (0, 10)


def test_drift_witness_is_second_in_canonical_order():
    # 首解与见证必须都可行、同数、不同，且见证规范键大于首解
    a = S([(0, "A"), (10, "B"), (200, "C"), (210, "D")])
    b = S([(0, "A"), (10, "B"), (100, "C"), (110, "D")])
    r = adjudicate_drift(a, b, -200, 200, max_drift=5, min_hits=1)
    assert drift_key(r.witness) > drift_key(r.solution)
    assert r.witness.matched_count == r.solution.matched_count
    assert r.witness.sequence != r.solution.sequence


def test_drift_duplicate_codes_repeated_trig():
    # 重复事件码陷阱：全 TRIG 流，漂移窗口区分真实对时
    a = S([(0, "TRIG"), (100, "TRIG"), (200, "TRIG"), (300, "TRIG")])
    b = S([(5, "TRIG"), (104, "TRIG"), (202, "TRIG"), (301, "TRIG")])
    # 逐对偏移 -5,-4,-2,-1（相邻变化 ≤ 2）
    r = adjudicate_drift(a, b, -10, 10, max_drift=2, min_hits=4)
    assert r.status == "optimal"
    assert r.matched_count == 4
    assert r.solution.offsets == (-5, -4, -2, -1)
    assert r.solution.sequence == ((0, 0), (1, 1), (2, 2), (3, 3))


def test_drift_large_times():
    a = S([(0, "A1B2C3D4"), (10**12 - 1, "Z9")])
    b = S([(10**9, "A1B2C3D4"), (10**12 - 1 + 10**9 - 3, "Z9")])
    r = adjudicate_drift(a, b, -(10**12), 10**12, max_drift=3, min_hits=2)
    assert r.status == "optimal"
    assert r.matched_count == 2
    assert r.solution.offsets == (-(10**9), -(10**9) + 3)


# ---------- 暴力枚举差分测试 ----------


def brute_force_drift(a, b, offset_min, offset_max, max_drift, min_hits):
    """返回 (status, max_count, first_key, second_key)；键 = (初始偏移, 配对序列)。"""
    n, m = len(a), len(b)
    candidates = []  # (count, key)
    for k in range(1, min(n, m) + 1):
        for ia in itertools.combinations(range(n), k):
            for jb in itertools.combinations(range(m), k):
                if not all(a[ia[t]][1] == b[jb[t]][1] for t in range(k)):
                    continue
                deltas = [a[ia[t]][0] - b[jb[t]][0] for t in range(k)]
                if not all(offset_min <= d <= offset_max for d in deltas):
                    continue
                if not all(
                    abs(deltas[t + 1] - deltas[t]) <= max_drift for t in range(k - 1)
                ):
                    continue
                candidates.append((k, (deltas[0], tuple(zip(ia, jb)))))
    if not candidates:
        return ("no_solution", 0, None, None)
    max_count = max(c for c, _ in candidates)
    if max_count < min_hits:
        return ("no_solution", max_count, None, None)
    keys = sorted({key for c, key in candidates if c == max_count})
    first = keys[0]
    second = keys[1] if len(keys) > 1 else None
    return ("optimal", max_count, first, second)


@pytest.mark.parametrize("seed", range(400))
def test_drift_matches_brute_force(seed):
    rng = random.Random(seed)
    n = rng.randint(2, 6)
    m = rng.randint(2, 6)

    def make_stream(size):
        events = []
        t = rng.randint(0, 5)
        for _ in range(size):
            t += rng.randint(1, 9)
            events.append((t, rng.choice(["A", "B", "C", "D"])))
        return events

    a = make_stream(n)
    b = make_stream(m)
    lo = rng.choice([-20, -15, -10, -5, 0])
    hi = rng.choice([0, 5, 10, 15, 20])
    if lo > hi:
        lo, hi = hi, lo
    max_drift = rng.randint(0, 12)
    min_hits = rng.randint(1, 3)

    expected = brute_force_drift(a, b, lo, hi, max_drift, min_hits)
    r = adjudicate_drift(a, b, lo, hi, max_drift, min_hits)

    assert r.status == expected[0]
    assert r.matched_count == expected[1]
    if expected[0] == "no_solution":
        assert r.solution is None and r.witness is None
        return

    assert drift_key(r.solution) == expected[2]
    if expected[3] is None:
        assert r.uniqueness == "unique"
        assert r.witness is None
    else:
        assert r.uniqueness == "ambiguous"
        assert drift_key(r.witness) == expected[3]


def test_drift_duplicate_code_streams_matches_brute_force():
    # 重复事件码专项：全部同码（最容易就近错配）
    rng = random.Random(555)
    for seed in range(100):
        rng.seed(seed)
        n, m = rng.randint(2, 6), rng.randint(2, 6)

        def mono(size):
            t = 0
            out = []
            for _ in range(size):
                t += rng.randint(1, 6)
                out.append((t, "X"))
            return out

        a, b = mono(n), mono(m)
        max_drift = rng.randint(0, 8)
        expected = brute_force_drift(a, b, -12, 12, max_drift, 1)
        r = adjudicate_drift(a, b, -12, 12, max_drift, 1)
        assert r.status == expected[0]
        if expected[0] == "optimal":
            assert drift_key(r.solution) == expected[2]
            if expected[3] is None:
                assert r.uniqueness == "unique"
            else:
                assert r.uniqueness == "ambiguous"
                assert drift_key(r.witness) == expected[3]
