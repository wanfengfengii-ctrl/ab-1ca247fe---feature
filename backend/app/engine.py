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
"""

from __future__ import annotations

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
