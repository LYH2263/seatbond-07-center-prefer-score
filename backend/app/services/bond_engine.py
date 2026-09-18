"""Contiguous seat bonding with center preference.

过道列（以及既有持座 punched holes）把每排切成若干连续空段；在每个能容纳
party_size 的空段内，枚举恰好 party_size 的候选块（滑动窗口），按候选块
中点到厅中线的距离打分（越近越高），跨排统一排序后只落一块。

排序键（同分次序稳定，已在 README 与测例中写死）：
    1. 得分 score 降序（块中点离厅中线越近越高）
    2. 排号 row 升序（更小排号优先）
    3. 起始列 start_col 升序（同排更靠左优先）

落库的 HoldSpan 与排序第一的候选块坐标完全一致。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SeatCell:
    row: int
    col: int
    is_aisle: bool = False


@dataclass(frozen=True)
class HoldSpan:
    row: int
    start_col: int
    end_col: int  # inclusive


@dataclass(frozen=True)
class Candidate:
    """一个恰好 party_size 的连续空座候选块。"""

    row: int
    start_col: int
    end_col: int  # inclusive
    center: float  # 候选块中点（座位列坐标）
    distance: float  # 中点到厅中线的距离
    score: float  # 居中得分：越近越高（= -distance）


def hall_center(cols: int) -> float:
    """厅中线：座位列 1..cols 的几何中心。

    奇数列厅穿过中央座中轴线；偶数列厅穿过两个中央座之间的缝。
    过道列同样计入列坐标（厅中线是厅的几何中线，不是某个座位）。
    """
    return (1 + cols) / 2.0


def segment_score(midpoint: float, center_line: float) -> float:
    """块中点到厅中线距离越近得分越高；以 -distance 作为得分，比较稳定。"""
    return -abs(midpoint - center_line)


def contiguous_runs(row_cells: list[SeatCell]) -> list[tuple[int, int]]:
    """Return inclusive (start_col, end_col) runs of non-aisle seats, broken by aisles."""
    runs: list[tuple[int, int]] = []
    start: int | None = None
    prev_col: int | None = None
    for cell in sorted(row_cells, key=lambda c: c.col):
        if cell.is_aisle:
            if start is not None and prev_col is not None:
                runs.append((start, prev_col))
            start = None
            prev_col = None
            continue
        if start is None:
            start = cell.col
        elif prev_col is not None and cell.col != prev_col + 1:
            runs.append((start, prev_col))
            start = cell.col
        prev_col = cell.col
    if start is not None and prev_col is not None:
        runs.append((start, prev_col))
    return runs


def occupied_cols(holds: list[HoldSpan], row: int) -> set[int]:
    cols: set[int] = set()
    for h in holds:
        if h.row != row:
            continue
        for c in range(h.start_col, h.end_col + 1):
            cols.add(c)
    return cols


def free_segments(
    row_cells: list[SeatCell],
    holds: list[HoldSpan],
    row: int,
) -> list[tuple[int, int]]:
    """过道与既有持座共同切出的连续空段（含端点，闭区间）。"""
    taken = occupied_cols(holds, row)
    segments: list[tuple[int, int]] = []
    for start, end in contiguous_runs(row_cells):
        seg_start: int | None = None
        prev: int | None = None
        for col in range(start, end + 1):
            if col in taken:
                if seg_start is not None and prev is not None:
                    segments.append((seg_start, prev))
                seg_start = None
                prev = None
                continue
            if seg_start is None:
                seg_start = col
            prev = col
        if seg_start is not None and prev is not None:
            segments.append((seg_start, prev))
    return segments


def rank_candidates(
    seats_by_row: dict[int, list[SeatCell]],
    holds: list[HoldSpan],
    party_size: int,
    cols: int,
) -> list[Candidate]:
    """枚举所有恰好 party_size 的连续空座块并按居中偏好排序。

    过道打断后的各段分别枚举、分别计分；持座 punched holes 同样断开。
    排序：score 降序、row 升序、start_col 升序。
    """
    if party_size <= 0:
        return []
    center_line = hall_center(cols)
    candidates: list[Candidate] = []
    for row in sorted(seats_by_row.keys()):
        for seg_start, seg_end in free_segments(seats_by_row[row], holds, row):
            for start in range(seg_start, seg_end - party_size + 2):
                end = start + party_size - 1
                midpoint = (start + end) / 2.0
                distance = abs(midpoint - center_line)
                candidates.append(
                    Candidate(
                        row=row,
                        start_col=start,
                        end_col=end,
                        center=midpoint,
                        distance=distance,
                        score=segment_score(midpoint, center_line),
                    )
                )
    candidates.sort(key=lambda c: (-c.score, c.row, c.start_col))
    return candidates


def select_block(candidates: list[Candidate]) -> HoldSpan | None:
    """取已排序候选的第一块；落库坐标与该候选块完全一致。"""
    if not candidates:
        return None
    top = candidates[0]
    return HoldSpan(row=top.row, start_col=top.start_col, end_col=top.end_col)


def find_contiguous_block(
    row_cells: list[SeatCell],
    holds: list[HoldSpan],
    row: int,
    party_size: int,
    cols: int | None = None,
) -> HoldSpan | None:
    """单排居中选座：该排得分最高的候选块。

    cols 为 None 时按该排实际座位列跨度推导厅中线（测试便捷入口）。
    """
    if party_size <= 0:
        return None
    if cols is None:
        present = [c.col for c in row_cells if not c.is_aisle]
        if not present:
            return None
        cols = max(present)
    return select_block(rank_candidates({row: row_cells}, holds, party_size, cols))


def find_bond_across_rows(
    seats_by_row: dict[int, list[SeatCell]],
    holds: list[HoldSpan],
    party_size: int,
    cols: int | None = None,
) -> HoldSpan | None:
    """跨排选座：全局得分最高的候选块。"""
    if party_size <= 0:
        return None
    if cols is None:
        max_col = 0
        for cells in seats_by_row.values():
            for c in cells:
                if not c.is_aisle and c.col > max_col:
                    max_col = c.col
        cols = max_col
    return select_block(rank_candidates(seats_by_row, holds, party_size, cols))


def conflicts_with(existing: list[HoldSpan], candidate: HoldSpan) -> list[HoldSpan]:
    hits: list[HoldSpan] = []
    for h in existing:
        if h.row != candidate.row:
            continue
        if h.end_col < candidate.start_col or candidate.end_col < h.start_col:
            continue
        hits.append(h)
    return hits
