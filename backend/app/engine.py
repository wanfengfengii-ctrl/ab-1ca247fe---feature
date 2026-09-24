"""束流事件流复核裁决引擎。

业务模型
========
两块采集卡各自产生一条事件流 A / B，事件为 ``(time, code)``。一次复核方案
选出若干配对 ``(i, j)``：

* 两侧事件码相同（``code_a == code_b``）；
* 两个索引都严格递增（保持两侧顺序，未选中事件可跳过）；
* 跳变发生前，每对满足 ``tA_i - tB_j = d``，``d`` 为初始偏移，必须是
  ``[offset_min, offset_max]`` 内的整数；
* 方案至多在两个已匹配事件之间发生一次永久跳变，跳变后每对满足
  ``tA_i - tB_j = d + s*J``，``J`` 为固定跳变量，``s ∈ {-1, 0, +1}``；
* 跳变必须夹在两对已匹配事件之间（跳变前、后各至少一对）。

优化目标与规范序
================
先最大化配对数；不足最低命中数即判无解。达到同一最大配对数时按以下键
升序取唯一的规范首解：

1. 初始偏移 ``d``；
2. 跳变方向：无跳变、减（``-J``）、加（``+J``）；
3. 跳变前匹配数 ``k``；
4. 配对索引序列 ``((i0,j0),(i1,j1),...)`` 字典序。

关键结构性质
============
时间严格递增 ⇒ 对固定差值 ``delta``，事件 A 的每个索引 i 至多与一个 B 事件
满足 ``tB_j = tA_i - delta``。把该差值桶内配对按 i 排序，则 j 也严格递增
（``tA`` 递增 ⇒ ``tB = tA - delta`` 递增 ⇒ ``j`` 递增）。因此桶内所有配对
两两兼容、构成唯一一条链，不存在“同一 (d, 方向, k) 的不同序列”，配对索引
序列键只可能在跨桶比较时作为最后的防御性判据。引擎据此精确给出唯一/歧义
结论：歧义当且仅当另一个 (d, 方向) 组或同组另一个 k 能达到相同最大配对数。

缓变校时（可选 drift 模式）
==========================
初步对时后，两卡时钟可能并非一次突跳，而是在连续命中间缓慢漂移，固定偏移
与单次跳变模型会把真实同码事件拒之门外。``adjudicate_drift`` 不再使用固定
跳变量：每相邻两对已匹配事件的整数偏移变化（(tA−tB) 之差）的绝对值不得
超过用户给出的 ``max_drift``。可行方案为配对序列：同码、两侧索引严格递增、
每对偏移位于 [offset_min, offset_max]、相邻偏移变化不超上限。规范序：先
最大化命中数，再按 (初始偏移, 配对索引序列) 升序取首解；歧义 ⇔ 存在另一份
同数方案，见证为规范序下的第二份。

算法：可行配对即 DAG 节点（边 = 索引递增且偏移差在限内），最长链即最优。
固定 B 索引 j 时配对偏移 tA_i − tB_j 随 i 严格递增（tA 严格递增），故每列
可按偏移二分窗口，反向 DP 在 O(配对数 × m) 内完成。首解逐位贪心：首对取
(偏移, i, j) 最小者，之后每步取索引最小的可行后继。见证利用“与首解首次
不同的位置越晚候选越优”（分叉处首解该位必小于任何其他可行位），自后向前
找首个存在次小可行位的分叉点，即得规范序第二解。
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from typing import Optional

SIGN_NONE = 0
SIGN_MINUS = -1
SIGN_PLUS = +1

# 规范序中的方向优先级：无跳变(0) → 减(1) → 加(2)。
SIGN_RANK = {SIGN_NONE: 0, SIGN_MINUS: 1, SIGN_PLUS: 2}
SIGN_NAME = {SIGN_NONE: "none", SIGN_MINUS: "minus", SIGN_PLUS: "plus"}

Pair = tuple[int, int]
Seq = tuple[Pair, ...]


@dataclass(frozen=True)
class Solution:
    """一个完整可行方案。"""

    initial_offset: int
    sign: int
    pairs_before_jump: int
    sequence: Seq

    @property
    def matched_count(self) -> int:
        return len(self.sequence)


@dataclass
class Adjudication:
    status: str  # "optimal" | "no_solution"
    matched_count: int
    min_hits: int
    solution: Optional[Solution]
    uniqueness: Optional[str]  # "unique" | "ambiguous" | None
    witness: Optional[Solution]
    offsets_evaluated: int
    groups_evaluated: int


def _solution_key(sol: Solution) -> tuple:
    return (
        sol.initial_offset,
        SIGN_RANK[sol.sign],
        sol.pairs_before_jump,
        sol.sequence,
    )


def _build_diff_buckets(
    stream_a: list[tuple[int, str]],
    stream_b: list[tuple[int, str]],
) -> dict[int, list[Pair]]:
    """时间差 -> 桶内配对（按 A 索引排序，B 索引随之严格递增）。"""
    by_diff: dict[int, list[Pair]] = {}
    for i, (ta, ca) in enumerate(stream_a):
        for j, (tb, cb) in enumerate(stream_b):
            if ca == cb:
                by_diff.setdefault(ta - tb, []).append((i, j))
    for pairs in by_diff.values():
        pairs.sort()
    return by_diff


def _suffix_after(pairs: list[Pair], i: int, j: int) -> list[Pair]:
    """桶内两个索引都严格大于 (i, j) 的后缀（含起点）；桶有序故为连续后缀。"""
    for idx, (qi, qj) in enumerate(pairs):
        if qi > i and qj > j:
            return pairs[idx:]
    return []


def adjudicate(
    stream_a: list[tuple[int, str]],
    stream_b: list[tuple[int, str]],
    offset_min: int,
    offset_max: int,
    jump: int,
    min_hits: int,
) -> Adjudication:
    """对两条事件流发起裁决，返回规范首解（及歧义见证）。"""
    by_diff = _build_diff_buckets(stream_a, stream_b)

    # 每个 (d, sign) 组记录：最大配对数、各可达 k 的 (总数, 序列)、组首解。
    @dataclass
    class Group:
        max_len: int
        by_k: dict[int, tuple[int, Seq]]
        first: Solution

    groups: dict[tuple[int, int], Group] = {}

    # —— 无跳变：桶内全部配对即为唯一最长链 ——
    for d, pairs in by_diff.items():
        if not offset_min <= d <= offset_max:
            continue
        seq: Seq = tuple(pairs)
        if len(seq) < 1:
            continue
        groups[(d, SIGN_NONE)] = Group(
            len(seq),
            {len(seq): (len(seq), seq)},
            Solution(d, SIGN_NONE, len(seq), seq),
        )

    # —— 一次跳变：枚举跳变前最后一对（决定 k），跳变后取可行后缀 ——
    for d, pre_pairs in by_diff.items():
        if not offset_min <= d <= offset_max:
            continue
        for sign in (SIGN_MINUS, SIGN_PLUS):
            post_pairs = by_diff.get(d + sign * jump)
            if not post_pairs:
                continue
            by_k: dict[int, tuple[int, Seq]] = {}
            for p, pair in enumerate(pre_pairs):
                k = p + 1  # 跳变前链包含桶内前缀全部配对
                suffix = _suffix_after(post_pairs, pair[0], pair[1])
                if not suffix:
                    continue  # 跳变后至少要保留一对
                total = k + len(suffix)
                by_k[k] = (total, tuple(pre_pairs[: p + 1]) + tuple(suffix))
            if not by_k:
                continue
            max_len = max(total for total, _ in by_k.values())
            k0 = min(k for k, (total, _) in by_k.items() if total == max_len)
            groups[(d, sign)] = Group(
                max_len, by_k, Solution(d, sign, k0, by_k[k0][1])
            )

    offsets_evaluated = {d for d, _ in groups}
    if not groups:
        return Adjudication(
            "no_solution", 0, min_hits, None, None, None,
            len(offsets_evaluated), 0,
        )

    # 枚举每个 (d, sign) 组内全部可达 k 的方案；同一 (d, sign, k) 下序列唯一
    # （桶内配对天然成链），故扁平候选集即为全部不同方案，无需再按序列去重。
    all_solutions: list[Solution] = []
    for (d, sign), group in groups.items():
        if sign == SIGN_NONE:
            all_solutions.append(group.first)
        else:
            for k, (total, seq) in group.by_k.items():
                all_solutions.append(Solution(d, sign, k, seq))

    ranked = sorted(
        all_solutions,
        key=lambda s: (-s.matched_count,) + _solution_key(s),
    )
    winner = ranked[0]
    best_len = winner.matched_count

    if best_len < min_hits:
        return Adjudication(
            "no_solution", best_len, min_hits, None, None, None,
            len(offsets_evaluated), len(groups),
        )

    # 规范序下紧随首解的不同方案即为歧义见证。
    witness: Optional[Solution] = None
    for cand in ranked[1:]:
        if cand.matched_count == best_len and _solution_key(cand) != _solution_key(winner):
            witness = cand
            break

    return Adjudication(
        "optimal",
        best_len,
        min_hits,
        winner,
        "unique" if witness is None else "ambiguous",
        witness,
        len(offsets_evaluated),
        len(groups),
    )


# ==================== 缓变校时（可选 drift 模式） ====================


@dataclass(frozen=True)
class DriftSolution:
    """缓变校时模式下的一个完整可行方案。"""

    sequence: Seq  # 配对索引序列 ((i0,j0),(i1,j1),...)
    offsets: tuple[int, ...]  # 每对实际偏移 tA_i − tB_j

    @property
    def matched_count(self) -> int:
        return len(self.sequence)

    @property
    def initial_offset(self) -> int:
        return self.offsets[0]


@dataclass
class DriftAdjudication:
    status: str  # "optimal" | "no_solution"
    matched_count: int
    min_hits: int
    solution: Optional[DriftSolution]
    uniqueness: Optional[str]  # "unique" | "ambiguous" | None
    witness: Optional[DriftSolution]
    pairs_evaluated: int  # 偏移范围内的同码配对（DAG 节点）数


def adjudicate_drift(
    stream_a: list[tuple[int, str]],
    stream_b: list[tuple[int, str]],
    offset_min: int,
    offset_max: int,
    max_drift: int,
    min_hits: int,
) -> DriftAdjudication:
    """缓变校时裁决：相邻已匹配对的偏移变化不超过 max_drift 的最长配对链。

    规范序：先最大化命中数，再按 (初始偏移, 配对索引序列) 升序取首解；
    歧义时见证为规范序下的第二份不同方案。
    """
    n, m = len(stream_a), len(stream_b)

    # —— 可行配对（DAG 节点）：同码且偏移落在 [offset_min, offset_max] ——
    # 固定 B 索引 j 时，配对偏移 tA_i − tB_j 随 i 严格递增（tA 严格递增），
    # 故每列节点按 i 排列后偏移天然有序，可用二分定位任意偏移窗口。
    col_i: list[list[int]] = [[] for _ in range(m)]
    col_d: list[list[int]] = [[] for _ in range(m)]
    is_node = [bytearray(m) for _ in range(n)]
    delta = [[0] * m for _ in range(n)]
    pos_in_col = [[0] * m for _ in range(n)]
    for j in range(m):
        tbj, cbj = stream_b[j]
        ci = col_i[j]
        cd = col_d[j]
        for i in range(n):
            tai, cai = stream_a[i]
            if cai != cbj:
                continue
            d = tai - tbj
            if offset_min <= d <= offset_max:
                is_node[i][j] = 1
                delta[i][j] = d
                pos_in_col[i][j] = len(ci)
                ci.append(i)
                cd.append(d)

    pairs_evaluated = sum(len(c) for c in col_i)
    if pairs_evaluated == 0:
        return DriftAdjudication("no_solution", 0, min_hits, None, None, None, 0)

    # —— 反向 DP：bwd[i][j] = 从 (i,j) 出发的最长可行链长度 ——
    # 边 (i,j) → (i',j')：i'>i、j'>j 且 |delta' − delta| ≤ max_drift。
    # 按 i 降序逐行处理：整行先查询（列结构中此时恰有 i'>i 的值），再整行写回，
    # 因此同行节点互不影响（边要求 i 严格递增）。
    col_f = [[0] * len(c) for c in col_i]
    bwd = [[0] * m for _ in range(n)]
    w = max_drift
    longest = 0
    for i in range(n - 1, -1, -1):
        row_vals = []
        di = delta[i]
        ni = is_node[i]
        for j in range(m):
            if not ni[j]:
                continue
            d0 = di[j]
            lo = d0 - w
            hi = d0 + w
            best = 0
            for jp in range(j + 1, m):
                ci = col_i[jp]
                if not ci:
                    continue
                lo_pos = bisect_right(ci, i)  # 列内 i' > i 的起点
                cd = col_d[jp]
                a = bisect_left(cd, lo, lo_pos)
                b = bisect_right(cd, hi, lo_pos)
                if a < b:
                    v = max(col_f[jp][a:b])
                    if v > best:
                        best = v
            row_vals.append((j, best + 1))
        for j, val in row_vals:
            bwd[i][j] = val
            col_f[j][pos_in_col[i][j]] = val
            if val > longest:
                longest = val

    if longest < min_hits:
        return DriftAdjudication(
            "no_solution", longest, min_hits, None, None, None, pairs_evaluated
        )

    def min_succ(iu: int, ju: int, rem: int, exclude: Optional[Pair] = None):
        """(iu,ju) 的后继中 bwd = rem 的 (i,j) 字典序最小者。"""
        du = delta[iu][ju]
        for ip in range(iu + 1, n):
            rown = is_node[ip]
            rowb = bwd[ip]
            rowd = delta[ip]
            for jp in range(ju + 1, m):
                if rown[jp] and rowb[jp] == rem and -w <= rowd[jp] - du <= w:
                    if exclude is not None and ip == exclude[0] and jp == exclude[1]:
                        continue
                    return (ip, jp)
        return None

    def chain_from(start: Pair, length: int) -> list[Pair]:
        """从 start 出发逐位取 (i,j) 最小可行后继，还原长度为 length 的链。"""
        out = [start]
        for rem in range(length - 1, 0, -1):
            iu, ju = out[-1]
            nxt = min_succ(iu, ju, rem)
            assert nxt is not None  # bwd 定义保证可行后继存在
            out.append(nxt)
        return out

    # —— 规范首解：首对取 (偏移, i, j) 最小者，之后逐位取索引最小可行后继 ——
    start = None
    start_key = None
    for i in range(n):
        rown = is_node[i]
        rowb = bwd[i]
        rowd = delta[i]
        for j in range(m):
            if rown[j] and rowb[j] == longest:
                key = (rowd[j], i, j)
                if start_key is None or key < start_key:
                    start_key = key
                    start = (i, j)
    assert start is not None
    first = chain_from(start, longest)

    # —— 见证：与首解首次不同的位置越晚候选越优（分叉处首解该位必小于任何
    # 其他可行位），故自后向前找首个存在次小可行位的分叉点即为规范序第二解 ——
    witness_seq: Optional[list[Pair]] = None
    for p in range(longest - 1, -1, -1):
        if p == 0:
            # 首对不同：bwd = longest 的节点中 (偏移, i, j) 次小者
            alt = None
            alt_key = None
            for i in range(n):
                rown = is_node[i]
                rowb = bwd[i]
                rowd = delta[i]
                for j in range(m):
                    if rown[j] and rowb[j] == longest and (i, j) != first[0]:
                        key = (rowd[j], i, j)
                        if alt_key is None or key < alt_key:
                            alt_key = key
                            alt = (i, j)
            cand = alt
        else:
            iu, ju = first[p - 1]
            cand = min_succ(iu, ju, longest - p, exclude=first[p])
        if cand is not None:
            witness_seq = first[:p] + chain_from(cand, longest - p)
            break

    def to_solution(seq: list[Pair]) -> DriftSolution:
        return DriftSolution(
            sequence=tuple(seq),
            offsets=tuple(delta[i][j] for i, j in seq),
        )

    witness = to_solution(witness_seq) if witness_seq is not None else None
    return DriftAdjudication(
        "optimal",
        longest,
        min_hits,
        to_solution(first),
        "unique" if witness is None else "ambiguous",
        witness,
        pairs_evaluated,
    )
