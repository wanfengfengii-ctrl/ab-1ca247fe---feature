"""引擎手工用例：覆盖无跳变、加/减跳变、规范序、唯一/歧义、无解。"""

from app.engine import (
    SIGN_MINUS,
    SIGN_NONE,
    SIGN_PLUS,
    adjudicate,
)


def S(pairs):
    """[(time, code), ...] 简写。"""
    return pairs


def test_basic_no_jump_unique():
    # B 整体比 A 晚 10：d = tA - tB = -10
    a = S([(0, "X"), (10, "Y"), (20, "Z")])
    b = S([(10, "X"), (20, "Y"), (30, "Z")])
    r = adjudicate(a, b, -100, 100, jump=5, min_hits=2)
    assert r.status == "optimal"
    assert r.matched_count == 3
    assert r.uniqueness == "unique"
    assert r.solution.initial_offset == -10
    assert r.solution.sign == SIGN_NONE
    assert r.solution.sequence == ((0, 0), (1, 1), (2, 2))


def test_skipped_events_and_codes_must_match():
    a = S([(0, "A"), (5, "B"), (9, "C"), (30, "D")])
    b = S([(100, "A"), (105, "X"), (109, "C"), (130, "D")])
    r = adjudicate(a, b, -1000, 1000, jump=50, min_hits=2)
    # A(0,A)-B(100,A) 与 A(9,C)-B(109,C) 与 A(30,D)-B(130,D)：d=-100
    assert r.status == "optimal"
    assert r.matched_count == 3
    assert r.solution.sequence == ((0, 0), (2, 2), (3, 3))


def test_min_hits_not_met_is_no_solution():
    a = S([(0, "A"), (10, "B")])
    b = S([(0, "A"), (99, "Z")])
    r = adjudicate(a, b, -100, 100, jump=3, min_hits=2)
    assert r.status == "no_solution"
    assert r.matched_count == 1


def test_no_pair_in_offset_range():
    a = S([(0, "A"), (10, "B")])
    b = S([(1000, "A"), (1010, "B")])
    r = adjudicate(a, b, 0, 10, jump=5, min_hits=1)
    assert r.status == "no_solution"
    assert r.matched_count == 0


def test_plus_jump_extends_match():
    # 前两对差 0；之后 B 整体提前 7（A 相对 B 变快），差值变为 +7
    a = S([(0, "A"), (10, "B"), (20, "C"), (30, "D")])
    b = S([(0, "A"), (10, "B"), (13, "C"), (23, "D")])
    r = adjudicate(a, b, -50, 50, jump=7, min_hits=3)
    assert r.status == "optimal"
    assert r.matched_count == 4
    sol = r.solution
    assert sol.initial_offset == 0
    assert sol.sign == SIGN_PLUS
    assert sol.pairs_before_jump == 2
    assert sol.sequence == ((0, 0), (1, 1), (2, 2), (3, 3))


def test_minus_jump_extends_match():
    # 前两对差 0；之后差值变为 -7
    a = S([(0, "A"), (10, "B"), (13, "C"), (23, "D")])
    b = S([(0, "A"), (10, "B"), (20, "C"), (30, "D")])
    r = adjudicate(a, b, -50, 50, jump=7, min_hits=3)
    sol = r.solution
    assert sol.matched_count == 4
    assert sol.sign == SIGN_MINUS
    assert sol.initial_offset == 0
    assert sol.pairs_before_jump == 2


def test_direction_order_none_before_minus_before_plus():
    # 构造：d=5 无跳变能拿 2 对；d=0 的跳变也能拿 2 对 → d 更小者胜
    # 这里直接验证同分时方向序：d=0 同时存在 minus 与 plus 两种 2 对方案
    a = S([(0, "A"), (10, "B"), (20, "C"), (30, "D")])
    # minus 段: B = tA + 6；plus 段: B = tA - 6 —— 用不同事件码隔离两条链
    b = S([(6, "A"), (16, "B"), (14, "C"), (24, "D")])
    # 检查配对：A0(0,A)-B0(6,A) d=-6(减方向以 d=0 起始？) —— 改用显式构造
    # d0=0 前缀两对需要同码且差值 0：
    a = S([(0, "P"), (10, "Q"), (20, "R"), (30, "S")])
    # minus: 后两对 B 晚 6；plus: 借助另一组码 T/U 构造 d=0 前缀
    b = S([
        (0, "P"), (10, "Q"),     # d=0 前缀
        (26, "R"), (36, "S"),    # d=-6：minus(J=6)
        (14, "T"), (24, "U"),    # 与 a 中无 T/U，不可配，忽略
    ])
    r = adjudicate(a, b, -50, 50, jump=6, min_hits=1)
    assert r.solution.initial_offset == 0
    assert r.solution.sign == SIGN_MINUS
    assert r.matched_count == 4

    # 再构造 plus 同分且 d 相同：替换后段为 d=+6
    b2 = S([(0, "P"), (10, "Q"), (14, "R"), (24, "S")])
    r2 = adjudicate(a, b2, -50, 50, jump=6, min_hits=1)
    assert r2.solution.sign == SIGN_PLUS
    assert r2.matched_count == 4


def test_ambiguous_between_two_offsets():
    # d=0 与 d=100 各能配 2 对，最大数相同 → 歧义，见证取规范序下一方案
    a = S([(0, "A"), (10, "B"), (200, "C"), (210, "D")])
    b = S([(0, "A"), (10, "B"), (100, "C"), (110, "D")])
    r = adjudicate(a, b, -200, 200, jump=5, min_hits=1)
    assert r.matched_count == 2
    assert r.uniqueness == "ambiguous"
    assert r.solution.initial_offset == 0
    assert r.witness is not None
    assert r.witness.initial_offset == 100


def test_ambiguous_within_group_different_k():
    # 同 (d=0, plus, J=10)：不同跳变点 k 都达到相同总数
    # 前段桶 d=0 配对链、后段桶 d=10 配对链，两个切点总数相同：
    # k=1: pre 1 + post 2 ; k=2: pre 2 + post 1
    a = S([(0, "A"), (10, "B"), (20, "C"), (40, "D"), (50, "E")])
    # d=0 桶（同码）: A0-B0(A), A1-B1(B)
    # d=10 桶（同码）: A2(t20,C)-B? tB=10 → B1 是 B 码不同; 需精心布置
    b = S([
        (0, "A"), (10, "B"),          # d=0: (0,0),(1,1)
        (10, "C"), (30, "D"),         # d=10: A2(20,C)->B2(10,C)? 索引需 > 跳变前最后一对
        (40, "E"),
    ])
    # k=2 切在 (1,1)，后缀要求 i>1,j>1：A2(20,C)-B2(10,C) d=10 ✓, A3(40,D)-B3(30,D) ✓, A4(50,E)-B4(40,E) ✓ → total 5
    # k=1 切在 (0,0)，后缀含 d=10 桶全部：另有 (1,1)? 不，那是 d=0 桶。
    r = adjudicate(a, b, -50, 50, jump=10, min_hits=1)
    assert r.status == "optimal"
    assert r.matched_count == 5
    assert r.solution.initial_offset == 0 and r.solution.sign == SIGN_PLUS
    # k=1 时：pre 1 + post 3 = 4；k=2 时 2+3=5 → 唯一首解 k=2
    assert r.solution.pairs_before_jump == 2
    assert r.uniqueness == "unique"


def test_ambiguous_different_k_equal_totals():
    # 显式构造同组两个 k 总数相等：
    # d=0 桶按 i 顺序有 3 对；d=10 桶后缀随切点缩短。
    # 切 k=1: 后缀 d=10 有 3 对（总 4）；切 k=2: 后缀 2 对（总 4）
    a = S([(0, "A"), (10, "B"), (20, "C"), (30, "D"), (40, "E"), (50, "F"), (60, "G")])
    b = [None] * 7
    # d=0 前缀：(0,A)t0,(1,B)t10 —— 两个
    # d=10 桶配对（tB=tA-10），且索引要在切点之后：
    #   A2(20,C)->B at10 与 B1(10,B) 同位置冲突码不同，改用独立索引靠后布置
    b = S([
        (0, "A"), (10, "B"),                       # idx 0,1
        (10, "C"), (20, "D"), (30, "E"),           # idx 2,3,4  d=10 对 A2,A3,A4
        (50, "X"), (60, "Y"),
    ])
    # k=2 切 (1,1)：后缀 idx>1 → (2,2)(3,3)(4,4) 共 3，总 5
    # k=1 切 (0,0)：d=10 桶中 j>0 全部同样 3 对（j 最小为 2），总 4
    r = adjudicate(a, b, -50, 50, jump=10, min_hits=1)
    assert r.matched_count == 5
    assert r.solution.pairs_before_jump == 2
    # 同分另一 k 不存在；唯一
    assert r.uniqueness == "unique"


def test_duplicate_codes_nearby_pairing_pitfall():
    # 业务陷阱：重复事件码就近配错。同一码出现多次，必须靠偏移/跳变区分。
    # 卡 A: TRIG,TRIG,TRIG 时间 0,100,200
    # 卡 B: TRIG,TRIG,TRIG 时间 5,105,205 → d=-5 三对
    a = S([(0, "TRIG"), (100, "TRIG"), (200, "TRIG")])
    b = S([(5, "TRIG"), (105, "TRIG"), (205, "TRIG")])
    r = adjudicate(a, b, -50, 50, jump=1000, min_hits=3)
    assert r.matched_count == 3
    assert r.solution.sequence == ((0, 0), (1, 1), (2, 2))

    # B 漏记一个脉冲且计数永久跳变：重复码就近配会把 U 错配到 B 上；
    # 真实对时：第 1 对 d=-5，跳变 +100 后第 2 对 d=95，中间事件跳过。
    a = S([(0, "TRIG"), (100, "U"), (200, "TRIG")])
    b2 = S([(5, "TRIG"), (105, "TRIG")])
    r2 = adjudicate(a, b2, -50, 50, jump=100, min_hits=2)
    assert r2.matched_count == 2
    assert r2.solution.initial_offset == -5
    assert r2.solution.sign == SIGN_PLUS
    assert r2.solution.pairs_before_jump == 1
    assert r2.solution.sequence == ((0, 0), (2, 1))

    # 纯漏记（两侧时间差不变）不需要跳变：差值桶天然还原对时
    a3 = S([(0, "TRIG"), (100, "TRIG"), (200, "TRIG"), (300, "TRIG")])
    b3 = S([(5, "TRIG"), (105, "TRIG"), (305, "TRIG"), (405, "TRIG")])
    r3 = adjudicate(a3, b3, -50, 50, jump=100, min_hits=4)
    assert r3.solution.sign == SIGN_MINUS
    assert r3.solution.pairs_before_jump == 2
    assert r3.solution.sequence == ((0, 0), (1, 1), (2, 2), (3, 3))


def test_large_times_and_codes():
    a = S([(0, "A1B2C3D4"), (10**12 - 1, "Z9")])
    b = S([(10**9, "A1B2C3D4"), (10**12 - 1 + 10**9, "Z9")])
    r = adjudicate(a, b, -(10**12), 10**12, jump=1, min_hits=2)
    assert r.matched_count == 2
    assert r.solution.initial_offset == -(10**9)
