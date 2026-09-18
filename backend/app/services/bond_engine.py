"""Contiguous seat bonding with center-preference scoring.

Selection rule (居中偏好):
- Aisles split a row into runs; existing holds punch free segments out of runs.
- Every free segment that fits the party yields one candidate. It is scored by the
  distance of the SEGMENT midpoint to the hall centerline ``(cols + 1) / 2`` —
  closer means a higher score (``score = -distance``).
- The block actually locked is placed at the segment's center (extra seats split
  floor-left / ceil-right, i.e. the block sits one half-seat left of center when
  the slack is odd); the persisted coordinates are the winning candidate's block.
- Ties use a fixed order: smaller row first, then smaller start_col.

The legacy leftmost helpers below are kept as the explicit baseline the center
strategy is compared against (and by the test suite).
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
    """A party-sized block placed centrally inside a scored free segment."""

    row: int
    start_col: int  # block actually locked (centered inside the segment)
    end_col: int  # inclusive
    seg_start_col: int  # containing free segment bounds
    seg_end_col: int
    score: float  # -distance of the SEGMENT midpoint to centerline; larger is better
    distance: float

    @property
    def span(self) -> HoldSpan:
        return HoldSpan(row=self.row, start_col=self.start_col, end_col=self.end_col)


def hall_centerline(cols: int) -> float:
    """Midpoint between seat columns 1..cols (cols odd -> seat, even -> half-seat)."""
    return (cols + 1) / 2


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
    """Inclusive (start_col, end_col) empty segments: runs split by aisles AND holds."""
    taken = occupied_cols(holds, row)
    segments: list[tuple[int, int]] = []
    for run_start, run_end in contiguous_runs(row_cells):
        seg_start: int | None = None
        prev: int | None = None
        for col in range(run_start, run_end + 1):
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


def centered_placement(seg_start: int, seg_end: int, party_size: int) -> tuple[int, int]:
    """Place a party_size block centrally inside a segment; floor slack goes left."""
    offset = (seg_end - seg_start + 1 - party_size) // 2
    start = seg_start + offset
    return start, start + party_size - 1


def score_candidates(
    seats_by_row: dict[int, list[SeatCell]],
    holds: list[HoldSpan],
    party_size: int,
    cols: int,
    restrict_row: int | None = None,
) -> list[Candidate]:
    """Score every fitting free segment, best first.

    Order: score descending (closer to hall centerline first), then row ascending,
    then start_col ascending — the tie-break is part of the contract and is pinned
    by tests.
    """
    if party_size <= 0:
        return []
    centerline = hall_centerline(cols)
    rows = [restrict_row] if restrict_row is not None else sorted(seats_by_row.keys())
    candidates: list[Candidate] = []
    for row in rows:
        for seg_start, seg_end in free_segments(seats_by_row.get(row, []), holds, row):
            if seg_end - seg_start + 1 < party_size:
                continue
            seg_midpoint = (seg_start + seg_end) / 2
            distance = abs(seg_midpoint - centerline)
            start, end = centered_placement(seg_start, seg_end, party_size)
            candidates.append(
                Candidate(
                    row=row,
                    start_col=start,
                    end_col=end,
                    seg_start_col=seg_start,
                    seg_end_col=seg_end,
                    score=-distance,
                    distance=distance,
                )
            )
    candidates.sort(key=lambda c: (-c.score, c.row, c.start_col))
    return candidates


def choose_centered_block(
    seats_by_row: dict[int, list[SeatCell]],
    holds: list[HoldSpan],
    party_size: int,
    cols: int,
    preferred_row: int | None = None,
) -> HoldSpan | None:
    """Pick the best-scoring block; preferred row wins when it has any fit."""
    if preferred_row is not None:
        pinned = score_candidates(seats_by_row, holds, party_size, cols, restrict_row=preferred_row)
        if pinned:
            return pinned[0].span
    ranked = score_candidates(seats_by_row, holds, party_size, cols)
    return ranked[0].span if ranked else None


# --- Legacy leftmost strategy, retained as the comparison baseline -------------


def find_contiguous_block(
    row_cells: list[SeatCell],
    holds: list[HoldSpan],
    row: int,
    party_size: int,
) -> HoldSpan | None:
    """Find leftmost contiguous empty seats of party_size in a row."""
    if party_size <= 0:
        return None
    for seg_start, seg_end in free_segments(row_cells, holds, row):
        if seg_end - seg_start + 1 >= party_size:
            return HoldSpan(row=row, start_col=seg_start, end_col=seg_start + party_size - 1)
    return None


def find_bond_across_rows(
    seats_by_row: dict[int, list[SeatCell]],
    holds: list[HoldSpan],
    party_size: int,
) -> HoldSpan | None:
    for row in sorted(seats_by_row.keys()):
        block = find_contiguous_block(seats_by_row[row], holds, row, party_size)
        if block is not None:
            return block
    return None


def conflicts_with(existing: list[HoldSpan], candidate: HoldSpan) -> list[HoldSpan]:
    hits: list[HoldSpan] = []
    for h in existing:
        if h.row != candidate.row:
            continue
        if h.end_col < candidate.start_col or candidate.end_col < h.start_col:
            continue
        hits.append(h)
    return hits
