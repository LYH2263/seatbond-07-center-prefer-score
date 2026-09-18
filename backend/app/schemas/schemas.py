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


class CandidateOut(BaseModel):
    """试算候选段：恰好 party_size 的连续空座块。"""

    rank: int
    row: int
    start_col: int
    end_col: int
    center: float
    distance: float
    score: float


class PreviewResponse(BaseModel):
    showtime_id: int
    party_size: int
    hall_center: float
    candidates: list[CandidateOut]


class HoldResultOut(BaseModel):
    """锁座响应：落库持座 + 选中块得分与完整候选排序，便于与试算核对。"""

    hold: HoldOut
    hall_center: float
    score: float
    distance: float
    candidates: list[CandidateOut]


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
