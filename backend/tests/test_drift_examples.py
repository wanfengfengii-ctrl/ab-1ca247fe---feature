"""缓变校时引擎的手工用例：漂移识别、边界、规范序、唯一/歧义、无解。"""

from __future__ import annotations

from app.drift import adjudicate_drift


def S(pairs):
    """[(time, code), ...] 简写。"""
    return pairs


def test_gradual_drift_matched_that_static_model_rejects():
    # 逐对实际偏移 -2, 0, +2, +4：既非固定偏移也不是一次跳变。
    a = S([(0, "A"), (10, "B"), (20, "C"), (30, "D")])
    b = S([(2, "A"), (10, "B"), (18, "C"), (26, "D")])

    # 变化上限 1：连不成 2 对以上 → 无解
    r = adjudicate_drift(a, b, -10, 10, 1, 2)
    assert r.status == "no_solution"
    assert r.matched_count == 1

    # 变化上限 2：四对全部命中
    r = adjudicate_drift(a, b, -10, 10, 2, 2)
    assert r.status == "optimal"
    assert r.matched_count == 4
    assert r.uniqueness == "unique"
    assert r.solution.sequence == ((0, 0), (1, 1), (2, 2), (3, 3))
    assert r.solution.offsets == (-2, 0, 2, 4)
    assert r.solution.initial_offset == -2


def test_zero_change_means_constant_offset():
    # max_change=0 退化为固定偏移链：同码配对按序全取。
    a = S([(0, "X"), (10, "Y"), (20, "Z")])
    b = S([(10, "X"), (20, "Y"), (30, "Z")])
    r = adjudicate_drift(a, b, -100, 100, 0, 2)
    assert r.status == "optimal"
    assert r.matched_count == 3
    assert r.solution.offsets == (-10, -10, -10)


def test_codes_must_match_and_indices_increase():
    a = S([(0, "A"), (5, "B"), (9, "C"), (30, "D")])
    b = S([(0, "X"), (5, "B"), (9, "C"), (30, "D")])
    r = adjudicate_drift(a, b, -100, 100, 5, 2)
    assert r.matched_count == 3
    assert r.solution.sequence == ((1, 1), (2, 2), (3, 3))


def test_offset_must_stay_in_range_for_every_pair():
    # 漂移把偏移带出范围的对不能选。
    a = S([(0, "A"), (10, "B"), (20, "C")])
    b = S([(0, "A"), (10, "B"), (30, "C")])  # 第三对差值 -10
    r = adjudicate_drift(a, b, -5, 5, 10, 1)
    assert r.status == "optimal"
    assert r.matched_count == 2
    assert r.solution.sequence == ((0, 0), (1, 1))


def test_no_pair_in_range():
    a = S([(0, "A"), (10, "B")])
    b = S([(1000, "A"), (1010, "B")])
    r = adjudicate_drift(a, b, 0, 10, 5, 1)
    assert r.status == "no_solution"
    assert r.matched_count == 0
    assert r.offsets_evaluated == 0


def test_min_hits_boundary():
    a = S([(0, "A"), (100, "B")])
    b = S([(0, "A"), (200, "Z")])
    r = adjudicate_drift(a, b, -50, 50, 50, 2)
    assert r.status == "no_solution"
    assert r.matched_count == 1
    r2 = adjudicate_drift(a, b, -50, 50, 50, 1)
    assert r2.status == "optimal"
    assert r2.matched_count == 1


def test_canonical_first_by_initial_offset():
    # 两条互不兼容的等长链（max_change=0）：d=0 的链与 d=3 的链；
    # 无法接续，故最大长度为 2，取初始偏移更小者为首解、另一个为见证。
    a = S([(0, "A"), (10, "B"), (100, "C"), (110, "D")])
    b = S([(0, "A"), (10, "B"), (97, "C"), (107, "D")])
    r = adjudicate_drift(a, b, -5, 5, 0, 2)
    assert r.matched_count == 2
    assert r.uniqueness == "ambiguous"
    assert r.solution.initial_offset == 0
    assert r.solution.sequence == ((0, 0), (1, 1))
    assert r.witness.initial_offset == 3
    assert r.witness.sequence == ((2, 2), (3, 3))


def test_canonical_tie_by_pair_sequence():
    # 相同初始偏移、相同最大长度：不同配对序列按字典序取首解，另一个为见证。
    # 码全部相同，时间设计成从同一起点出发有两条同长延续。
    a = S([(0, "X"), (10, "X"), (20, "X")])
    b = S([(0, "X"), (10, "X"), (20, "X")])
    r = adjudicate_drift(a, b, 0, 0, 0, 3)
    # 差值 0 的配对为 (0,0),(1,1),(2,2)，且只能成这一条 3 链 → 唯一
    assert r.uniqueness == "unique"
    assert r.solution.sequence == ((0, 0), (1, 1), (2, 2))


def test_witness_on_fork_is_canonical_second():
    # 同一首对、同长，第二位不同延续；分叉越晚在规范序越靠前。
    # A=[0,10,20]，B=[0,8,9,10]，窗口 9：长度 3 的链有
    #   (0,0)(1,1)(2,2) 偏移 0,2,11（变化 2,9）
    #   (0,0)(1,1)(2,3) 偏移 0,2,10（变化 2,8）
    #   (0,0)(1,2)(2,3) 偏移 0,1,10（变化 1,9）
    # 偏移范围取 [0,12] 以排除首对为负偏移的等长链，只留下同首对的三条。
    a = S([(0, "X"), (10, "X"), (20, "X")])
    b = S([(0, "X"), (8, "X"), (9, "X"), (10, "X")])
    r = adjudicate_drift(a, b, 0, 12, 9, 3)
    assert r.matched_count == 3
    assert r.uniqueness == "ambiguous"
    assert r.solution.sequence == ((0, 0), (1, 1), (2, 2))
    assert r.solution.offsets == (0, 2, 11)
    # 见证取与首解最晚分叉者：共享前两对，末位分叉
    assert r.witness.sequence == ((0, 0), (1, 1), (2, 3))
    assert r.witness.offsets == (0, 2, 10)


def test_change_limit_is_inclusive_boundary():
    # 相邻差恰好等于上限必须放行：偏移 -3, 0, +3，变化均为 3。
    a = S([(0, "A"), (10, "B"), (20, "C")])
    b = S([(3, "A"), (10, "B"), (17, "C")])
    r = adjudicate_drift(a, b, -10, 10, 3, 3)
    assert r.status == "optimal"
    assert r.solution.offsets == (-3, 0, 3)
    # 上限 2：变化 3 不允许，最长 1 → 无解
    r2 = adjudicate_drift(a, b, -10, 10, 2, 2)
    assert r2.status == "no_solution"
    assert r2.matched_count == 1


def test_skipped_events_drift_chain():
    # 漏记 + 漂移：最长链跳过中间事件。
    a = S([(0, "T"), (5, "U"), (12, "V"), (24, "W")])
    b = S([(2, "T"), (10, "V"), (18, "W")])  # 偏移 -2, +2, +6
    r = adjudicate_drift(a, b, -10, 10, 4, 2)
    assert r.status == "optimal"
    assert r.matched_count == 3
    assert r.solution.sequence == ((0, 0), (2, 1), (3, 2))
    assert r.solution.offsets == (-2, 2, 6)


def test_diagnostics_counts():
    a = S([(0, "A"), (10, "B")])
    b = S([(0, "A"), (10, "B"), (20, "C")])
    r = adjudicate_drift(a, b, -5, 5, 1, 1)
    assert r.candidates_evaluated == 2
    assert r.offsets_evaluated == 1
