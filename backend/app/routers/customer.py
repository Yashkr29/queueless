"""Customer-facing endpoints: service discovery, queue, notifications, predictions."""
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..engine import optimizer, queue_engine as qe
from ..ml import predictor
from ..models import Location, Notification, PushDevice, QueueToken, Role, Service, ServiceStatus, TokenStatus, User, utcnow
from ..realtime import Outbox, flush_outbox
from ..schemas import ConfirmArrivalIn, JoinIn, ServiceOut, ServiceStatusOut, TokenOut
from ..security import current_user, staff_user
from ..services import demand_service, queue_ops, settings_service as cfg

router = APIRouter()


# --------------------------------------------------------------- organizations
@router.get("/locations", tags=["locations"])
def list_locations(db: Session = Depends(get_db), _: User = Depends(current_user)):
    """Organizations customers can choose from (active only)."""
    from sqlalchemy import func
    counts = dict(db.execute(select(Service.location_id, func.count(Service.service_id)).where(Service.status == ServiceStatus.active)
                             .group_by(Service.location_id)).all())
    rows = db.scalars(select(Location).where(Location.is_active.is_(True)).order_by(Location.location_id)).all()
    return [{"location_id": l.location_id, "name": l.name, "location_type": l.location_type, "address": l.address,
             "timezone": l.timezone, "service_count": counts.get(l.location_id, 0)} for l in rows]


# ---------------------------------------------------------------- services
def _service_status(db: Session, snap: qe.Snapshot, svc: Service) -> dict:
    est = qe.estimate_new_joiner(snap, svc.service_id)
    return {"service": svc, "queue_length": sum(1 for t in snap.waiting if t.service_id == svc.service_id),
            "active_counters": sum(1 for c in snap.counter_states if c.available and svc.service_id in c.service_ids),
            "open_counters": sum(1 for c in snap.counters if c.status.value == "open" and svc.service_id in c.service_ids),
            "estimate": est.as_dict()}


@router.get("/services", response_model=list[ServiceStatusOut], tags=["services"])
def list_services(db: Session = Depends(get_db), _: User = Depends(current_user)):
    snap = qe.build_snapshot(db)
    return [_service_status(db, snap, s) for s in snap.services.values() if s.status == ServiceStatus.active]


@router.get("/services/{service_id}", response_model=ServiceStatusOut, tags=["services"])
def get_service(service_id: int, db: Session = Depends(get_db), _: User = Depends(current_user)):
    row = db.get(Service, service_id)
    if not row:
        raise HTTPException(404, "Service not found")
    snap = qe.build_snapshot(db, row.location_id)         # the service's own organization, whatever the header says
    return _service_status(db, snap, snap.services[service_id])


@router.get("/queue/status/{service_id}", response_model=ServiceStatusOut, tags=["queue"])
def queue_status(service_id: int, db: Session = Depends(get_db), _: User = Depends(current_user)):
    return get_service(service_id, db, _)


# ------------------------------------------------------------------- queue
def _commit_and_view(db: Session, outbox: Outbox, bg: BackgroundTasks, token: QueueToken) -> dict:
    qe.refresh(db, outbox)
    db.commit()
    bg.add_task(flush_outbox, outbox)
    return qe.view_for_tokens(db, [token])[0]


@router.post("/queue/join", response_model=TokenOut, status_code=201, tags=["queue"])
def join(body: JoinIn, bg: BackgroundTasks, db: Session = Depends(get_db), user: User = Depends(current_user)):
    outbox = Outbox()
    token = queue_ops.join_queue(db, outbox, user, body.service_id, body.priority_type)
    return _commit_and_view(db, outbox, bg, token)


@router.get("/queue/mine", response_model=list[TokenOut], tags=["queue"])
def my_tokens(active_only: bool = False, limit: int = Query(50, le=200), db: Session = Depends(get_db), user: User = Depends(current_user)):
    q = select(QueueToken).where(QueueToken.user_id == user.user_id).order_by(QueueToken.created_at.desc()).limit(limit)
    if active_only:
        q = q.where(QueueToken.status.in_([s for s in TokenStatus if s not in (TokenStatus.completed, TokenStatus.cancelled, TokenStatus.no_show)]))
    return qe.view_for_tokens(db, list(db.scalars(q)))


def _own_or_staff(db: Session, token_id: int, user: User) -> QueueToken:
    t = queue_ops.get_token_or_404(db, token_id)
    if t.user_id != user.user_id and user.role == Role.customer:
        raise HTTPException(404, "Token not found")        # 404, not 403: do not reveal other customers' tokens
    return t


@router.get("/queue/{token_id}", response_model=TokenOut, tags=["queue"])
def get_token(token_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return qe.view_for_tokens(db, [_own_or_staff(db, token_id, user)])[0]


@router.post("/queue/{token_id}/cancel", response_model=TokenOut, tags=["queue"])
def cancel(token_id: int, bg: BackgroundTasks, db: Session = Depends(get_db), user: User = Depends(current_user)):
    token = _own_or_staff(db, token_id, user)
    outbox = Outbox()
    queue_ops.cancel_token(db, outbox, token, user)
    return _commit_and_view(db, outbox, bg, token)


@router.post("/queue/{token_id}/confirm-arrival", response_model=TokenOut, tags=["queue"])
def confirm_arrival(token_id: int, bg: BackgroundTasks, body: ConfirmArrivalIn | None = None, db: Session = Depends(get_db),
                    user: User = Depends(current_user)):
    token = _own_or_staff(db, token_id, user)
    outbox = Outbox()
    queue_ops.confirm_arrival(db, token, user, (body or ConfirmArrivalIn()).mode)
    return _commit_and_view(db, outbox, bg, token)


# ------------------------------------------------------------ notifications
@router.get("/notifications", tags=["notifications"])
def list_notifications(limit: int = Query(50, le=200), db: Session = Depends(get_db), user: User = Depends(current_user)):
    rows = db.scalars(select(Notification).where(Notification.user_id == user.user_id).order_by(Notification.notification_id.desc()).limit(limit)).all()
    unread = db.scalar(select(func.count(Notification.notification_id)).where(Notification.user_id == user.user_id, Notification.read_at.is_(None)))
    return {"unread": unread, "items": [{"notification_id": n.notification_id, "notification_type": n.notification_type, "title": n.title,
                                         "message": n.message, "token_id": n.token_id, "created_at": n.created_at, "read": n.read_at is not None} for n in rows]}


@router.post("/notifications/read-all", tags=["notifications"])
def read_all(db: Session = Depends(get_db), user: User = Depends(current_user)):
    for n in db.scalars(select(Notification).where(Notification.user_id == user.user_id, Notification.read_at.is_(None))):
        n.read_at = utcnow()
    db.commit()
    return {"ok": True}


@router.post("/notifications/devices", tags=["notifications"], status_code=201)
def register_device(body: dict, db: Session = Depends(get_db), user: User = Depends(current_user)):
    tok = str(body.get("fcm_token", "")).strip()
    if not 20 <= len(tok) <= 4096:
        raise HTTPException(422, "fcm_token is required")
    existing = db.scalar(select(PushDevice).where(PushDevice.fcm_token == tok))
    if existing:
        existing.user_id = user.user_id
    else:
        db.add(PushDevice(user_id=user.user_id, fcm_token=tok))
    db.commit()
    return {"ok": True}


# -------------------------------------------------------------- predictions
@router.get("/predictions/wait-time/{token_id}", tags=["predictions"])
def wait_time(token_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    view = qe.view_for_tokens(db, [_own_or_staff(db, token_id, user)])[0]
    return {"token_id": token_id, "prediction_timestamp": utcnow(), "estimate": view["estimate"], "arrival_window": view["arrival_window"],
            "customers_ahead": view["customers_ahead"]}


@router.get("/predictions/demand/{service_id}", tags=["predictions"])
def demand(service_id: int, db: Session = Depends(get_db), _: User = Depends(staff_user)):
    svc = db.get(Service, service_id)
    if not svc:
        raise HTTPException(404, "Service not found")
    if db.info.get("restrict_location") and svc.location_id != db.info["restrict_location"]:
        raise HTTPException(404, "Service not found")
    cfg.set_location(db, svc.location_id)
    result = demand_service.forecast_service(db, svc)
    db.commit()
    snap = qe.build_snapshot(db)
    active = sum(1 for c in snap.counter_states if c.available and service_id in c.service_ids)
    avg = snap.avg_service.get(service_id, svc.average_service_duration)
    for f in result["forecasts"]:
        f["expected_workload_minutes"] = round(f["predicted_arrivals"] * avg, 1)
        f["capacity_minutes"] = active * f["horizon_minutes"]
        f["potential_congestion"] = f["capacity_minutes"] == 0 or f["expected_workload_minutes"] > f["capacity_minutes"]
    result["active_counters"] = active
    result["preparation"] = [a["recommendation"] for a in optimizer.evaluate(db, snap, service_id) if a["type"] == "demand_exceeds_capacity"]
    return result


@router.get("/predictions/congestion/{service_id}", tags=["predictions"])
def congestion(service_id: int, db: Session = Depends(get_db), _: User = Depends(staff_user)):
    svc = db.get(Service, service_id)
    if not svc or (db.info.get("restrict_location") and svc.location_id != db.info["restrict_location"]):
        raise HTTPException(404, "Service not found")
    cfg.set_location(db, svc.location_id)
    return {"service_id": service_id, "alerts": optimizer.evaluate(db, None, service_id)}


@router.get("/predictions/models", tags=["predictions"])
def models(_: User = Depends(staff_user)):
    return {"wait_time": predictor.wait_model_info(), "demand": predictor.demand_model_info(), "registry": predictor.registry()}
