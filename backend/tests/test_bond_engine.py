from app.services.bond_engine import (
    Candidate,
    HoldSpan,
    SeatCell,
    conflicts_with,
    contiguous_runs,
    find_bond_across_rows,
    find_contiguous_block,
    free_segments,
    hall_center,
    rank_candidates,
    select_block,
)


def _row(cols, aisles=(), row=1):
    return [SeatCell(row=row, col=c, is_aisle=(c in aisles)) for c in cols]


def test_aisle_breaks_runs():
    cells = _row(range(1, 11), aisles={5, 6})
    assert contiguous_runs(cells) == [(1, 4), (7, 10)]


def test_free_segments_aisle_and_holds():
    # 过道 5,6 断开；持座 2-3 又把左区切成 1 / 4 两段
    cells = _row(range(1, 11), aisles={5, 6})
    holds = [HoldSpan(row=1, start_col=2, end_col=3)]
    assert free_segments(cells, holds, 1) == [(1, 1), (4, 4), (7, 10)]


def test_center_prefers_middle_window_over_leftmost():
    # 单排 9 座无过道：3 人候选，最左是 1-3，但块 4-6 中点 5 正对厅中线
    cells = _row(range(1, 10))
    block = find_contiguous_block(cells, [], 1, 3, cols=9)
    assert block == HoldSpan(row=1, start_col=4, end_col=6)


def test_party_too_large_returns_none():
    cells = _row(range(1, 5), aisles={3})
    assert find_contiguous_block(cells, [], 1, 3) is None


def test_rank_candidates_ordered_by_distance():
    # 12 列、中央过道 6,7，全空第 1 排；2 人候选
    cells = _row(range(1, 13), aisles={6, 7})
    ranked = rank_candidates({1: cells}, [], 2, cols=12)
    # 厅中线 6.5；左右区内缘块 4-5 与 8-9 中点都距中线 2.0，并列最高
    top_two = ranked[:2]
    assert (top_two[0].row, top_two[0].start_col, top_two[0].end_col) == (1, 4, 5)
    assert (top_two[1].row, top_two[1].start_col, top_two[1].end_col) == (1, 8, 9)
    assert top_two[0].score == top_two[1].score == -2.0
    # 同分时起始列更小的排在前（约定次序写死）
    assert top_two[0].start_col < top_two[1].start_col
    # 最左块 1-2 距中线 5.0，排序落在后部；同分的 11-12 因起始列次序排在其后
    far = {(c.start_col, c.end_col): c.score for c in ranked if c.score == -5.0}
    assert far == {(1, 2): -5.0, (11, 12): -5.0}
    assert [c.start_col for c in ranked if c.score == -5.0] == [1, 11]
    # 整体严格按 score 降序
    assert [c.score for c in ranked] == sorted((c.score for c in ranked), reverse=True)


def test_tie_break_row_then_start_col():
    # 三个候选关于中线完全镜像同分：应按 row 升序、再 start_col 升序
    seats = {
        1: _row(range(1, 13), aisles={6, 7}, row=1),
        2: _row(range(1, 13), aisles={6, 7}, row=2),
    }
    ranked = rank_candidates(seats, [], 2, cols=12)
    assert (ranked[0].row, ranked[0].start_col) == (1, 4)
    assert (ranked[1].row, ranked[1].start_col) == (1, 8)
    assert (ranked[2].row, ranked[2].start_col) == (2, 4)
    assert (ranked[3].row, ranked[3].start_col) == (2, 8)


def test_seed_layout_center_vs_leftmost():
    # 与种子三号厅一致的布局：12 列、过道 6,7；第 1 排持座 4-5，2 人锁座
    seats = {r: _row(range(1, 13), aisles={6, 7}, row=r) for r in range(1, 5)}
    holds = [HoldSpan(row=1, start_col=4, end_col=5)]
    ranked = rank_candidates(seats, holds, 2, cols=12)
    # 最左策略会落 1 排 1-2；居中策略最高分是 1 排 8-9（距中线 2.0）
    assert select_block(ranked) == HoldSpan(row=1, start_col=8, end_col=9)
    leftmost = [c for c in ranked if (c.row, c.start_col, c.end_col) == (1, 1, 2)]
    assert leftmost and leftmost[0].score < ranked[0].score
    assert isinstance(ranked[0], Candidate)
    assert hall_center(12) == 6.5


def test_conflict_overlap():
    existing = [HoldSpan(row=2, start_col=4, end_col=6)]
    cand = HoldSpan(row=2, start_col=6, end_col=8)
    assert conflicts_with(existing, cand) == existing


def test_find_across_rows_picks_center_not_first_row_leftmost():
    seats = {
        1: _row(range(1, 5), row=1),  # 只有 1-4，块中点 2.5
        2: [SeatCell(row=2, col=c) for c in range(1, 9)],  # 块 3-5 中点 4 更近厅中线 4.5
    }
    block = find_bond_across_rows(seats, [], 3, cols=8)
    assert block == HoldSpan(row=2, start_col=3, end_col=5)
