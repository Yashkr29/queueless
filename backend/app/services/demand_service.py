"""Demand forecasting: builds the lag features from real arrivals, asks the ML model, falls back to a
4-week historical average (labelled) when no model exists, and stores forecasts so they can be scored later."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..ml import predictor
from ..ml.calendar_utils import is_default_holiday
from ..ml.features import DEMAND_BIN_MINUTES, DEMAND_HORIZONS, demand_feature_row
from ..models import DemandForecast, QueueToken, Service, SpecialEvent, utcnow
from . import settings_service as cfg

_BASE = datetime(2000, 1, 3)       # an arbitrary Monday midnight; only differences matter (48 bins per day)


def _bin_of(local_naive: datetime) -> int:
    return int((local_naive - _BASE).total_seconds() // (DEMAND_BIN_MINUTES * 60))


def _counts(db: Session, loc, service_id: int, now_local: datetime) -> dict[int, int]:
    tz = cfg.local_tz(loc)
    since = (now_local - timedelta(days=29)).astimezone(timezone.utc)
    rows = db.scalars(select(QueueToken.created_at).where(
        QueueToken.service_id == service_id, QueueToken.created_at >= since)).all()
    counts: dict[int, int] = {}
    for ts in rows:
        b = _bin_of(ts.astimezone(tz).replace(tzinfo=None))
        counts[b] = counts.get(b, 0) + 1
    return counts


def forecast_service(db: Session, service: Service, persist: bool = True) -> dict:
    loc = cfg.get_location(db, service.location_id)
    now_local = cfg.local_now(loc)
    naive = now_local.replace(tzinfo=None)
    counts = _counts(db, loc, service.service_id, now_local)
    get = lambda i: counts.get(i, 0)
    idx = _bin_of(naive)
    d = now_local.date()
    ev = db.get(SpecialEvent, (d, loc.location_id))
    holiday = int(is_default_holiday(d) or bool(ev and ev.is_holiday))
    special = int(bool(ev and not ev.is_holiday))
    interval_start = now_local.replace(minute=(now_local.minute // 30) * 30, second=0, microsecond=0)
    out = []
    for h in DEMAND_HORIZONS:
        f = demand_feature_row(get_count=get, bin_index=idx, horizon_bins=h // DEMAND_BIN_MINUTES,
                               hour_of_day=interval_start.hour + interval_start.minute / 60, day_of_week=now_local.weekday(),
                               is_holiday=holiday, special_event=special, service_type=service.service_id)
        ml = predictor.predict_demand(h, f)
        if ml:
            value, version, method = ml[0], ml[1], "ml"
        else:
            value, version, method = f["historical_demand"], "historical-mean-v1", "fallback"
        value = round(value, 1)
        out.append({"horizon_minutes": h, "predicted_arrivals": value, "method": method, "model_version": version,
                    "interval_start": interval_start, "interval_end": interval_start + timedelta(minutes=h)})
        if persist:
            exists = db.scalar(select(DemandForecast.forecast_id).where(
                DemandForecast.service_id == service.service_id, DemandForecast.interval_start == interval_start.astimezone(timezone.utc),
                DemandForecast.horizon_minutes == h, DemandForecast.model_version == version))
            if not exists:
                db.add(DemandForecast(service_id=service.service_id, interval_start=interval_start, horizon_minutes=h,
                                      predicted_arrivals=value, method=method, model_version=version))
    # expected peak hours: historical hourly profile over the last 4 weeks (same weekday)
    hourly: dict[int, list[int]] = {}
    for b, c in counts.items():
        if (b // 48) % 7 == naive.weekday():      # _BASE is a Monday, so (day index % 7) is the weekday
            hourly.setdefault((b % 48) // 2, []).append(c)
    profile = sorted(((h, sum(v) / 4) for h, v in hourly.items()), key=lambda kv: -kv[1])[:3]
    return {"service_id": service.service_id, "generated_at": utcnow(), "forecasts": out,
            "expected_peak_hours": [{"hour": h, "avg_arrivals": round(v, 1)} for h, v in sorted(profile)]}


def backfill_actuals(db: Session) -> int:
    """Fill actual_arrivals for forecasts whose interval has passed (feeds the predicted-vs-actual chart)."""
    now = utcnow()
    pending = db.scalars(select(DemandForecast).where(DemandForecast.actual_arrivals.is_(None)).limit(500)).all()
    n = 0
    for f in pending:
        end = f.interval_start + timedelta(minutes=f.horizon_minutes)
        if end > now:
            continue
        f.actual_arrivals = len(db.scalars(select(QueueToken.token_id).where(
            QueueToken.service_id == f.service_id, QueueToken.created_at >= f.interval_start, QueueToken.created_at < end)).all())
        n += 1
    if n:
        db.flush()
    return n
