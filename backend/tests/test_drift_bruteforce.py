"""差分测试：缓变校时引擎 vs 全部有序配对方案的暴力枚举。

n,m ≤ 6 时有序配对方案总数 Σ_k C(n,k)C(m,k) = C(n+m,n) ≤ 924，
足以覆盖漂移窗口、跨列转移、同码冲突、同分排序与最晚分叉见证。
"""

from __future__ import annotations

import itertools
import random

import pytest

from app.drift import adjudicate_drift


def brute_force_drift(a, b, offset_min, offset_max, max_change, min_hits):
    """返回 (status, max_count, first_key, second_key, first_offsets)。

    方案键：(首对偏移 d, 配对序列)。
    """
    n, m = len(a), len(b)
    candidates = []  # (count, key, offsets)
    for k in range(1, min(n, m) + 1):
        for ia in itertools.combinations(range(n), k):
            for jb in itertools.combinations(range(m), k):
                if not all(a[ia[t]][1] == b[jb[t]][1] for t in range(k)):
                    continue
                deltas = [a[ia[t]][0] - b[jb[t]][0] for t in range(k)]
                if not all(offset_min <= d <= offset_max for d in deltas):
                    continue
                if any(
                    abs(deltas[t] - deltas[t - 1]) > max_change for t in range(1, k)
                ):
                    continue
                seq = tuple(zip(ia, jb))
                candidates.append((k, (deltas[0], seq), tuple(deltas)))
    if not candidates:
        return ("no_solution", 0, None, None, None)
    max_count = max(c for c, _, _ in candidates)
    if max_count < min_hits:
        return ("no_solution", max_count, None, None, None)
    keys = sorted({key for c, key, _ in candidates if c == max_count})
    first = keys[0]
    second = keys[1] if len(keys) > 1 else None
    first_offsets = next(
        ds for c, key, ds in candidates if c == max_count and key == first
    )
    return ("optimal", max_count, first, second, first_offsets)


def _engine_key(sol):
    return sol.initial_offset, sol.sequence


@pytest.mark.parametrize("seed", range(400))
def test_drift_engine_matches_brute_force(seed):
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
    max_change = rng.randint(0, 12)
    min_hits = rng.randint(1, 3)

    expected = brute_force_drift(a, b, lo, hi, max_change, min_hits)
    r = adjudicate_drift(a, b, lo, hi, max_change, min_hits)

    assert r.status == expected[0]
    assert r.matched_count == expected[1]
    if expected[0] == "no_solution":
        assert r.solution is None and r.witness is None
        return

    assert _engine_key(r.solution) == expected[2]
    assert r.solution.offsets == expected[4]
    if expected[3] is None:
        assert r.uniqueness == "unique"
        assert r.witness is None
    else:
        assert r.uniqueness == "ambiguous"
        assert _engine_key(r.witness) == expected[3]


def test_drift_duplicate_code_streams_matches_brute_force():
    # 全部同码：候选最密集、分叉最多，专门检验见证的“最晚分叉”选择。
    for seed in range(200):
        rng = random.Random(seed)
        n, m = rng.randint(2, 6), rng.randint(2, 6)

        def mono(size):
            t = 0
            out = []
            for _ in range(size):
                t += rng.randint(1, 5)
                out.append((t, "X"))
            return out

        a, b = mono(n), mono(m)
        max_change = rng.randint(0, 6)
        expected = brute_force_drift(a, b, -10, 10, max_change, 1)
        r = adjudicate_drift(a, b, -10, 10, max_change, 1)
        assert r.status == expected[0]
        if expected[0] == "optimal":
            assert _engine_key(r.solution) == expected[2]
            if expected[3] is None:
                assert r.uniqueness == "unique"
                assert r.witness is None
            else:
                assert r.uniqueness == "ambiguous"
                assert _engine_key(r.witness) == expected[3]


def test_drift_witness_offsets_are_actual_pair_deltas():
    # 见证方案的逐对偏移也必须等于该对真实时间差，且相邻变化不越界。
    rng = random.Random(424242)
    checked = 0
    for _ in range(300):
        n, m = rng.randint(2, 6), rng.randint(2, 6)

        def mono(size):
            t = 0
            out = []
            for _ in range(size):
                t += rng.randint(1, 5)
                out.append((t, "X"))
            return out

        a, b = mono(n), mono(m)
        max_change = rng.randint(0, 6)
        r = adjudicate_drift(a, b, -10, 10, max_change, 1)
        if r.status != "optimal" or r.witness is None:
            continue
        checked += 1
        for sol in (r.solution, r.witness):
            for pos, ((i, j), d) in enumerate(zip(sol.sequence, sol.offsets)):
                assert d == a[i][0] - b[j][0]
                if pos:
                    assert abs(d - sol.offsets[pos - 1]) <= max_change
    assert checked >= 5  # 确认确实在歧义实例上做了校验
