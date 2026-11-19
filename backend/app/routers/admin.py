"""Staff / admin endpoints. Every mutation: transaction -> engine refresh -> commit -> WebSocket flush."""
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from ..db import get_db
from ..engine import optimizer, queue_engine as qe
from ..models import (
    ACTIVE_STATUSES, WAITING_STATUSES, AuditLog, Counter, CounterService, CounterStatus, QueueEvent, QueueToken, Role, Service, ServiceRecord,
    ServiceStatus, Staff, TokenStatus, User, utcnow, Location,
)
from ..realtime import Outbox, flush_outbox
from ..schemas import (
    CallIn, CallNextIn, CounterIn, CounterOut, CounterPatch, LocationIn, LocationPatch, ReasonIn, ServiceIn, ServiceOut, ServicePatch,
    SettingsPatch, StaffIn, StaffPatch, TokenPatchIn,
)
from ..security import admin_user, hash_password, staff_user
from zoneinfo import ZoneInfo

from ..services import queue_ops, settings_service as cfg
from ..services.org_templates import TEMPLATES

router = APIRouter(prefix="/admin", tags=["admin"])


def _finish(db: Session, bg: BackgroundTasks, outbox: Outbox) -> None:
    qe.refresh(db, outbox)
    db.commit()
    bg.add_task(flush_outbox, outbox)


# -------------------------------------------------------------------- queue
@router.get("/queue")
def admin_queue(service_id: int | None = None, status: str | None = None, active_only: bool = True,
                page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200),
                db: Session = Depends(get_db), _: User = Depends(staff_user)):
    loc = cfg.get_location(db)
    q = (select(QueueToken).join(Service, Service.service_id == QueueToken.service_id)
         .options(selectinload(QueueToken.user), selectinload(QueueToken.service), selectinload(QueueToken.counter)))
    cond = [Service.location_id == loc.location_id]
    if service_id:
        cond.append(QueueToken.service_id == service_id)
    if status:
        try:
            cond.append(QueueToken.status.in_([TokenStatus(s) for s in status.split(",")]))
        except ValueError:
            raise HTTPException(422, "Unknown status filter")
    elif active_only:
        cond.append(QueueToken.status.in_(ACTIVE_STATUSES))
    for c in cond:
        q = q.where(c)
    total = db.scalar(select(func.count()).select_from(q.subquery()))
    rows = list(db.scalars(q.order_by(QueueToken.created_at, QueueToken.token_id).offset((page - 1) * page_size).limit(page_size)))
    snap = qe.build_snapshot(db)
    est = qe.estimate_all(snap)
    now = utcnow()
    items = []
    for t in rows:
        e = est.get(t.token_id)
        items.append({
            "token_id": t.token_id, "token_label": t.token_label, "customer_name": t.user.name, "service_id": t.service_id,
            "service_name": t.service.service_name, "status": t.status.value, "priority_type": t.priority_type.value,
            "queue_position": e.features["customers_ahead"] + 1 if e and t.status in WAITING_STATUSES else None,
            "counter_id": t.counter_id, "counter_name": t.counter.counter_name if t.counter else None,
            "waited_minutes": round((now - t.created_at).total_seconds() / 60, 1), "arrived": t.arrival_time is not None,
            "estimate": e.as_dict() if e and t.status in WAITING_STATUSES else None, "created_at": t.created_at})
    return {"items": items, "total": total, "page": page, "page_size": page_size}


def _token(db: Session, token_id: int) -> QueueToken:
    return queue_ops.get_token_or_404(db, token_id)


@router.get("/queue/{token_id}/events")
def token_events(token_id: int, db: Session = Depends(get_db), _: User = Depends(staff_user)):
    """Append-only event history of one token (timeline in the live-queue side panel)."""
    _token(db, token_id)
    rows = db.scalars(select(QueueEvent).where(QueueEvent.token_id == token_id).order_by(QueueEvent.event_id)).all()
    return {"events": [{"event_id": e.event_id, "event_type": e.event_type, "timestamp": e.timestamp, "metadata": e.metadata_} for e in rows]}


@router.post("/queue/call-next")
def call_next(body: CallNextIn, bg: BackgroundTasks, db: Session = Depends(get_db), user: User = Depends(staff_user)):
    outbox = Outbox()
    token = queue_ops.call_next(db, outbox, user, body.counter_id)
    _finish(db, bg, outbox)
    return {"token_id": token.token_id, "token_label": token.token_label, "status": "called"}


@router.post("/queue/{token_id}/call")
def call(token_id: int, bg: BackgroundTasks, body: CallIn | None = None, db: Session = Depends(get_db), user: User = Depends(staff_user)):
    outbox, body = Outbox(), body or CallIn()
    queue_ops.call_token(db, outbox, user, _token(db, token_id), body.counter_id, body.override_reason)
    _finish(db, bg, outbox)
    return {"ok": True}


@router.post("/queue/{token_id}/start")
def start(token_id: int, bg: BackgroundTasks, db: Session = Depends(get_db), user: User = Depends(staff_user)):
    outbox = Outbox()
    queue_ops.start_service(db, user, _token(db, token_id))
    _finish(db, bg, outbox)
    return {"ok": True}


@router.post("/queue/{token_id}/complete")
def complete(token_id: int, bg: BackgroundTasks, db: Session = Depends(get_db), user: User = Depends(staff_user)):
    outbox = Outbox()
    queue_ops.complete_service(db, user, _token(db, token_id))
    _finish(db, bg, outbox)
    return {"ok": True}


@router.post("/queue/{token_id}/no-show")
def no_show(token_id: int, bg: BackgroundTasks, db: Session = Depends(get_db), user: User = Depends(staff_user)):
    outbox = Outbox()
    queue_ops.mark_no_show(db, outbox, user, _token(db, token_id))
    _finish(db, bg, outbox)
    return {"ok": True}


@router.post("/queue/{token_id}/cancel")
def staff_cancel(token_id: int, bg: BackgroundTasks, body: ReasonIn | None = None, db: Session = Depends(get_db), user: User = Depends(staff_user)):
    outbox = Outbox()
    queue_ops.cancel_token(db, outbox, _token(db, token_id), user, (body.reason if body else None))
    _finish(db, bg, outbox)
    return {"ok": True}


@router.patch("/queue/{token_id}")
def patch_token(token_id: int, body: TokenPatchIn, bg: BackgroundTasks, db: Session = Depends(get_db), user: User = Depends(staff_user)):
    outbox = Outbox()
    queue_ops.patch_token(db, user, _token(db, token_id), body.priority_type, body.reason)
    _finish(db, bg, outbox)
    return {"ok": True}


# ----------------------------------------------------------------- counters
def _counter_out(db: Session, c: Counter, served: dict[int, int], current: dict[int, str]) -> dict:
    return {"counter_id": c.counter_id, "counter_name": c.counter_name, "status": c.status, "assigned_staff_id": c.assigned_staff_id,
            "staff_name": c.staff.user.name if c.staff else None, "service_ids": c.service_ids, "busy": c.counter_id in current,
            "current_token": current.get(c.counter_id), "served_today": served.get(c.counter_id, 0)}


@router.get("/counters", response_model=list[CounterOut])
def list_counters(db: Session = Depends(get_db), _: User = Depends(staff_user)):
    loc = cfg.get_location(db)
    today = cfg.local_today(loc)
    from ..services.analytics import day_bounds
    start, end = day_bounds(loc, today)
    served = dict(db.execute(select(ServiceRecord.counter_id, func.count()).where(
        ServiceRecord.service_start_time >= start, ServiceRecord.service_start_time < end).group_by(ServiceRecord.counter_id)).all())
    current = {t.counter_id: t.token_label for t in db.scalars(select(QueueToken).where(
        QueueToken.status.in_([TokenStatus.called, TokenStatus.serving]), QueueToken.counter_id.is_not(None)))}
    counters = db.scalars(select(Counter).where(Counter.location_id == loc.location_id).order_by(Counter.counter_id)
                          .options(selectinload(Counter.service_links), selectinload(Counter.staff).selectinload(Staff.user))).all()
    return [_counter_out(db, c, served, current) for c in counters]


def _apply_services(db: Session, c: Counter, service_ids: list[int]) -> None:
    valid = set(db.scalars(select(Service.service_id).where(Service.service_id.in_(service_ids), Service.location_id == c.location_id)))
    if valid != set(service_ids):
        raise HTTPException(422, "Unknown service id (services must belong to the counter's organization)")
    c.service_links = [CounterService(counter_id=c.counter_id, service_id=s) for s in service_ids]


@router.post("/counters", response_model=CounterOut, status_code=201)
def create_counter(body: CounterIn, bg: BackgroundTasks, db: Session = Depends(get_db), user: User = Depends(admin_user)):
    loc = cfg.get_location(db)
    c = Counter(location_id=loc.location_id, counter_name=body.counter_name.strip(), status=body.status, assigned_staff_id=body.assigned_staff_id)
    db.add(c)
    try:
        db.flush()
        _apply_services(db, c, body.service_ids)
        queue_ops.audit(db, user, "counter_created", "counter", c.counter_id, name=c.counter_name)
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Counter name or staff assignment conflicts with an existing counter")
    _finish(db, bg, Outbox())
    db.refresh(c)
    return _counter_out(db, c, {}, {})


@router.patch("/counters/{counter_id}", response_model=CounterOut)
def patch_counter(counter_id: int, body: CounterPatch, bg: BackgroundTasks, db: Session = Depends(get_db), user: User = Depends(admin_user)):
    c = db.scalar(select(Counter).where(Counter.counter_id == counter_id).options(selectinload(Counter.service_links)))
    if not c:
        raise HTTPException(404, "Counter not found")
    cfg.set_location(db, c.location_id)
    changes = {}
    if body.counter_name is not None:
        changes["counter_name"] = (c.counter_name, body.counter_name); c.counter_name = body.counter_name.strip()
    if body.status is not None and body.status != c.status:
        changes["status"] = (c.status.value, body.status.value)
        if body.status != CounterStatus.open and db.scalar(select(func.count(QueueToken.token_id)).where(
                QueueToken.counter_id == c.counter_id, QueueToken.status.in_([TokenStatus.called, TokenStatus.serving]))):
            raise HTTPException(409, "Finish or reassign the customer currently at this counter first.")
        c.status = body.status
    if body.unassign_staff:
        changes["assigned_staff_id"] = (c.assigned_staff_id, None); c.assigned_staff_id = None
    elif body.assigned_staff_id is not None:
        st = db.get(Staff, body.assigned_staff_id)
        if not st or (st.location_id and st.location_id != c.location_id):
            raise HTTPException(422, "Unknown staff id (staff must belong to the counter's organization)")
        changes["assigned_staff_id"] = (c.assigned_staff_id, body.assigned_staff_id); c.assigned_staff_id = body.assigned_staff_id
    if body.service_ids is not None:
        changes["service_ids"] = (c.service_ids, body.service_ids)
        _apply_services(db, c, body.service_ids)
    try:
        queue_ops.audit(db, user, "counter_updated", "counter", c.counter_id, changes={k: [str(a), str(b)] for k, (a, b) in changes.items()})
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "That staff member is already assigned to another counter")
    _finish(db, bg, Outbox())
    return next(x for x in list_counters(db, user) if x["counter_id"] == counter_id)


# -------------------------------------------------------------------- staff
@router.get("/staff")
def list_staff(db: Session = Depends(get_db), _: User = Depends(staff_user)):
    loc = cfg.get_location(db)
    counters = {c.assigned_staff_id: c for c in db.scalars(select(Counter).where(Counter.location_id == loc.location_id)) if c.assigned_staff_id}
    return [{"staff_id": s.staff_id, "user_id": s.user_id, "name": s.user.name, "email": s.user.email, "availability": s.availability.value,
             "assigned_counter_id": counters[s.staff_id].counter_id if s.staff_id in counters else None,
             "assigned_counter": counters[s.staff_id].counter_name if s.staff_id in counters else None}
            for s in db.scalars(select(Staff).where(Staff.location_id == loc.location_id).options(selectinload(Staff.user)).order_by(Staff.staff_id))]


@router.post("/staff", status_code=201)
def create_staff(body: StaffIn, db: Session = Depends(get_db), admin: User = Depends(admin_user)):
    if db.scalar(select(User.user_id).where(func.lower(User.email) == body.email.lower())):
        raise HTTPException(409, "Email already registered")
    u = User(name=body.name.strip(), email=body.email.lower(), password_hash=hash_password(body.password), role=Role.staff)
    db.add(u); db.flush()
    s = Staff(user_id=u.user_id, location_id=cfg.get_location(db).location_id); db.add(s); db.flush()
    queue_ops.audit(db, admin, "staff_created", "staff", s.staff_id, email=u.email)
    db.commit()
    return {"staff_id": s.staff_id, "user_id": u.user_id}


@router.patch("/staff/{staff_id}")
def patch_staff(staff_id: int, body: StaffPatch, bg: BackgroundTasks, db: Session = Depends(get_db), admin: User = Depends(admin_user)):
    s = db.get(Staff, staff_id)
    if not s:
        raise HTTPException(404, "Staff not found")
    cfg.set_location(db, s.location_id)
    old, s.availability = s.availability, body.availability
    queue_ops.audit(db, admin, "staff_availability", "staff", staff_id, old=old.value, new=body.availability.value)
    _finish(db, bg, Outbox())          # availability changes wait estimates
    return {"ok": True}


# ----------------------------------------------------------------- services
@router.get("/services", response_model=list[ServiceOut])
def list_all_services(db: Session = Depends(get_db), _: User = Depends(staff_user)):
    """Every service of the active organization, including paused/archived ones (customers only see active)."""
    loc = cfg.get_location(db)
    return db.scalars(select(Service).where(Service.location_id == loc.location_id).order_by(Service.service_id)).all()


@router.post("/services", response_model=ServiceOut, status_code=201)
def create_service(body: ServiceIn, db: Session = Depends(get_db), admin: User = Depends(admin_user)):
    svc = Service(location_id=cfg.get_location(db).location_id, service_name=body.service_name.strip(), code=body.code.upper(),
                  description=body.description, average_service_duration=body.average_service_duration, status=ServiceStatus.active)
    db.add(svc)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "A service with this name or code already exists in this organization")
    queue_ops.audit(db, admin, "service_created", "service", svc.service_id, name=svc.service_name, location_id=svc.location_id)
    db.commit()
    return svc


@router.patch("/services/{service_id}", response_model=ServiceOut)
def patch_service(service_id: int, body: ServicePatch, bg: BackgroundTasks, db: Session = Depends(get_db), admin: User = Depends(admin_user)):
    svc = db.get(Service, service_id)
    if not svc:
        raise HTTPException(404, "Service not found")
    cfg.set_location(db, svc.location_id)
    changes = {}
    for field in ("service_name", "description", "average_service_duration", "status"):
        v = getattr(body, field)
        if v is not None and v != getattr(svc, field):
            changes[field] = [str(getattr(svc, field)), str(v)]
            setattr(svc, field, v.strip() if isinstance(v, str) else v)
    try:
        queue_ops.audit(db, admin, "service_updated", "service", svc.service_id, changes=changes)
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "A service with this name already exists in this organization")
    _finish(db, bg, Outbox())
    return svc


# ------------------------------------------------------------ organizations
def _validate_tz(tz: str) -> None:
    try:
        ZoneInfo(tz)
    except Exception:
        raise HTTPException(422, f"Unknown timezone: {tz}")


def _location_out(db: Session, l: Location) -> dict:
    settings = cfg.get_settings_map(db, l.location_id)
    n_services = db.scalar(select(func.count(Service.service_id)).where(Service.location_id == l.location_id, Service.status == ServiceStatus.active)) or 0
    n_counters = db.scalar(select(func.count(Counter.counter_id)).where(Counter.location_id == l.location_id)) or 0
    n_staff = db.scalar(select(func.count(Staff.staff_id)).where(Staff.location_id == l.location_id)) or 0
    waiting = db.scalar(select(func.count(QueueToken.token_id)).join(Service, Service.service_id == QueueToken.service_id).where(
        Service.location_id == l.location_id, QueueToken.status.in_(WAITING_STATUSES))) or 0
    return {"location_id": l.location_id, "name": l.name, "location_type": l.location_type,
            "type_label": TEMPLATES.get(l.location_type, TEMPLATES["other"])["label"], "address": l.address, "timezone": l.timezone,
            "is_active": l.is_active, "open_time": settings["open_time"], "close_time": settings["close_time"],
            "services": n_services, "counters": n_counters, "staff": n_staff, "waiting": waiting}


@router.get("/location-templates")
def location_templates(_: User = Depends(admin_user)):
    """What 'start with typical services' will create for each organization type (all editable afterwards)."""
    return {k: {"label": v["label"], "open_time": v["hours"][0], "close_time": v["hours"][1], "counters": v["counters"],
                "services": [{"service_name": n, "code": c, "description": d, "average_service_duration": m} for n, c, d, m in v["services"]]}
            for k, v in TEMPLATES.items()}


@router.get("/locations")
def admin_locations(db: Session = Depends(get_db), user: User = Depends(staff_user)):
    q = select(Location).order_by(Location.location_id)
    restrict = db.info.get("restrict_location")
    if restrict:                      # staff only see the organization they work at
        q = q.where(Location.location_id == restrict)
    return [_location_out(db, l) for l in db.scalars(q)]


@router.post("/locations", status_code=201)
def create_location(body: LocationIn, db: Session = Depends(get_db), admin: User = Depends(admin_user)):
    _validate_tz(body.timezone)
    tpl = TEMPLATES[body.location_type]
    open_t, close_t = body.open_time or tpl["hours"][0], body.close_time or tpl["hours"][1]
    if open_t >= close_t:
        raise HTTPException(422, "Opening time must be before closing time")
    if db.scalar(select(Location.location_id).where(func.lower(Location.name) == body.name.strip().lower())):
        raise HTTPException(409, "An organization with this name already exists")
    loc = Location(name=body.name.strip(), location_type=body.location_type, address=body.address, timezone=body.timezone, is_active=True)
    db.add(loc)
    db.flush()
    cfg.set_location(db, loc.location_id)
    cfg.update_settings(db, {"open_time": open_t, "close_time": close_t}, admin.user_id)
    created = {"services": 0, "counters": 0}
    if body.use_template:
        svcs = []
        for name, code, desc, minutes in tpl["services"]:
            sv = Service(location_id=loc.location_id, service_name=name, code=code, description=desc, average_service_duration=minutes)
            db.add(sv)
            svcs.append(sv)
        db.flush()
        n = len(svcs)
        for i in range(tpl["counters"]):
            c = Counter(location_id=loc.location_id, counter_name=f"Counter {i + 1}", status=CounterStatus.closed)
            db.add(c)
            db.flush()
            # each counter handles two neighbouring services so work can be shared between counters
            picks = sorted({svcs[i % n].service_id, svcs[(i + 1) % n].service_id})
            c.service_links = [CounterService(counter_id=c.counter_id, service_id=s) for s in picks]
        created = {"services": n, "counters": tpl["counters"]}
    queue_ops.audit(db, admin, "location_created", "location", loc.location_id, name=loc.name, type=loc.location_type, template=body.use_template)
    db.commit()
    return {**_location_out(db, loc), "created": created}


@router.patch("/locations/{location_id}")
def patch_location(location_id: int, body: LocationPatch, db: Session = Depends(get_db), admin: User = Depends(admin_user)):
    loc = db.get(Location, location_id)
    if not loc:
        raise HTTPException(404, "Organization not found")
    if body.is_active is False and loc.is_active and db.scalar(select(func.count(Location.location_id)).where(Location.is_active.is_(True))) <= 1:
        raise HTTPException(409, "At least one organization must stay active.")
    changes = {}
    for field in ("name", "location_type", "address", "timezone", "is_active"):
        v = getattr(body, field)
        if v is not None and v != getattr(loc, field):
            if field == "timezone":
                _validate_tz(v)
            changes[field] = [str(getattr(loc, field)), str(v)]
            setattr(loc, field, v.strip() if isinstance(v, str) else v)
    hours = {k: v for k, v in (("open_time", body.open_time), ("close_time", body.close_time)) if v}
    if hours:
        cfg.set_location(db, loc.location_id)
        merged = {**cfg.get_settings_map(db, loc.location_id), **hours}
        if merged["open_time"] >= merged["close_time"]:
            raise HTTPException(422, "Opening time must be before closing time")
        cfg.update_settings(db, hours, admin.user_id)
        changes["hours"] = [str(h) for h in hours.values()]
    try:
        queue_ops.audit(db, admin, "location_updated", "location", loc.location_id, changes=changes)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "An organization with this name already exists")
    return _location_out(db, loc)


# ------------------------------------------------- settings / audit / advice
@router.get("/settings")
def get_settings_(db: Session = Depends(get_db), _: User = Depends(staff_user)):
    return {"settings": cfg.get_settings_map(db), "defaults": cfg.DEFAULTS}


@router.patch("/settings")
def patch_settings(body: SettingsPatch, db: Session = Depends(get_db), admin: User = Depends(admin_user)):
    try:
        new = cfg.update_settings(db, body.values, admin.user_id)
    except ValueError as e:
        raise HTTPException(422, str(e))
    queue_ops.audit(db, admin, "settings_changed", "settings", None, values=body.values)
    db.commit()
    return {"settings": new}


@router.get("/audit")
def audit_log(page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200), db: Session = Depends(get_db), _: User = Depends(admin_user)):
    total = db.scalar(select(func.count(AuditLog.audit_id)))
    rows = db.scalars(select(AuditLog).order_by(AuditLog.audit_id.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    names = {u.user_id: u.name for u in db.scalars(select(User).where(User.user_id.in_({r.actor_user_id for r in rows if r.actor_user_id})))}
    return {"total": total, "page": page, "page_size": page_size, "items": [
        {"audit_id": r.audit_id, "actor": names.get(r.actor_user_id), "action": r.action, "entity_type": r.entity_type,
         "entity_id": r.entity_id, "details": r.details, "created_at": r.created_at} for r in rows]}


@router.get("/alerts")
def alerts(db: Session = Depends(get_db), _: User = Depends(staff_user)):
    snap = qe.build_snapshot(db)
    return {"alerts": optimizer.evaluate(db, snap), "thresholds": {k: snap.settings[k] for k in (
        "congestion_queue_length", "wait_threshold_minutes", "rapid_growth_delta", "capacity_alert_ratio")}}


@router.get("/recommendations")
def recommendations(db: Session = Depends(get_db), _: User = Depends(staff_user)):
    return {"recommendations": optimizer.recommend_allocation(db),
            "note": "Recommendations only. Apply them from the Counters page; every change is audited."}
