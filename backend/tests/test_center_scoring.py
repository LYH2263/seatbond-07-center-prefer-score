from app.services.bond_engine import (
    HoldSpan,
    SeatCell,
    centered_placement,
    choose_centered_block,
    free_segments,
    hall_centerline,
    score_candidates,
    find_contiguous_block,
)


def _row(row, cols, aisles=()):
    return [SeatCell(row=row, col=c, is_aisle=(c in aisles)) for c in range(1, cols + 1)]


def _grid(rows, cols, aisles=()):
    return {r: _row(r, cols, aisles) for r in range(1, rows + 1)}


# --- segment enumeration -------------------------------------------------------


def test_aisle_and_holds_split_segments():
    # aisle at 6; hold punches col 12 out of the right run
    cells = _row(1, 12, aisles={6})
    holds = [HoldSpan(row=1, start_col=12, end_col=12)]
    assert free_segments(cells, holds, 1) == [(1, 5), (7, 11)]


def test_hold_in_middle_of_run_splits_twice():
    cells = _row(1, 8)
    holds = [HoldSpan(row=1, start_col=3, end_col=4)]
    assert free_segments(cells, holds, 1) == [(1, 2), (5, 8)]


# --- scoring order -------------------------------------------------------------


def test_symmetric_seed_right_segment_wins_over_leftmost():
    """Pinned seed scenario: mirror segments, centerline offset between columns."""
    seats = _grid(1, 12, aisles={6})
    holds = [HoldSpan(row=1, start_col=12, end_col=12)]
    ranked = score_candidates(seats, holds, 4, cols=12)

    assert [(c.row, c.start_col, c.end_col) for c in ranked] == [(1, 7, 10), (1, 1, 4)]
    winner, loser = ranked
    assert winner.seg_start_col == 7 and winner.seg_end_col == 11
    assert winner.distance == 2.5 and winner.score == -2.5
    assert loser.seg_start_col == 1 and loser.seg_end_col == 5
    assert loser.distance == 3.5 and loser.score == -3.5

    # The legacy leftmost strategy reaches the opposite conclusion on the same state.
    assert find_contiguous_block(seats[1], holds, 1, 4) == HoldSpan(1, 1, 4)
    # The center strategy locks the winner's exact block.
    assert choose_centered_block(seats, holds, 4, cols=12) == HoldSpan(1, 7, 10)


def test_tie_break_row_then_start_col_is_stable():
    # Two rows share an identical segment -> equal distance -> smaller row first.
    seats = _grid(2, 12)
    holds = [
        HoldSpan(row=1, start_col=7, end_col=12),
        HoldSpan(row=2, start_col=7, end_col=12),
    ]
    ranked = score_candidates(seats, holds, 2, cols=12)
    assert [c.row for c in ranked] == [1, 2]
    assert ranked[0].distance == ranked[1].distance

    # Same row, two segments mirrored about the centerline -> smaller start_col first.
    seats2 = _grid(1, 12, aisles={6})
    holds2 = [HoldSpan(row=1, start_col=7, end_col=7)]  # right run becomes [8,12]
    ranked2 = score_candidates(seats2, holds2, 2, cols=12)
    assert [(c.start_col, c.end_col, c.distance) for c in ranked2] == [
        (2, 3, 3.5),
        (9, 10, 3.5),
    ]


def test_full_row_block_is_centered_not_leftmost():
    seats = _grid(1, 12)
    ranked = score_candidates(seats, [], 4, cols=12)
    assert len(ranked) == 1
    assert ranked[0].distance == 0.0
    assert (ranked[0].start_col, ranked[0].end_col) == (5, 8)
    assert hall_centerline(12) == 6.5


# --- placement within a segment ------------------------------------------------


def test_centered_placement_slack_split():
    assert centered_placement(1, 5, 4) == (1, 4)  # slack 1 -> floor goes left
    assert centered_placement(1, 5, 3) == (2, 4)  # slack 2 -> exact center
    assert centered_placement(1, 6, 2) == (3, 4)  # slack 4
    assert centered_placement(7, 12, 4) == (8, 11)  # right run of seed hall row 2


# --- preferred row -------------------------------------------------------------


def test_preferred_row_pins_when_it_fits_falls_back_otherwise():
    # row 1 only has an edge segment; row 2 offers a better centered one.
    seats = _grid(2, 12, aisles={6})
    holds = [
        HoldSpan(row=1, start_col=7, end_col=12),  # row 1: [1,5] only
    ]
    assert choose_centered_block(seats, holds, 4, cols=12, preferred_row=1) == HoldSpan(1, 1, 4)
    # preferred row with no fit -> global best (row 2 centered block)
    assert choose_centered_block(seats, holds, 4, cols=12, preferred_row=1) is not None
    seats_full = _grid(2, 12, aisles={6})
    holds_full = [
        HoldSpan(row=1, start_col=1, end_col=12),
    ]
    assert choose_centered_block(seats_full, holds_full, 4, cols=12, preferred_row=1) == HoldSpan(
        2, 8, 11
    )


def test_party_too_large_scores_nothing():
    seats = _grid(1, 5, aisles={3})
    assert score_candidates(seats, [], 3, cols=5) == []
    assert choose_centered_block(seats, [], 3, cols=5) is None
