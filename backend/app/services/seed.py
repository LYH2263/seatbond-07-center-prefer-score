from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.models import ConflictLog, Hall, SeatHold, Showtime


def seed_if_empty(db: Session) -> None:
    if db.scalar(select(Hall.id).limit(1)):
        return
    h1 = Hall(name="一号厅", rows=8, cols=12, aisle_cols="5,6")
    h2 = Hall(name="二号厅", rows=6, cols=10, aisle_cols="4,5")
    # 居中试算厅：cols=12、中央过道 6,7，左右两区（1-5 / 8-12）关于厅中线 6.5 镜像。
    h3 = Hall(name="三号厅（居中试算）", rows=4, cols=12, aisle_cols="6,7")
    db.add_all([h1, h2, h3])
    db.flush()
    now = datetime.utcnow().replace(minute=0, second=0, microsecond=0)
    s1 = Showtime(hall_id=h1.id, film_title="星际旅人", start_at=now + timedelta(hours=2))
    s2 = Showtime(hall_id=h1.id, film_title="雾都夜曲", start_at=now + timedelta(hours=5))
    s3 = Showtime(hall_id=h2.id, film_title="山海经异", start_at=now + timedelta(hours=3))
    s4 = Showtime(hall_id=h3.id, film_title="镜厅回声", start_at=now + timedelta(hours=4))
    db.add_all([s1, s2, s3, s4])
    db.flush()
    db.add_all(
        [
            SeatHold(showtime_id=s1.id, order_code="SB-1001", row=3, start_col=2, end_col=4, party_size=3),
            SeatHold(showtime_id=s1.id, order_code="SB-1002", row=5, start_col=7, end_col=9, party_size=3),
            SeatHold(showtime_id=s3.id, order_code="SB-1003", row=2, start_col=1, end_col=2, party_size=2),
            # 三号厅第1排：占掉靠左中的 4-5。2 人试算时左区只剩 1-3（最左策略落 1-2），
            # 右区 8-12 完整，块 8-9 中点 8.5 距厅中线 6.5 仅 2.0，为全局最高分 → 居中策略落 8-9。
            SeatHold(showtime_id=s4.id, order_code="SB-2001", row=1, start_col=4, end_col=5, party_size=2),
        ]
    )
    db.add(ConflictLog(showtime_id=s1.id, party_size=4, reason="与既有持座重叠：第3排 2-4"))
    db.commit()
