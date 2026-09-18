"""End-to-end: trial ranking and the persisted lock share the same winning block."""

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
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine)

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    # Mirror-seed hall: aisle at 6, centerline 6.5; col 12 of row 1 pre-held so
    # row 1 free segments are exactly [1,5] and [7,11].
    seeded = TestingSession()
    hall = Hall(name="三号厅", rows=3, cols=12, aisle_cols="6")
    seeded.add(hall)
    seeded.flush()
    st = Showtime(hall_id=hall.id, film_title="对轴迷局", start_at=datetime(2026, 10, 1, 10, 0, 0))
    seeded.add(st)
    seeded.flush()
    seeded.add(SeatHold(showtime_id=st.id, order_code="SB-1004", row=1, start_col=12, end_col=12, party_size=1))
    seeded.commit()
    sid = st.id
    seeded.close()

    with TestClient(app) as c:
        yield c, TestingSession, sid

    app.dependency_overrides.clear()


def test_trial_ranks_right_segment_first(client):
    c, _Session, sid = client
    r = c.get(f"/api/trial", params={"showtime_id": sid, "party_size": 4})
    assert r.status_code == 200
    data = r.json()
    assert data["centerline"] == 6.5

    ranked = [(x["row"], x["start_col"], x["end_col"], x["distance"]) for x in data["candidates"]]
    # Row 1 right segment [7,11] (d=2.5) beats both the row-1 left segment and the
    # wider row 2/3 right runs [7,12] (d=3.0) — not the leftmost [1,4].
    assert ranked[0] == (1, 7, 10, 2.5)
    assert ranked[0][:3] != (1, 1, 4)
    # d=3.0 group is tie-broken by ascending row.
    assert ranked[1] == (2, 8, 11, 3.0)
    assert ranked[2] == (3, 8, 11, 3.0)
    # The d=3.5 group keeps row then start_col order.
    assert ranked[3] == (1, 1, 4, 3.5)

    assert data["selected"] == data["candidates"][0]
    winner = data["selected"]
    assert winner["seg_start_col"] == 7 and winner["seg_end_col"] == 11
    assert winner["score"] == -2.5


def test_lock_persists_exactly_the_trial_winner(client):
    c, Session, sid = client
    trial = c.get("/api/trial", params={"showtime_id": sid, "party_size": 4}).json()["selected"]

    r = c.post("/api/holds", json={"showtime_id": sid, "party_size": 4})
    assert r.status_code == 200
    hold = r.json()
    # Persisted block coordinates are identical to the top trial candidate.
    assert (hold["row"], hold["start_col"], hold["end_col"]) == (
        trial["row"],
        trial["start_col"],
        trial["end_col"],
    )
    assert (hold["row"], hold["start_col"], hold["end_col"]) == (1, 7, 10)

    db = Session()
    try:
        stored = db.scalars(select(SeatHold).where(SeatHold.order_code == hold["order_code"])).one()
        assert (stored.row, stored.start_col, stored.end_col) == (1, 7, 10)
    finally:
        db.close()


def test_preferred_row_pins_trial_selection(client):
    c, _Session, sid = client
    r = c.get(
        "/api/trial",
        params={"showtime_id": sid, "party_size": 4, "preferred_row": 2},
    )
    assert r.status_code == 200
    sel = r.json()["selected"]
    # Pinned to row 2, which is empty: its right run [7,12] wins with block [8,11].
    assert (sel["row"], sel["start_col"], sel["end_col"]) == (2, 8, 11)


def test_no_fit_logs_conflict_and_returns_409_before_persisting(client):
    c, Session, sid = client
    # Largest aisle-bounded run is 6 seats.
    r = c.post("/api/holds", json={"showtime_id": sid, "party_size": 12})
    assert r.status_code == 409

    db = Session()
    try:
        conflicts = db.scalars(select(ConflictLog).where(ConflictLog.showtime_id == sid)).all()
        assert len(conflicts) == 1
        assert conflicts[0].party_size == 12
        # Nothing was locked by the failed request.
        holds = db.scalars(select(SeatHold).where(SeatHold.showtime_id == sid)).all()
        assert len(holds) == 1  # only the seed hold
    finally:
        db.close()


def test_overlap_gate_fires_before_persist_on_race(client, monkeypatch):
    """If the chosen block is already taken at write time (concurrent lock), the
    pre-persist overlap gate rejects it and logs the conflict instead."""
    c, Session, sid = client
    from app.api import router
    from app.services.bond_engine import Candidate

    raced = [
        Candidate(
            row=1,
            start_col=11,
            end_col=12,  # overlaps the seed hold on (1, 12)
            seg_start_col=11,
            seg_end_col=12,
            score=0.0,
            distance=0.0,
        )
    ]
    monkeypatch.setattr(router, "_rank_candidates", lambda *a, **k: raced)

    r = c.post("/api/holds", json={"showtime_id": sid, "party_size": 2})
    assert r.status_code == 409

    db = Session()
    try:
        conflict = db.scalars(select(ConflictLog).where(ConflictLog.showtime_id == sid)).one()
        assert "重叠" in conflict.reason
        holds = db.scalars(select(SeatHold).where(SeatHold.showtime_id == sid)).all()
        assert len(holds) == 1  # the overlapping block was not persisted
    finally:
        db.close()


def test_trial_rejects_party_out_of_range(client):
    c, _Session, sid = client
    assert c.get("/api/trial", params={"showtime_id": sid, "party_size": 0}).status_code == 422
    assert c.get("/api/trial", params={"showtime_id": sid, "party_size": 13}).status_code == 422


def test_trial_unknown_showtime_404(client):
    c, _Session, _sid = client
    assert c.get("/api/trial", params={"showtime_id": 9999, "party_size": 2}).status_code == 404
