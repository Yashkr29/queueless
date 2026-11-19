"""Queue engine: builds a consistent snapshot of the location, estimates waits (ML with labelled fallback),
derives arrival windows, and persists the derived state (positions, approaching status, predictions, notices).

Ordering policy (PRD §4): priority rank, then queue-entry time. ML never influences eligibility or order.
Estimates are REMAINING wait computed from the current state, i.e. the model is asked "how long would someone
in this position, in this state, wait?".
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ..ml import predictor
from ..ml.features import (
    DEFAULT_HISTORICAL_WAIT, CounterState, QueuedToken, WaitSnapshotContext, compute_wait_features, fallback_wait_minutes,
)
from ..models import (
    ACTIVE_STATUSES, PRIORITY_RANK, WAITING_STATUSES, Counter, CounterStatus, Location, Prediction, Priority, QueueEvent, QueueToken,
    Service, ServiceRecord, StaffAvailability, TokenStatus, utcnow,
)
from ..realtime import Outbox
from ..services import settings_service as cfg
from ..services.notifications import notify

_hist_cache: dict[tuple[int, int], tuple[float, dict[int, float]]] = {}   # (location, service) -> (ts, {hour: mean})


@dataclass
class Estimate:
    minutes: float | None
    lower: float | None
    upper: float | None
    method: str                      # ml | fallback | unavailable
    model_version: str | None
    trained_on: str | None
    note: str
    features: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {"wait_minutes": self.minutes, "lower_minutes": self.lower, "upper_minutes": self.upper, "method": self.method,
                "model_version": self.model_version, "trained_on": self.trained_on, "note": self.note}


@dataclass
class Snapshot:
    now: datetime
    loc: Location
    settings: dict
    counters: list[Counter]
    counter_states: list[CounterState]
    busy_counter_ids: set[int]
    waiting: list[QueueToken]
    queued: list[QueuedToken]
    services: dict[int, Service]
    avg_service: dict[int, float]
    arrival_rate: float
    hist: dict[int, dict[int, float]]
    local_hour: int
    local_dow: int


def counter_available(c: Counter) -> bool:
    return c.status == CounterStatus.open and (c.staff is None or c.staff.availability != StaffAvailability.off)


def _hist_wait(db: Session, loc: Location, service_id: int, now: datetime) -> dict[int, float]:
    key = (loc.location_id, service_id)
    cached = _hist_cache.get(key)
    if cached and time.time() - cached[0] < 300:
        return cached[1]
    rows = db.execute(
        select(ServiceRecord.service_start_time, ServiceRecord.actual_wait_minutes)
        .join(QueueToken, QueueToken.token_id == ServiceRecord.token_id)
        .where(QueueToken.service_id == service_id, ServiceRecord.actual_wait_minutes.is_not(None),
               ServiceRecord.service_start_time >= now - timedelta(days=28))).all()
    tz = cfg.local_tz(loc)
    buckets: dict[int, list[float]] = {}
    for start, wait in rows:
        buckets.setdefault(start.astimezone(tz).hour, []).append(float(wait))
    out = {h: sum(v) / len(v) for h, v in buckets.items() if len(v) >= 3}
    _hist_cache[key] = (time.time(), out)
    return out


def clear_caches() -> None:
    _hist_cache.clear()


def build_snapshot(db: Session, location_id: int | None = None) -> Snapshot:
    """Everything the engine needs about ONE organization. Counters, services and queues of other locations are excluded."""
    loc = cfg.get_location(db, location_id)
    settings = cfg.get_settings_map(db, loc.location_id)
    now = utcnow()
    local = now.astimezone(cfg.local_tz(loc))

    counters = list(db.scalars(select(Counter).where(Counter.location_id == loc.location_id)
                               .options(selectinload(Counter.service_links), selectinload(Counter.staff))
                               .order_by(Counter.counter_id)))
    counter_ids = [c.counter_id for c in counters]
    busy = set(db.scalars(select(QueueToken.counter_id).where(
        QueueToken.status.in_([TokenStatus.called, TokenStatus.serving]), QueueToken.counter_id.in_(counter_ids)))) if counter_ids else set()
    states = [CounterState(c.counter_id, frozenset(c.service_ids), counter_available(c), c.counter_id in busy) for c in counters]

    waiting = list(db.scalars(select(QueueToken).join(Service, Service.service_id == QueueToken.service_id)
                              .where(QueueToken.status.in_(WAITING_STATUSES), Service.location_id == loc.location_id)
                              .options(selectinload(QueueToken.service), selectinload(QueueToken.counter))
                              .order_by(QueueToken.created_at, QueueToken.token_id)))
    queued = [QueuedToken(t.token_id, t.service_id, PRIORITY_RANK[t.priority_type], t.created_at.timestamp()) for t in waiting]

    services = {s.service_id: s for s in db.scalars(select(Service).where(Service.location_id == loc.location_id))}
    avg: dict[int, float] = {}
    for sid, s in services.items():
        durs = [float(d) for d in db.scalars(
            select(ServiceRecord.actual_service_duration).join(QueueToken, QueueToken.token_id == ServiceRecord.token_id)
            .where(QueueToken.service_id == sid, ServiceRecord.actual_service_duration.is_not(None))
            .order_by(ServiceRecord.record_id.desc()).limit(50))]
        avg[sid] = (sum(durs) / len(durs)) if len(durs) >= 10 else (sum(durs) + s.average_service_duration * (10 - len(durs))) / 10

    recent = db.scalar(select(func.count(QueueToken.token_id)).join(Service, Service.service_id == QueueToken.service_id)
                       .where(QueueToken.created_at >= now - timedelta(minutes=30), Service.location_id == loc.location_id)) or 0
    hist = {sid: _hist_wait(db, loc, sid, now) for sid in services}
    return Snapshot(now, loc, settings, counters, states, busy, waiting, queued, services, avg, recent * 2.0, hist,
                    local.hour, local.weekday())


def _features(snap: Snapshot, q: QueuedToken) -> dict:
    ctx = WaitSnapshotContext(
        hour=snap.local_hour, day_of_week=snap.local_dow,
        average_service_time=snap.avg_service.get(q.service_id, 8.0), current_arrival_rate=snap.arrival_rate,
        historical_average_wait=snap.hist.get(q.service_id, {}).get(snap.local_hour, DEFAULT_HISTORICAL_WAIT))
    return compute_wait_features(q, snap.queued, snap.counter_states, ctx)


def _estimate_from(feat: dict, ml) -> Estimate:
    if feat["active_counters"] <= 0:
        return Estimate(None, None, None, "unavailable", None, None,
                        "No eligible counter is open right now. An estimate will appear as soon as one opens.", feat)
    if ml is not None:
        src = "simulated" if ml.trained_on == "synthetic" else "real"
        return Estimate(ml.minutes, ml.lower, ml.upper, "ml", ml.model_version, ml.trained_on,
                        f"ML estimate (80% range {ml.lower:.0f}–{ml.upper:.0f} min), model trained on {src} data. A prediction, not a guarantee.", feat)
    fb = fallback_wait_minutes(feat)
    return Estimate(fb, None, None, "fallback", "fallback-v1", None,
                    "Non-ML estimate from customers ahead, average service time and open counters. No confidence range available.", feat)


def estimate_all(snap: Snapshot) -> dict[int, Estimate]:
    feats = {q.token_id: _features(snap, q) for q in snap.queued}
    ids = list(feats)
    ml = predictor.predict_wait_batch([feats[i] for i in ids]) if ids else []
    ml = ml if ml is not None else [None] * len(ids)
    return {i: _estimate_from(feats[i], m) for i, m in zip(ids, ml)}


def estimate_new_joiner(snap: Snapshot, service_id: int) -> Estimate:
    """What would a regular-priority customer joining this service right now wait?"""
    q = QueuedToken(-1, service_id, PRIORITY_RANK[Priority.none], snap.now.timestamp() + 1)
    snap2 = Snapshot(**{**snap.__dict__, "queued": snap.queued + [q]})
    feat = _features(snap2, q)
    ml = predictor.predict_wait(feat)
    return _estimate_from(feat, ml)


def arrival_window(est: Estimate, snap: Snapshot) -> dict | None:
    """PRD A6: expected 12:40, buffer 15 -> recommended 12:25, window 12:20-12:35 (widened by ML uncertainty)."""
    if est.minutes is None:
        return None
    buf = float(snap.settings["arrival_buffer_minutes"])
    expected = snap.now + timedelta(minutes=est.minutes)
    earliest = snap.now + timedelta(minutes=est.lower if est.lower is not None else est.minutes)
    recommended = max(snap.now, expected - timedelta(minutes=buf))
    start = max(snap.now, earliest - timedelta(minutes=buf + 5))
    end = max(recommended, expected - timedelta(minutes=5))
    return {"expected_service_time": expected, "recommended_arrival": recommended, "window_start": start, "window_end": end,
            "arrive_now": expected - timedelta(minutes=buf) <= snap.now}


def token_view(token: QueueToken, snap: Snapshot, estimates: dict[int, Estimate]) -> dict:
    est = estimates.get(token.token_id)
    waiting = token.status in WAITING_STATUSES
    ahead = est.features.get("customers_ahead") if est and waiting else None
    return {
        "token_id": token.token_id, "token_label": token.token_label, "status": token.status, "priority_type": token.priority_type,
        "service": token.service, "queue_position": (ahead + 1) if ahead is not None else None, "customers_ahead": ahead,
        "counter": {"counter_id": token.counter.counter_id, "counter_name": token.counter.counter_name} if token.counter else None,
        "created_at": token.created_at, "arrival_time": token.arrival_time,
        "estimate": est.as_dict() if est and waiting else None,
        "arrival_window": arrival_window(est, snap) if est and waiting and not token.arrival_time else None,
    }


def log_event(db: Session, token: QueueToken, event_type: str, actor_id: int | None = None, **meta) -> None:
    db.add(QueueEvent(token_id=token.token_id, event_type=event_type, actor_user_id=actor_id, metadata_=meta))


def refresh(db: Session, outbox: Outbox, location_id: int | None = None) -> dict[int, dict]:
    """Recompute derived queue state for one organization. Call inside the request transaction after a mutation."""
    loc = cfg.get_location(db, location_id)
    today = cfg.local_today(loc)
    stale = db.scalars(select(QueueToken).join(Service, Service.service_id == QueueToken.service_id).where(
        QueueToken.status.in_(ACTIVE_STATUSES), QueueToken.queue_date < today, Service.location_id == loc.location_id)).all()
    for t in stale:                                    # end-of-day reset: yesterday's unserved tokens expire
        t.status, t.queue_position, t.counter_id = TokenStatus.cancelled, None, None
        log_event(db, t, "expired", reason="end_of_day")
    if stale:
        db.flush()

    snap = build_snapshot(db, loc.location_id)
    est = estimate_all(snap)
    approaching_n = int(snap.settings["approaching_ahead"])
    delay_n = float(snap.settings["delay_notify_minutes"])
    ids = [t.token_id for t in snap.waiting]

    last_pred: dict[int, Prediction] = {}
    delay_base: dict[int, float] = {}
    if ids:
        for p in db.scalars(select(Prediction).where(Prediction.token_id.in_(ids)).order_by(Prediction.prediction_id.desc())):
            last_pred.setdefault(p.token_id, p)
        first: dict[int, float] = {}
        for p in db.scalars(select(Prediction).where(Prediction.token_id.in_(ids)).order_by(Prediction.prediction_id)):
            first.setdefault(p.token_id, p.predicted_waiting_time)
        delay_base = first
        for e in db.scalars(select(QueueEvent).where(QueueEvent.token_id.in_(ids), QueueEvent.event_type == "delay_notified")
                            .order_by(QueueEvent.event_id)):
            delay_base[e.token_id] = float(e.metadata_.get("wait", 0))

    for t in snap.waiting:
        e = est[t.token_id]
        ahead = e.features["customers_ahead"]
        t.queue_position = ahead + 1
        if ahead <= approaching_n and t.status in (TokenStatus.booked, TokenStatus.confirmed, TokenStatus.waiting):
            t.status = TokenStatus.approaching
            log_event(db, t, "approaching", customers_ahead=ahead)
            notify(db, outbox, t.user_id, "approaching_turn", "Your turn is approaching",
                   f"Token {t.token_label}: about {ahead} ahead of you. Please head to the counter area.", t.token_id)
        if e.minutes is not None:
            prev = last_pred.get(t.token_id)
            if prev is None or abs(prev.predicted_waiting_time - e.minutes) >= 2 or prev.method != e.method:
                db.add(Prediction(token_id=t.token_id, predicted_waiting_time=e.minutes, prediction_lower_bound=e.lower,
                                  prediction_upper_bound=e.upper, method=e.method, model_version=e.model_version or "fallback-v1",
                                  features=e.features))
            base = delay_base.get(t.token_id)
            if base is not None and e.minutes - base >= delay_n and t.token_id in last_pred:
                log_event(db, t, "delay_notified", wait=e.minutes, previous=base)
                notify(db, outbox, t.user_id, "delay", "Your wait has increased",
                       f"Token {t.token_label}: your estimated wait is now about {e.minutes:.0f} min (was {base:.0f}).", t.token_id)
    db.flush()

    views: dict[int, dict] = {}
    for t in snap.waiting:
        views[t.token_id] = token_view(t, snap, est)
    # called / serving tokens also get live pushes (counter assignment, status)
    for t in db.scalars(select(QueueToken).join(Service, Service.service_id == QueueToken.service_id)
                        .where(QueueToken.status.in_([TokenStatus.called, TokenStatus.serving]), Service.location_id == loc.location_id)
                        .options(selectinload(QueueToken.service), selectinload(QueueToken.counter))):
        views[t.token_id] = token_view(t, snap, est)
    by_id = {t.token_id: t for t in snap.waiting}
    for tid, v in views.items():
        uid = by_id[tid].user_id if tid in by_id else db.get(QueueToken, tid).user_id
        outbox.to_user(uid, {"type": "token_update", "token": v})
    outbox.to_staff({"type": "queue_changed"})
    return views


def view_for_tokens(db: Session, tokens: list[QueueToken]) -> list[dict]:
    """Read-only views (no persistence). Tokens may belong to different organizations: one snapshot per organization."""
    by_loc: dict[int, tuple] = {}
    out = []
    for t in tokens:
        lid = t.service.location_id
        if lid not in by_loc:
            snap = build_snapshot(db, lid)
            by_loc[lid] = (snap, estimate_all(snap))
        _ = t.counter
        out.append(token_view(t, *by_loc[lid]))
    return out
