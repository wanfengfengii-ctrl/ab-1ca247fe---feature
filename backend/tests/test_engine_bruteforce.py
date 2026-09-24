"""差分测试：引擎 vs 暴力枚举全部有序配对方案。

暴力枚举规模：n,m ≤ 6 时有序配对方案数至多 Σ C(n,k)C(m,k) ≤ 924，
足以覆盖同码冲突、跳变切点、同分排序等全部结构。
"""

from __future__ import annotations

import itertools
import random

import pytest

from app.engine import SIGN_NAME, SIGN_RANK, adjudicate


def brute_force(a, b, offset_min, offset_max, jump, min_hits):
    """返回 (status, max_count, first_key, second_key)。

    方案键：(d, sign_rank, pairs_before_jump, sequence)。
    """
    n, m = len(a), len(b)
    candidates = []  # (count, key, dict)
    for k in range(1, min(n, m) + 1):
        for ia in itertools.combinations(range(n), k):
            for jb in itertools.combinations(range(m), k):
                if not all(a[ia[t]][1] == b[jb[t]][1] for t in range(k)):
                    continue
                deltas = [a[ia[t]][0] - b[jb[t]][0] for t in range(k)]
                seq = tuple(zip(ia, jb))
                # 无跳变解释
                d0 = deltas[0]
                if all(x == d0 for x in deltas) and offset_min <= d0 <= offset_max:
                    candidates.append(
                        (k, (d0, SIGN_RANK[0], k, seq))
                    )
                # 跳变解释：枚举切点 t（前 t 对为前段）
                for t in range(1, k):
                    d = deltas[0]
                    if not (offset_min <= d <= offset_max):
                        break  # d 只由首个 delta 决定
                    if not all(x == d for x in deltas[:t]):
                        break
                    d2 = deltas[t]
                    if not all(x == d2 for x in deltas[t:]):
                        continue
                    if d2 == d + jump:
                        sign = +1
                    elif d2 == d - jump:
                        sign = -1
                    else:
                        continue
                    candidates.append(
                        (k, (d, SIGN_RANK[sign], t, seq))
                    )
    if not candidates:
        return ("no_solution", 0, None, None)
    max_count = max(c for c, _ in candidates)
    if max_count < min_hits:
        return ("no_solution", max_count, None, None)
    keys = sorted({key for c, key in candidates if c == max_count})
    first = keys[0]
    second = keys[1] if len(keys) > 1 else None
    return ("optimal", max_count, first, second)


def _engine_key(sol):
    return (
        sol.initial_offset,
        SIGN_RANK[sol.sign],
        sol.pairs_before_jump,
        sol.sequence,
    )


@pytest.mark.parametrize("seed", range(400))
def test_engine_matches_brute_force(seed):
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
    jump = rng.randint(1, 12)
    min_hits = rng.randint(1, 3)

    expected = brute_force(a, b, lo, hi, jump, min_hits)
    r = adjudicate(a, b, lo, hi, jump, min_hits)

    assert r.status == expected[0]
    assert r.matched_count == expected[1]
    if expected[0] == "no_solution":
        assert r.solution is None and r.witness is None
        return

    assert _engine_key(r.solution) == expected[2]
    if expected[3] is None:
        assert r.uniqueness == "unique"
        assert r.witness is None
    else:
        assert r.uniqueness == "ambiguous"
        assert _engine_key(r.witness) == expected[3]


def test_duplicate_code_streams_matches_brute_force():
    # 重复事件码专项：全部同码（最容易就近错配）
    rng = random.Random(777)
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
        jump = rng.randint(1, 8)
        expected = brute_force(a, b, -12, 12, jump, 1)
        r = adjudicate(a, b, -12, 12, jump, 1)
        assert r.status == expected[0]
        if expected[0] == "optimal":
            assert _engine_key(r.solution) == expected[2]
            if expected[3] is None:
                assert r.uniqueness == "unique"
            else:
                assert r.uniqueness == "ambiguous"
                assert _engine_key(r.witness) == expected[3]


def test_sign_name_consistency():
    # 见证/首解方向名在 API 层依赖此映射。
    assert SIGN_NAME[0] == "none"
    assert SIGN_NAME[-1] == "minus"
    assert SIGN_NAME[+1] == "plus"
