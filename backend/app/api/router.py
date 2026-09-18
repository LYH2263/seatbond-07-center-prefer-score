from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.models import ConflictLog, Hall, SeatHold, Showtime
from app.schemas.schemas import (
    CandidateOut,
    ConflictOut,
    HallOut,
    HoldOut,
    HoldRequest,
    HoldResultOut,
    PreviewResponse,
    SeatMapCell,
    SeatMapOut,
    ShowtimeOut,
)
from app.services.bond_engine import (
    Candidate,
    HoldSpan,
    SeatCell,
    conflicts_with,
    hall_center,
    rank_candidates,
    select_block,
)

api_router = APIRouter()


def _aisles(hall: Hall) -> list[int]:
    if not hall.aisle_cols.strip():
        return []
    return [int(x) for x in hall.aisle_cols.split(",") if x.strip()]


def _hall_out(h: Hall) -> HallOut:
    return HallOut(id=h.id, name=h.name, rows=h.rows, cols=h.cols, aisle_cols=_aisles(h))


def _seats_by_row(hall: Hall) -> dict[int, list[SeatCell]]:
    aisles = set(_aisles(hall))
    return {
        r: [SeatCell(row=r, col=c, is_aisle=c in aisles) for c in range(1, hall.cols + 1)]
        for r in range(1, hall.rows + 1)
    }


def _existing_holds(db: Session, showtime_id: int) -> tuple[list[SeatHold], list[HoldSpan]]:
    rows = db.scalars(select(SeatHold).where(SeatHold.showtime_id == showtime_id)).all()
    return rows, [HoldSpan(row=h.row, start_col=h.start_col, end_col=h.end_col) for h in rows]


def _candidate_out(cand: Candidate, rank: int) -> CandidateOut:
    return CandidateOut(
        rank=rank,
        row=cand.row,
        start_col=cand.start_col,
        end_col=cand.end_col,
        center=cand.center,
        distance=cand.distance,
        score=cand.score,
    )


@api_router.get("/health")
def health():
    return {"status": "ok"}


@api_router.get("/halls", response_model=list[HallOut])
def list_halls(db: Session = Depends(get_db)):
    return [_hall_out(h) for h in db.scalars(select(Hall).order_by(Hall.id)).all()]


@api_router.get("/showtimes", response_model=list[ShowtimeOut])
def list_showtimes(db: Session = Depends(get_db)):
    rows = db.scalars(select(Showtime).order_by(Showtime.start_at)).all()
    out = []
    for s in rows:
        hall = db.get(Hall, s.hall_id)
        out.append(
            ShowtimeOut(
                id=s.id,
                hall_id=s.hall_id,
                film_title=s.film_title,
                start_at=s.start_at,
                hall_name=hall.name if hall else None,
            )
        )
    return out


@api_router.get("/seatmap/{showtime_id}", response_model=SeatMapOut)
def seatmap(showtime_id: int, db: Session = Depends(get_db)):
    st = db.get(Showtime, showtime_id)
    if not st:
        raise HTTPException(404, "场次不存在")
    hall = db.get(Hall, st.hall_id)
    assert hall
    aisles = set(_aisles(hall))
    holds = db.scalars(select(SeatHold).where(SeatHold.showtime_id == showtime_id)).all()
    occupied: set[tuple[int, int]] = set()
    for h in holds:
        for c in range(h.start_col, h.end_col + 1):
            occupied.add((h.row, c))
    cells: list[SeatMapCell] = []
    total = hall.rows * hall.cols
    for r in range(1, hall.rows + 1):
        for c in range(1, hall.cols + 1):
            occ = (r, c) in occupied
            cells.append(
                SeatMapCell(
                    row=r,
                    col=c,
                    is_aisle=c in aisles,
                    occupied=occ,
                    heat=1.0 if occ else (0.15 if c in aisles else 0.0),
                )
            )
    return SeatMapOut(
        showtime_id=showtime_id,
        hall_name=hall.name,
        rows=hall.rows,
        cols=hall.cols,
        cells=cells,
    )


@api_router.get("/holds", response_model=list[HoldOut])
def list_holds(db: Session = Depends(get_db)):
    return db.scalars(select(SeatHold).order_by(SeatHold.id.desc())).all()


@api_router.get("/conflicts", response_model=list[ConflictOut])
def list_conflicts(db: Session = Depends(get_db)):
    return db.scalars(select(ConflictLog).order_by(ConflictLog.id.desc())).all()


@api_router.post("/holds/preview", response_model=PreviewResponse)
def preview_holds(body: HoldRequest, db: Session = Depends(get_db)):
    """试算：返回所有满足人数的连续空座候选块（按居中得分排序），不落库。"""
    st = db.get(Showtime, body.showtime_id)
    if not st:
        raise HTTPException(404, "场次不存在")
    hall = db.get(Hall, st.hall_id)
    assert hall
    _, holds = _existing_holds(db, body.showtime_id)
    seats = _seats_by_row(hall)
    if body.preferred_row:
        seats = {body.preferred_row: seats.get(body.preferred_row, [])}
    candidates = rank_candidates(seats, holds, body.party_size, hall.cols)
    return PreviewResponse(
        showtime_id=body.showtime_id,
        party_size=body.party_size,
        hall_center=hall_center(hall.cols),
        candidates=[_candidate_out(c, i + 1) for i, c in enumerate(candidates)],
    )


@api_router.post("/holds", response_model=HoldResultOut)
def create_hold(body: HoldRequest, db: Session = Depends(get_db)):
    st = db.get(Showtime, body.showtime_id)
    if not st:
        raise HTTPException(404, "场次不存在")
    hall = db.get(Hall, st.hall_id)
    assert hall
    _, holds = _existing_holds(db, body.showtime_id)
    seats = _seats_by_row(hall)

    # 居中偏好：跨所有排统一打分排序；指定优先排时只在该排候选中取最高分。
    all_candidates = rank_candidates(seats, holds, body.party_size, hall.cols)
    if body.preferred_row:
        candidates = [c for c in all_candidates if c.row == body.preferred_row]
    else:
        candidates = all_candidates
    block = select_block(candidates)
    if block is None:
        db.add(
            ConflictLog(
                showtime_id=body.showtime_id,
                party_size=body.party_size,
                reason=f"无足够连续空座（人数 {body.party_size}）",
            )
        )
        db.commit()
        raise HTTPException(409, "无足够连续空座")

    # 冲突重叠检测仍在落库前生效。
    hits = conflicts_with(holds, block)
    if hits:
        db.add(
            ConflictLog(
                showtime_id=body.showtime_id,
                party_size=body.party_size,
                reason=f"与既有持座重叠：第{hits[0].row}排 {hits[0].start_col}-{hits[0].end_col}",
            )
        )
        db.commit()
        raise HTTPException(409, "与既有持座冲突")

    code = f"SB-{int(datetime.utcnow().timestamp()) % 100000:05d}"
    hold = SeatHold(
        showtime_id=body.showtime_id,
        order_code=code,
        row=block.row,
        start_col=block.start_col,
        end_col=block.end_col,
        party_size=body.party_size,
    )
    db.add(hold)
    db.commit()
    db.refresh(hold)
    return HoldResultOut(
        hold=HoldOut.model_validate(hold),
        hall_center=hall_center(hall.cols),
        score=candidates[0].score,
        distance=candidates[0].distance,
        candidates=[_candidate_out(c, i + 1) for i, c in enumerate(candidates)],
    )
