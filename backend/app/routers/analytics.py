from datetime import date

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import User
from ..security import staff_user
from ..services import analytics as an
from ..services import settings_service as cfg

router = APIRouter(prefix="/analytics", tags=["analytics"])
Source = Query(None, pattern="^(all|live|demo)$", description="Demo rows are flagged; 'live' excludes them")


@router.get("/overview")
def overview(source: str | None = Source, db: Session = Depends(get_db), _: User = Depends(staff_user)):
    res = an.overview(db, source)
    db.commit()
    return res


@router.get("/traffic")
def traffic(granularity: str = Query("hour", pattern="^(hour|day|week|month)$"), days: int = Query(14, ge=1, le=366),
            source: str | None = Source, db: Session = Depends(get_db), _: User = Depends(staff_user)):
    return an.traffic(db, granularity, days, source)


@router.get("/waiting-time")
def waiting_time(days: int = Query(14, ge=1, le=366), source: str | None = Source, db: Session = Depends(get_db), _: User = Depends(staff_user)):
    return an.waiting_time(db, days, source)


@router.get("/counter-performance")
def counter_performance(days: int = Query(14, ge=1, le=366), source: str | None = Source, db: Session = Depends(get_db), _: User = Depends(staff_user)):
    return an.counter_performance(db, days, source)


@router.get("/predicted-vs-actual-arrivals")
def pva(day: date | None = None, db: Session = Depends(get_db), _: User = Depends(staff_user)):
    res = an.predicted_vs_actual_arrivals(db, day)
    db.commit()
    return res


@router.get("/ml-monitoring")
def ml_monitoring(days: int = Query(30, ge=1, le=180), source: str | None = Source, db: Session = Depends(get_db), _: User = Depends(staff_user)):
    res = an.ml_monitoring(db, days, source)
    db.commit()
    return res


@router.get("/reports/daily")
def daily_report(day: date | None = None, format: str = Query("json", pattern="^(json|csv|pdf)$"), source: str | None = Source,
                 db: Session = Depends(get_db), _: User = Depends(staff_user)):
    d = day or cfg.local_today(cfg.get_location(db))
    rep = an.daily_report(db, d, source)
    if format == "csv":
        return Response(an.report_csv(rep), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="queueless-report-{d}.csv"'})
    if format == "pdf":
        return Response(an.report_pdf(rep), media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="queueless-report-{d}.pdf"'})
    return rep
