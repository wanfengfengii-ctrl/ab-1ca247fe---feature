"""缓变校时（漂移）裁决引擎。

业务模型
========
两块采集卡完成初步对时后，时钟并非一次突跳，而会在连续命中间**缓慢漂移**。
固定偏移 / 单次跳变量模型会把真实同码事件拒之门外，因此提供可选的
“缓变校时”裁决：仍沿用两条事件流、允许偏移范围与最低命中数，但**不再
使用固定跳变量**。用户给出每相邻已匹配事件允许的最大整数偏移变化
``max_change``（≥0 的整数）。

一个方案选出若干配对 ``(i, j)``：

* 两侧事件码相同（``code_a == code_b``）；
* 两个索引都严格递增（保持两侧顺序，未选中事件可跳过）；
* 每对的时间差 ``tA_i - tB_j`` 都是 ``[offset_min, offset_max]`` 内的整数；
* 相邻两对的实际偏移之差（绝对值）不超过 ``max_change``
  （首对无约束，仅受偏移范围限制）。

优化目标与规范序
================
先最大化配对数；不足最低命中数即判无解。达到同一最大配对数时按以下键
升序取唯一的规范首解：

1. 初始偏移 ``d``（首对的实际偏移 ``tA - tB``）；
2. 配对索引序列 ``((i0,j0),(i1,j1),...)`` 字典序。

序列唯一决定各对偏移，因此上述键是全部方案上的全序；规范序下紧随首解的
不同方案即为歧义见证。

算法
====
把每个可行配对看作有向无环图的节点（索引递增保证无环），若配对 q 可接在
p 之后（``i_q > i_p`` 且 ``j_q > j_p`` 且 ``|δ_q - δ_p| ≤ max_change``）则连边，
最长链即最长路径。按 A 索引倒序做动态规划，转移需要在“列 j' > j 且差值
落在窗口 [δ±max_change] 内”的已处理节点中取最大值：每列 j 把该列全部候选
差值排序建静态骨架的区间最大值线段树，点更新、窗口查询均为对数级。

得到每个节点的最长后缀长度后，规范首解逐位贪心确定：首对在最长链起点中
按 ``(δ, i, j)`` 取最小，之后每一步在可行后继中按 ``(i, j)`` 取最小——字典序
比较下，逐位最小即整体最小。歧义见证取“与首解最晚分叉”的最小方案：分叉
位置越靠后，方案在规范序下越靠前，故从末位向首位找到第一个可分叉位置，
接最小分叉元素并贪心续接即得规范序第二解。
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from typing import Optional

Pair = tuple[int, int]
Seq = tuple[Pair, ...]
# 候选配对节点：(A 索引, B 索引, 该对实际偏移 tA - tB)
Node = tuple[int, int, int]


@dataclass(frozen=True)
class DriftSolution:
    """缓变校时模式下的一个完整可行方案。"""

    sequence: Seq
    offsets: tuple[int, ...]  # 逐对实际偏移 tA - tB，与 sequence 一一对应

    @property
    def initial_offset(self) -> int:
        return self.offsets[0]

    @property
    def matched_count(self) -> int:
        return len(self.sequence)


@dataclass
class DriftAdjudication:
    status: str  # "optimal" | "no_solution"
    matched_count: int
    min_hits: int
    solution: Optional[DriftSolution]
    uniqueness: Optional[str]  # "unique" | "ambiguous" | None
    witness: Optional[DriftSolution]
    offsets_evaluated: int  # 范围内出现过的不同偏移值个数
    candidates_evaluated: int  # 范围内同码候选配对数


def _solution_key(sol: DriftSolution) -> tuple:
    return (sol.initial_offset, sol.sequence)


# ---------- 区间最大值线段树（静态骨架，点更新取 max） ----------

def _st_build(size: int) -> list[int]:
    return [0] * (2 * size)


def _st_update(tree: list[int], size: int, pos: int, val: int) -> None:
    """把位置 pos 的值更新为 max(原值, val)。"""
    p = pos + size
    if tree[p] >= val:
        return
    tree[p] = val
    p >>= 1
    while p:
        merged = tree[2 * p] if tree[2 * p] >= tree[2 * p + 1] else tree[2 * p + 1]
        if tree[p] == merged:
            break  # 祖先不会变化，提前终止
        tree[p] = merged
        p >>= 1


def _st_query(tree: list[int], size: int, lo: int, hi: int) -> int:
    """闭区间 [lo, hi] 上的最大值（空区间为 0）。"""
    res = 0
    lo += size
    hi += size
    while lo <= hi:
        if lo & 1:
            if tree[lo] > res:
                res = tree[lo]
            lo += 1
        if not (hi & 1):
            if tree[hi] > res:
                res = tree[hi]
            hi -= 1
        lo >>= 1
        hi >>= 1
    return res


def _longest_suffix_lengths(
    candidates: list[Node],
    n: int,
    m: int,
    max_change: int,
) -> dict[Pair, int]:
    """对每个候选节点求“以它为链首”的最长链长度。

    按 A 索引倒序处理；处理第 i 行时，数据结构里恰含 i' > i 的全部节点。
    对节点 (i, j, δ) 的转移：在列 j' > j 中查询差值窗口 [δ±max_change] 的
    最大链长。每列一棵线段树，键为该列候选差值（同一列内差值两两不同，
    因为 tA 严格递增）。
    """
    by_row: dict[int, list[tuple[int, int]]] = {}
    col_deltas: dict[int, list[int]] = {}
    for i, j, d in candidates:
        by_row.setdefault(i, []).append((j, d))
        col_deltas.setdefault(j, []).append(d)

    col_coords: dict[int, list[int]] = {j: sorted(ds) for j, ds in col_deltas.items()}
    col_size: dict[int, int] = {}
    col_tree: dict[int, list[int]] = {}
    for j, coords in col_coords.items():
        size = 1
        while size < len(coords):
            size <<= 1
        col_size[j] = size
        col_tree[j] = _st_build(size)
    col_list = sorted(col_coords)  # 升序列号，遍历时跳过 <= j 的列

    best: dict[Pair, int] = {}
    for i in range(n - 1, -1, -1):
        row = by_row.get(i)
        if not row:
            continue
        for j, d in row:
            lo_d = d - max_change
            hi_d = d + max_change
            q = 0
            for jj in col_list:
                if jj <= j:
                    continue
                coords = col_coords[jj]
                lo = bisect_left(coords, lo_d)
                hi = bisect_right(coords, hi_d) - 1
                if lo > hi:
                    continue
                v = _st_query(col_tree[jj], col_size[jj], lo, hi)
                if v > q:
                    q = v
            best[(i, j)] = q + 1
        for j, d in row:
            pos = bisect_left(col_coords[j], d)
            _st_update(col_tree[j], col_size[j], pos, best[(i, j)])
    return best


def _extend_greedy(
    start: Node,
    length: int,
    best: dict[Pair, int],
    candidates: list[Node],
    max_change: int,
) -> list[Node]:
    """从 start 出发续接出长度为 length 的链，逐位取字典序最小的可行后继。"""
    chain = [start]
    cur = start
    need = length - 1
    while need:
        ci, cj, cd = cur
        nxt: Optional[Node] = None
        for node in candidates:
            ni, nj, nd = node
            if ni <= ci or nj <= cj:
                continue
            if best[(ni, nj)] != need:
                continue
            diff = nd - cd
            if diff > max_change or diff < -max_change:
                continue
            if nxt is None or (ni, nj) < (nxt[0], nxt[1]):
                nxt = node
        # need 与 best 的定义保证必存在可行后继
        chain.append(nxt)  # type: ignore[arg-type]
        cur = nxt  # type: ignore[assignment]
        need -= 1
    return chain


def _to_solution(chain: list[Node]) -> DriftSolution:
    return DriftSolution(
        sequence=tuple((i, j) for i, j, _ in chain),
        offsets=tuple(d for _, _, d in chain),
    )


def adjudicate_drift(
    stream_a: list[tuple[int, str]],
    stream_b: list[tuple[int, str]],
    offset_min: int,
    offset_max: int,
    max_change: int,
    min_hits: int,
) -> DriftAdjudication:
    """缓变校时裁决：返回规范首解（及歧义时的第二份见证）。"""
    n = len(stream_a)
    m = len(stream_b)

    # 候选配对：事件码相同且时间差落在允许偏移范围内。
    candidates: list[Node] = []
    for i, (ta, ca) in enumerate(stream_a):
        for j, (tb, cb) in enumerate(stream_b):
            if ca != cb:
                continue
            d = ta - tb
            if offset_min <= d <= offset_max:
                candidates.append((i, j, d))

    offsets_evaluated = len({d for _, _, d in candidates})
    if not candidates:
        return DriftAdjudication(
            "no_solution", 0, min_hits, None, None, None, 0, 0
        )

    best = _longest_suffix_lengths(candidates, n, m, max_change)
    max_len = max(best.values())

    if max_len < min_hits:
        return DriftAdjudication(
            "no_solution", max_len, min_hits, None, None, None,
            offsets_evaluated, len(candidates),
        )

    # —— 规范首解：首对按 (初始偏移, i, j) 最小，之后逐位取最小可行后继 ——
    first = min(
        (node for node in candidates if best[(node[0], node[1])] == max_len),
        key=lambda node: (node[2], node[0], node[1]),
    )
    winner_chain = _extend_greedy(first, max_len, best, candidates, max_change)
    winner = _to_solution(winner_chain)

    # —— 歧义见证：规范序下的第二解 = 与首解最晚分叉的最小方案 ——
    # 分叉位置 t（1 起）越靠后方案越靠前；从 t = max_len 向 1 找首个可分叉点。
    witness: Optional[DriftSolution] = None
    for t in range(max_len, 0, -1):
        need = max_len - t + 1  # 第 t 对起（含）还需的链长
        if t == 1:
            # 首对分叉：初始偏移 / 索引与首解不同的最长链起点
            pool = [
                node
                for node in candidates
                if best[(node[0], node[1])] == max_len and node != winner_chain[0]
            ]
            if not pool:
                continue
            fork = min(pool, key=lambda node: (node[2], node[0], node[1]))
        else:
            pi, pj, pd = winner_chain[t - 2]
            fork = None
            for node in candidates:
                ni, nj, nd = node
                if ni <= pi or nj <= pj:
                    continue
                if best[(ni, nj)] != need:
                    continue
                diff = nd - pd
                if diff > max_change or diff < -max_change:
                    continue
                if (ni, nj) == (winner_chain[t - 1][0], winner_chain[t - 1][1]):
                    continue  # 必须与首解在该位不同
                if fork is None or (ni, nj) < (fork[0], fork[1]):
                    fork = node
            if fork is None:
                continue
        chain = winner_chain[: t - 1] + _extend_greedy(
            fork, need, best, candidates, max_change
        )
        witness = _to_solution(chain)
        break

    return DriftAdjudication(
        "optimal",
        max_len,
        min_hits,
        winner,
        "unique" if witness is None else "ambiguous",
        witness,
        offsets_evaluated,
        len(candidates),
    )
