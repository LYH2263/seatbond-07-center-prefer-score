"""试算 / 锁座 API：试算排序、居中落库坐标、冲突落日志。"""

from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models.models import ConflictLog, Hall, SeatHold, Showtime


@pytest.fixture()
def client():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def _override():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override

    db = TestSession()
    # 与种子三号厅完全一致：12 列、中央过道 6,7；第 1 排持座 4-5
    hall = Hall(name="三号厅（居中试算）", rows=4, cols=12, aisle_cols="6,7")
    db.add(hall)
    db.flush()
    st = Showtime(hall_id=hall.id, film_title="镜厅回声", start_at=datetime(2026, 9, 18, 20, 0))
    db.add(st)
    db.flush()
    db.add(
        SeatHold(
            showtime_id=st.id,
            order_code="SB-2001",
            row=1,
            start_col=4,
            end_col=5,
            party_size=2,
        )
    )
    db.commit()
    sid = st.id
    db.close()

    with TestClient(app) as c:
        yield c, TestSession, sid

    app.dependency_overrides.clear()


def test_preview_ranks_center_block_first(client):
    c, _session, sid = client
    r = c.post("/api/holds/preview", json={"showtime_id": sid, "party_size": 2})
    assert r.status_code == 200
    data = r.json()
    assert data["showtime_id"] == sid
    assert data["hall_center"] == 6.5

    cands = data["candidates"]
    # 居中策略第一名：第 1 排 8-9（中点 8.5，距中线 2.0）；最左策略会选 1-2
    first = cands[0]
    assert (first["rank"], first["row"], first["start_col"], first["end_col"]) == (1, 1, 8, 9)
    assert first["distance"] == 2.0
    assert first["score"] == -2.0

    # 试算严格按得分降序；同分按排号、起始列稳定排列
    scores = [x["score"] for x in cands]
    assert scores == sorted(scores, reverse=True)

    leftmost = next(x for x in cands if (x["row"], x["start_col"], x["end_col"]) == (1, 1, 2))
    assert leftmost["score"] < first["score"]
    assert leftmost["rank"] > first["rank"]


def test_lock_persists_top_preview_candidate(client):
    c, TestSession, sid = client
    preview = c.post("/api/holds/preview", json={"showtime_id": sid, "party_size": 2}).json()
    top = preview["candidates"][0]

    r = c.post("/api/holds", json={"showtime_id": sid, "party_size": 2})
    assert r.status_code == 200
    data = r.json()
    hold = data["hold"]

    # 锁座响应自带得分与候选排序，与试算一致
    assert data["score"] == top["score"]
    assert [
        (x["row"], x["start_col"], x["end_col"]) for x in data["candidates"]
    ] == [(x["row"], x["start_col"], x["end_col"]) for x in preview["candidates"]]

    # 持座坐标必须与得分最高段一致（而不是旧最左策略的 1-2）
    assert (hold["row"], hold["start_col"], hold["end_col"]) == (
        top["row"],
        top["start_col"],
        top["end_col"],
    ) == (1, 8, 9)

    db = TestSession()
    persisted = db.scalars(
        select(SeatHold).where(SeatHold.showtime_id == sid, SeatHold.order_code != "SB-2001")
    ).one()
    assert (persisted.row, persisted.start_col, persisted.end_col) == (1, 8, 9)
    db.close()


def test_no_capacity_returns_409_and_logs_conflict(client):
    c, TestSession, sid = client
    r = c.post("/api/holds", json={"showtime_id": sid, "party_size": 12})
    assert r.status_code == 409

    db = TestSession()
    logs = db.scalars(select(ConflictLog).where(ConflictLog.showtime_id == sid)).all()
    assert len(logs) == 1
    assert "12" in logs[0].reason
    # 未写入持座
    assert len(db.scalars(select(SeatHold).where(SeatHold.showtime_id == sid)).all()) == 1
    db.close()


def test_preview_is_read_only(client):
    c, TestSession, sid = client
    r = c.post("/api/holds/preview", json={"showtime_id": sid, "party_size": 2})
    assert r.status_code == 200
    db = TestSession()
    assert len(db.scalars(select(SeatHold).where(SeatHold.showtime_id == sid)).all()) == 1
    db.close()


def test_aisle_segments_scored_separately(client):
    # 3 人：左区 1-3 是唯一能容纳 3 人的段（右区 8-12 也有），各自独立计分
    c, _session, sid = client
    r = c.post("/api/holds/preview", json={"showtime_id": sid, "party_size": 3})
    cands = r.json()["candidates"]
    # 右区内缘块 8-10（中点 9，距中线 2.5）居中胜出；不会跨过过道 6,7
    first = cands[0]
    assert (first["row"], first["start_col"], first["end_col"]) == (1, 8, 10)
    for x in cands:
        # 任何候选块都不得跨过中央过道 6,7
        assert x["end_col"] < 6 or x["start_col"] > 7
