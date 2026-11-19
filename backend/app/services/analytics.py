"""Operational analytics. Aggregation is done in Python over small, indexed result sets so the same code runs on
Supabase Postgres and the local SQLite fallback. Move to SQL GROUP BY / materialised views if volumes grow."""
from __future__ import annotations

import csv
import io
import math
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..engine import queue_engine as qe
from ..ml import predictor
from ..models import (
    WAITING_STATUSES, Counter, DemandForecast, Prediction, QueueEvent, QueueToken, Service, ServiceRecord, TokenStatus, utcnow,
)
from . import demand_service
from . import settings_service as cfg

OPERATING_MINUTES = 8 * 60


def source_filter(source: str | None):
    """Demo rows are flagged; analytics can include them (demo mode) or show only real operations."""
    src = source or ("all" if get_settings().demo_mode else "live")
    if src == "live":
        return QueueToken.is_demo.is_(False)
    if src == "demo":
        return QueueToken.is_demo.is_(True)
    return None


def _where(cond, *extra):
    return [c for c in (cond, *extra) if c is not None]


def day_bounds(loc, d: date) -> tuple[datetime, datetime]:
    tz = cfg.local_tz(loc)
    start = datetime(d.year, d.month, d.day, tzinfo=tz)
    return start.astimezone(timezone.utc), (start + timedelta(days=1)).astimezone(timezone.utc)


def _records(db: Session, start: datetime, end: datetime, source: str | None):
    q = (select(ServiceRecord, QueueToken).join(QueueToken, QueueToken.token_id == ServiceRecord.token_id)
         .join(Service, Service.service_id == QueueToken.service_id)
         .where(ServiceRecord.service_start_time >= start, ServiceRecord.service_start_time < end,
                Service.location_id == cfg.get_location(db).location_id))
    for c in _where(source_filter(source)):
        q = q.where(c)
    return db.execute(q).all()


def _tokens(db: Session, start: datetime, end: datetime, source: str | None) -> list[QueueToken]:
    q = (select(QueueToken).join(Service, Service.service_id == QueueToken.service_id)
         .where(QueueToken.created_at >= start, QueueToken.created_at < end, Service.location_id == cfg.get_location(db).location_id))
    for c in _where(source_filter(source)):
        q = q.where(c)
    return list(db.scalars(q))


def _avg(xs) -> float | None:
    xs = [float(x) for x in xs if x is not None]
    return round(sum(xs) / len(xs), 1) if xs else None


# ------------------------------------------------------------------ overview
def overview(db: Session, source: str | None = None) -> dict:
    loc = cfg.get_location(db)
    today = cfg.local_today(loc)
    start, end = day_bounds(loc, today)
    toks = _tokens(db, start, end, source)
    recs = _records(db, start, end, source)
    snap = qe.build_snapshot(db)
    waiting_now = len(snap.waiting)
    serving = sum(1 for _ in snap.busy_counter_ids)
    active = sum(1 for s in snap.counter_states if s.available)
    predicted60 = 0.0
    method = "fallback"
    for svc in snap.services.values():
        f = next(f for f in demand_service.forecast_service(db, svc, persist=False)["forecasts"] if f["horizon_minutes"] == 60)
        predicted60 += f["predicted_arrivals"]
        method = f["method"]
    thr = float(snap.settings["congestion_queue_length"])
    worst = 0.0
    for sid in snap.services:
        if any(t.service_id == sid for t in snap.waiting):
            est = qe.estimate_new_joiner(snap, sid)
            worst = max(worst, est.minutes or 0)
    wthr = float(snap.settings["wait_threshold_minutes"])
    level = ("critical" if waiting_now >= thr or worst >= 1.5 * wthr else "high" if waiting_now >= 0.7 * thr or worst >= wthr
             else "moderate" if waiting_now >= 0.35 * thr or worst >= 0.5 * wthr else "low")
    has_demo = bool(db.scalar(select(func.count(QueueToken.token_id)).where(QueueToken.is_demo.is_(True)).limit(1)))
    done = [r for r, t in recs if r.service_end_time]
    return {
        "customers_today": len(toks), "served_today": len(done), "currently_waiting": waiting_now, "currently_serving": serving,
        "avg_wait_minutes": _avg(r.actual_wait_minutes for r, _ in recs), "avg_service_minutes": _avg(r.actual_service_duration for r in done),
        "active_counters": active, "total_counters": len(snap.counters), "queue_length": waiting_now,
        "predicted_arrivals_next_hour": round(predicted60, 1), "predicted_arrivals_method": method,
        "congestion_level": level, "abandoned_today": sum(1 for t in toks if t.status in (TokenStatus.cancelled, TokenStatus.no_show)),
        "demo_data_present": has_demo, "demo_mode": get_settings().demo_mode, "generated_at": utcnow(),
    }


# ------------------------------------------------------------------- traffic
def traffic(db: Session, granularity: str, days: int, source: str | None = None) -> dict:
    loc = cfg.get_location(db)
    tz = cfg.local_tz(loc)
    today = cfg.local_today(loc)
    since = day_bounds(loc, today - timedelta(days=max(days, 1) - 1))[0]
    toks = _tokens(db, since, utcnow() + timedelta(days=1), source)
    buckets: dict[str, dict] = defaultdict(lambda: {"arrivals": 0, "cancelled": 0, "no_show": 0})
    for t in toks:
        lt = t.created_at.astimezone(tz)
        if granularity == "hour":
            if lt.date() != today:
                continue
            key = f"{lt.hour:02d}:00"
        elif granularity == "day":
            key = lt.date().isoformat()
        elif granularity == "week":
            y, w, _ = lt.isocalendar(); key = f"{y}-W{w:02d}"
        else:
            key = lt.strftime("%Y-%m")
        buckets[key]["arrivals"] += 1
        if t.status == TokenStatus.cancelled: buckets[key]["cancelled"] += 1
        if t.status == TokenStatus.no_show: buckets[key]["no_show"] += 1
    series = [{"label": k, **v} for k, v in sorted(buckets.items())]
    # peak hours over the whole window
    hourly: dict[int, int] = defaultdict(int)
    for t in toks:
        hourly[t.created_at.astimezone(tz).hour] += 1
    n_days = max(len({t.created_at.astimezone(tz).date() for t in toks}), 1)
    peaks = sorted(({"hour": h, "avg_arrivals": round(c / n_days, 1)} for h, c in hourly.items()), key=lambda x: -x["avg_arrivals"])[:3]
    return {"granularity": granularity, "series": series, "peak_hours": peaks}


def waiting_time(db: Session, days: int, source: str | None = None) -> dict:
    loc = cfg.get_location(db)
    tz = cfg.local_tz(loc)
    today = cfg.local_today(loc)
    since = day_bounds(loc, today - timedelta(days=max(days, 1) - 1))[0]
    recs = _records(db, since, utcnow() + timedelta(days=1), source)
    by_day: dict[str, list] = defaultdict(list)
    by_hour: dict[int, list] = defaultdict(list)
    for r, t in recs:
        lt = r.service_start_time.astimezone(tz)
        by_day[lt.date().isoformat()].append(r)
        by_hour[lt.hour].append(r)
    daily = [{"label": k, "avg_wait": _avg(x.actual_wait_minutes for x in v), "avg_service": _avg(x.actual_service_duration for x in v), "served": len(v)}
             for k, v in sorted(by_day.items())]
    hourly = [{"label": f"{h:02d}:00", "avg_wait": _avg(x.actual_wait_minutes for x in v), "avg_service": _avg(x.actual_service_duration for x in v)}
              for h, v in sorted(by_hour.items())]
    return {"daily": daily, "hourly": hourly, "queue_length_today": queue_length_series(db, today, source)}


def queue_length_series(db: Session, d: date, source: str | None = None) -> list[dict]:
    loc = cfg.get_location(db)
    tz = cfg.local_tz(loc)
    start, end = day_bounds(loc, d)
    toks = _tokens(db, start, end, source)
    if not toks:
        return []
    ids = [t.token_id for t in toks]
    left: dict[int, datetime] = {}
    for r in db.scalars(select(ServiceRecord).where(ServiceRecord.token_id.in_(ids))):
        left[r.token_id] = r.service_start_time
    for e in db.scalars(select(QueueEvent).where(QueueEvent.token_id.in_(ids), QueueEvent.event_type.in_(["cancelled", "expired", "called"]))
                        .order_by(QueueEvent.event_id)):
        left.setdefault(e.token_id, e.timestamp)
    now = utcnow()
    out = []
    t0 = start + timedelta(hours=8)
    while t0 <= min(end, now):
        qlen = sum(1 for t in toks if t.created_at <= t0 < left.get(t.token_id, now + timedelta(days=1)))
        out.append({"label": t0.astimezone(tz).strftime("%H:%M"), "queue_length": qlen})
        t0 += timedelta(minutes=30)
    return out


# ------------------------------------------------------- counter performance
def counter_performance(db: Session, days: int, source: str | None = None) -> list[dict]:
    loc = cfg.get_location(db)
    tz = cfg.local_tz(loc)
    since = day_bounds(loc, cfg.local_today(loc) - timedelta(days=max(days, 1) - 1))[0]
    recs = _records(db, since, utcnow() + timedelta(days=1), source)
    per: dict[int, list] = defaultdict(list)
    for r, t in recs:
        per[r.counter_id].append(r)
    out = []
    for c in db.scalars(select(Counter).where(Counter.location_id == loc.location_id).order_by(Counter.counter_id)):
        rows = per.get(c.counter_id, [])
        active_days = len({r.service_start_time.astimezone(tz).date() for r in rows}) or 1
        busy = sum(float(r.actual_service_duration or 0) for r in rows)
        out.append({"counter_id": c.counter_id, "counter_name": c.counter_name, "status": c.status.value, "served": len(rows),
                    "avg_service_minutes": _avg(r.actual_service_duration for r in rows), "avg_wait_minutes": _avg(r.actual_wait_minutes for r in rows),
                    "utilization": round(min(1.0, busy / (active_days * OPERATING_MINUTES)), 3) if rows else 0.0})
    return out


# -------------------------------------------------------------- daily report
def daily_report(db: Session, d: date, source: str | None = None) -> dict:
    loc = cfg.get_location(db)
    tz = cfg.local_tz(loc)
    start, end = day_bounds(loc, d)
    toks = _tokens(db, start, end, source)
    recs = _records(db, start, end, source)
    total = len(toks)
    abandoned = sum(1 for t in toks if t.status in (TokenStatus.cancelled, TokenStatus.no_show))
    hourly: dict[int, int] = defaultdict(int)
    for t in toks:
        hourly[t.created_at.astimezone(tz).hour] += 1
    peaks = [{"hour": h, "arrivals": c} for h, c in sorted(hourly.items(), key=lambda kv: -kv[1])[:3]]
    ids = [t.token_id for t in toks]
    first_pred: dict[int, Prediction] = {}
    if ids:
        for p in db.scalars(select(Prediction).where(Prediction.token_id.in_(ids)).order_by(Prediction.prediction_id)):
            first_pred.setdefault(p.token_id, p)
    errs = [abs(first_pred[r.token_id].predicted_waiting_time - r.actual_wait_minutes) for r, _ in recs
            if r.token_id in first_pred and r.actual_wait_minutes is not None]
    settings = cfg.get_settings_map(db, loc.location_id)
    avg_wait = _avg(r.actual_wait_minutes for r, _ in recs)
    recommendations = []
    if peaks:
        recommendations.append(f"Peak arrivals were around {', '.join(f'{p['hour']:02d}:00' for p in peaks)}; schedule extra counters then.")
    if avg_wait and avg_wait > settings["wait_threshold_minutes"] * 0.6:
        recommendations.append(f"Average wait ({avg_wait:.0f} min) approached the {settings['wait_threshold_minutes']} min threshold; review counter coverage at peak.")
    if total and abandoned / total > 0.15:
        recommendations.append(f"Abandonment was {abandoned / total:.0%} of tokens; consider tighter arrival windows and reminders.")
    if not recommendations:
        recommendations.append("No operational issues detected for this day.")
    return {
        "date": d.isoformat(), "total_tokens": total, "customers_served": len(recs), "avg_wait_minutes": avg_wait,
        "avg_service_minutes": _avg(r.actual_service_duration for r, _ in recs), "peak_periods": peaks,
        "abandonment_rate": round(abandoned / total, 3) if total else 0.0, "abandoned": abandoned,
        "counter_utilization": counter_performance(db, 1, source) if d == cfg.local_today(loc) else counter_performance_for_day(db, d, source),
        "prediction_mae_minutes": round(sum(errs) / len(errs), 2) if errs else None, "prediction_samples": len(errs),
        "recommendations": recommendations,
        "data_note": "Includes demo data" if (source or ("all" if get_settings().demo_mode else "live")) != "live" and any(t.is_demo for t in toks) else "Live data",
    }


def counter_performance_for_day(db: Session, d: date, source: str | None) -> list[dict]:
    loc = cfg.get_location(db)
    start, end = day_bounds(loc, d)
    recs = _records(db, start, end, source)
    per: dict[int, list] = defaultdict(list)
    for r, _ in recs:
        per[r.counter_id].append(r)
    out = []
    for c in db.scalars(select(Counter).where(Counter.location_id == loc.location_id).order_by(Counter.counter_id)):
        rows = per.get(c.counter_id, [])
        busy = sum(float(r.actual_service_duration or 0) for r in rows)
        out.append({"counter_id": c.counter_id, "counter_name": c.counter_name, "status": c.status.value, "served": len(rows),
                    "avg_service_minutes": _avg(r.actual_service_duration for r in rows), "avg_wait_minutes": _avg(r.actual_wait_minutes for r in rows),
                    "utilization": round(min(1.0, busy / OPERATING_MINUTES), 3)})
    return out


def report_csv(rep: dict) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["QueueLess daily report", rep["date"]]); w.writerow(["Data", rep["data_note"]]); w.writerow([])
    for k in ("total_tokens", "customers_served", "avg_wait_minutes", "avg_service_minutes", "abandonment_rate", "abandoned",
              "prediction_mae_minutes", "prediction_samples"):
        w.writerow([k, rep[k]])
    w.writerow([]); w.writerow(["peak_hour", "arrivals"])
    for p in rep["peak_periods"]:
        w.writerow([f"{p['hour']:02d}:00", p["arrivals"]])
    w.writerow([]); w.writerow(["counter", "served", "avg_service_min", "avg_wait_min", "utilization"])
    for c in rep["counter_utilization"]:
        w.writerow([c["counter_name"], c["served"], c["avg_service_minutes"], c["avg_wait_minutes"], c["utilization"]])
    w.writerow([]); w.writerow(["recommendations"])
    for r in rep["recommendations"]:
        w.writerow([r])
    return buf.getvalue()


def report_pdf(rep: dict) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, title=f"QueueLess daily report {rep['date']}")
    st = getSampleStyleSheet()
    fmt = lambda v, suffix="": "—" if v is None else f"{v}{suffix}"
    el = [Paragraph(f"QueueLess — Daily Report {rep['date']}", st["Title"]), Paragraph(f"Data: {rep['data_note']}", st["Italic"]), Spacer(1, 12)]
    kpis = [["Metric", "Value"], ["Total tokens", rep["total_tokens"]], ["Customers served", rep["customers_served"]],
            ["Average wait", fmt(rep["avg_wait_minutes"], " min")], ["Average service time", fmt(rep["avg_service_minutes"], " min")],
            ["Abandonment", f"{rep['abandonment_rate']:.1%} ({rep['abandoned']})"],
            ["Prediction MAE", fmt(rep["prediction_mae_minutes"], f" min (n={rep['prediction_samples']})")]]
    ts = TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2f6bff")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                     ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")), ("FONTSIZE", (0, 0), (-1, -1), 9)])
    t1 = Table(kpis, colWidths=[200, 250]); t1.setStyle(ts); el += [t1, Spacer(1, 14), Paragraph("Peak periods", st["Heading3"])]
    el.append(Paragraph(", ".join(f"{p['hour']:02d}:00 ({p['arrivals']} arrivals)" for p in rep["peak_periods"]) or "No data", st["Normal"]))
    el += [Spacer(1, 12), Paragraph("Counter utilization", st["Heading3"])]
    rows = [["Counter", "Served", "Avg service", "Avg wait", "Utilization"]] + [
        [c["counter_name"], c["served"], fmt(c["avg_service_minutes"], " min"), fmt(c["avg_wait_minutes"], " min"), f"{c['utilization']:.0%}"] for c in rep["counter_utilization"]]
    t2 = Table(rows); t2.setStyle(ts); el += [t2, Spacer(1, 12), Paragraph("Operational recommendations", st["Heading3"])]
    el += [Paragraph(f"• {r}", st["Normal"]) for r in rep["recommendations"]]
    doc.build(el)
    return buf.getvalue()


# ------------------------------------------------------------- ML monitoring
def ml_monitoring(db: Session, days: int = 30, source: str | None = None) -> dict:
    loc = cfg.get_location(db)
    tz = cfg.local_tz(loc)
    since = utcnow() - timedelta(days=days)
    recs = _records(db, since, utcnow() + timedelta(days=1), source)
    ids = [r.token_id for r, _ in recs if r.actual_wait_minutes is not None]
    first: dict[int, Prediction] = {}
    for chunk in range(0, len(ids), 500):
        for p in db.scalars(select(Prediction).where(Prediction.token_id.in_(ids[chunk:chunk + 500])).order_by(Prediction.prediction_id)):
            first.setdefault(p.token_id, p)
    pairs = []
    for r, t in recs:
        p = first.get(r.token_id)
        if p is not None and r.actual_wait_minutes is not None:
            pairs.append((r.service_start_time.astimezone(tz).date(), p, float(r.actual_wait_minutes), t.is_demo))

    def stats(rows):
        if not rows:
            return None
        err = [p.predicted_waiting_time - a for _, p, a, _ in rows]
        ml_rows = [(p, a) for _, p, a, _ in rows if p.prediction_lower_bound is not None]
        return {"n": len(rows), "mae": round(sum(abs(e) for e in err) / len(err), 2), "rmse": round(math.sqrt(sum(e * e for e in err) / len(err)), 2),
                "bias": round(sum(err) / len(err), 2),
                "interval_coverage": round(sum(1 for p, a in ml_rows if p.prediction_lower_bound <= a <= p.prediction_upper_bound) / len(ml_rows), 3) if ml_rows else None}

    by_method = {m: stats([x for x in pairs if x[1].method == m]) for m in ("ml", "fallback")}
    by_day: dict[str, list] = defaultdict(list)
    for d, p, a, _ in pairs:
        by_day[d.isoformat()].append((d, p, a, None))
    daily = [{"label": k, "mae": stats(v)["mae"], "n": len(v)} for k, v in sorted(by_day.items())]
    recent = [x for x in pairs if x[0] >= cfg.local_today(loc) - timedelta(days=7)]
    prior = [x for x in pairs if cfg.local_today(loc) - timedelta(days=14) <= x[0] < cfg.local_today(loc) - timedelta(days=7)]
    s_recent, s_prior = stats(recent), stats(prior)
    drift = None
    if s_recent and s_prior and s_prior["mae"] > 0:
        drift = {"recent_mae": s_recent["mae"], "prior_mae": s_prior["mae"], "ratio": round(s_recent["mae"] / s_prior["mae"], 2),
                 "flag": s_recent["mae"] / s_prior["mae"] > 1.2}
    sample = [{"predicted": p.predicted_waiting_time, "actual": a} for _, p, a, _ in pairs[-300:]]

    demand_backfilled = demand_service.backfill_actuals(db)
    fc = db.scalars(select(DemandForecast).join(Service, Service.service_id == DemandForecast.service_id).where(
        DemandForecast.horizon_minutes == 60, DemandForecast.actual_arrivals.is_not(None), DemandForecast.interval_start >= since,
        Service.location_id == loc.location_id).order_by(DemandForecast.interval_start)).all()
    dem_err = sum(abs(f.predicted_arrivals - f.actual_arrivals) for f in fc)
    dem_act = sum(f.actual_arrivals for f in fc)
    return {
        "wait_model": predictor.wait_model_info(), "demand_model": predictor.demand_model_info(),
        "live_vs_actual": {"all": stats(pairs), "by_method": by_method, "real_only": stats([x for x in pairs if not x[3]]),
                           "demo_only": stats([x for x in pairs if x[3]])},
        "daily_mae": daily, "drift": drift, "scatter": sample,
        "demand": {"n": len(fc), "wape": round(dem_err / dem_act, 3) if dem_act else None,
                   "mae": round(dem_err / len(fc), 2) if fc else None, "backfilled": demand_backfilled},
        "note": "Metrics on demo rows come from simulated history and are NOT evidence of real-world accuracy. "
                "'real_only' becomes meaningful after real customers have been served.",
    }


def predicted_vs_actual_arrivals(db: Session, d: date | None = None) -> list[dict]:
    loc = cfg.get_location(db)
    tz = cfg.local_tz(loc)
    demand_service.backfill_actuals(db)
    if d is None:   # default: today, or the most recent day that has forecasts (e.g. before today's first forecast is stored)
        latest = db.scalar(select(func.max(DemandForecast.interval_start)).join(Service, Service.service_id == DemandForecast.service_id)
                           .where(DemandForecast.horizon_minutes == 60, Service.location_id == loc.location_id))
        d = latest.astimezone(tz).date() if latest else cfg.local_today(loc)
    start, end = day_bounds(loc, d)
    rows = db.scalars(select(DemandForecast).join(Service, Service.service_id == DemandForecast.service_id).where(
        DemandForecast.horizon_minutes == 60, DemandForecast.interval_start >= start, DemandForecast.interval_start < end,
        Service.location_id == loc.location_id)).all()
    agg: dict[str, dict] = defaultdict(lambda: {"predicted": 0.0, "actual": 0, "has_actual": False})
    for f in rows:
        key = f.interval_start.astimezone(tz).strftime("%H:00")
        agg[key]["predicted"] += f.predicted_arrivals if f.interval_start.astimezone(tz).minute == 0 else 0
        if f.actual_arrivals is not None and f.interval_start.astimezone(tz).minute == 0:
            agg[key]["actual"] += f.actual_arrivals; agg[key]["has_actual"] = True
    return [{"label": k, "predicted": round(v["predicted"], 1), "actual": v["actual"] if v["has_actual"] else None} for k, v in sorted(agg.items())]
