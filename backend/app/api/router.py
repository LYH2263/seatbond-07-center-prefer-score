from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.models import ConflictLog, Hall, SeatHold, Showtime
from app.schemas.schemas import (
    ConflictOut,
    HallOut,
    HoldOut,
    HoldRequest,
    SeatMapCell,
    SeatMapOut,
    ShowtimeOut,
    TrialCandidateOut,
    TrialOut,
)
from app.services.bond_engine import (
    Candidate,
    HoldSpan,
    SeatCell,
    conflicts_with,
    hall_centerline,
    score_candidates,
)

api_router = APIRouter()


def _aisles(hall: Hall) -> list[int]:
    if not hall.aisle_cols.strip():
        return []
    return [int(x) for x in hall.aisle_cols.split(",") if x.strip()]


def _hall_out(h: Hall) -> HallOut:
    return HallOut(id=h.id, name=h.name, rows=h.rows, cols=h.cols, aisle_cols=_aisles(h))


def _load_layout(
    db: Session, showtime_id: int
) -> tuple[Showtime, Hall, list[HoldSpan], dict[int, list[SeatCell]]]:
    st = db.get(Showtime, showtime_id)
    if not st:
        raise HTTPException(404, "场次不存在")
    hall = db.get(Hall, st.hall_id)
    assert hall
    aisles = set(_aisles(hall))
    existing = db.scalars(select(SeatHold).where(SeatHold.showtime_id == showtime_id)).all()
    holds = [HoldSpan(row=h.row, start_col=h.start_col, end_col=h.end_col) for h in existing]
    seats_by_row: dict[int, list[SeatCell]] = {
        r: [SeatCell(row=r, col=c, is_aisle=c in aisles) for c in range(1, hall.cols + 1)]
        for r in range(1, hall.rows + 1)
    }
    return st, hall, holds, seats_by_row


def _rank_candidates(
    hall: Hall,
    holds: list[HoldSpan],
    seats_by_row: dict[int, list[SeatCell]],
    party_size: int,
    preferred_row: int | None,
) -> list[Candidate]:
    """Center-preference ranking; a preferred row pins selection to that row when it fits."""
    if preferred_row is not None:
        pinned = score_candidates(seats_by_row, holds, party_size, hall.cols, restrict_row=preferred_row)
        if pinned:
            return pinned
    return score_candidates(seats_by_row, holds, party_size, hall.cols)


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


@api_router.get("/trial", response_model=TrialOut)
def trial(
    showtime_id: int,
    party_size: int,
    preferred_row: int | None = None,
    db: Session = Depends(get_db),
):
    """Dry-run: return all fitting candidate segments ranked by center preference.

    Nothing is persisted. ``selected`` is the single block a subsequent lock would
    take (under the same holds); POST /holds re-ranks and re-checks overlap at
    write time.
    """
    if party_size < 1 or party_size > 12:
        raise HTTPException(422, "人数需在 1-12 之间")
    _st, hall, holds, seats_by_row = _load_layout(db, showtime_id)
    ranked = _rank_candidates(hall, holds, seats_by_row, party_size, preferred_row)
    payload = [
        TrialCandidateOut(
            row=c.row,
            start_col=c.start_col,
            end_col=c.end_col,
            seg_start_col=c.seg_start_col,
            seg_end_col=c.seg_end_col,
            score=c.score,
            distance=c.distance,
        )
        for c in ranked
    ]
    return TrialOut(
        showtime_id=showtime_id,
        party_size=party_size,
        centerline=hall_centerline(hall.cols),
        candidates=payload,
        selected=payload[0] if payload else None,
    )


@api_router.post("/holds", response_model=HoldOut)
def create_hold(body: HoldRequest, db: Session = Depends(get_db)):
    _st, hall, holds, seats_by_row = _load_layout(db, body.showtime_id)

    ranked = _rank_candidates(hall, holds, seats_by_row, body.party_size, body.preferred_row)
    if not ranked:
        db.add(
            ConflictLog(
                showtime_id=body.showtime_id,
                party_size=body.party_size,
                reason=f"无足够连续空座（人数 {body.party_size}）",
            )
        )
        db.commit()
        raise HTTPException(409, "无足够连续空座")

    block = ranked[0].span

    # Overlap detection stays the final gate before persisting.
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
    return hold
