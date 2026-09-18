from datetime import datetime
from pydantic import BaseModel, Field


class HallOut(BaseModel):
    id: int
    name: str
    rows: int
    cols: int
    aisle_cols: list[int]
    model_config = {"from_attributes": True}


class ShowtimeOut(BaseModel):
    id: int
    hall_id: int
    film_title: str
    start_at: datetime
    hall_name: str | None = None
    model_config = {"from_attributes": True}


class HoldOut(BaseModel):
    id: int
    showtime_id: int
    order_code: str
    row: int
    start_col: int
    end_col: int
    party_size: int
    status: str
    model_config = {"from_attributes": True}


class HoldRequest(BaseModel):
    showtime_id: int
    party_size: int = Field(ge=1, le=12)
    preferred_row: int | None = None


class ConflictOut(BaseModel):
    id: int
    showtime_id: int
    party_size: int
    reason: str
    created_at: datetime
    model_config = {"from_attributes": True}


class SeatMapCell(BaseModel):
    row: int
    col: int
    is_aisle: bool
    occupied: bool
    heat: float


class SeatMapOut(BaseModel):
    showtime_id: int
    hall_name: str
    rows: int
    cols: int
    cells: list[SeatMapCell]


class TrialCandidateOut(BaseModel):
    row: int
    start_col: int  # block coordinates that would actually be locked
    end_col: int
    seg_start_col: int  # containing free segment (aisle/hold-bounded)
    seg_end_col: int
    score: float  # -distance of the segment midpoint to the hall centerline
    distance: float


class TrialOut(BaseModel):
    showtime_id: int
    party_size: int
    centerline: float
    candidates: list[TrialCandidateOut]  # best first; tie: row asc, start_col asc
    selected: TrialCandidateOut | None = None
