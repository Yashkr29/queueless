"""Transactional queue operations (join / cancel / call / serve ...). Routers stay thin; every mutation
writes an append-only QueueEvent, and staff actions additionally write an AuditLog row."""
from datetime import datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..engine import queue_engine as qe
from ..models import (
    ACTIVE_STATUSES, PRIORITY_RANK, WAITING_STATUSES, AuditLog, Counter, Priority, QueueEvent, QueueToken, Service, ServiceRecord,
    ServiceStatus, Staff, TokenStatus, User, utcnow,
)
from ..realtime import Outbox
from ..services import settings_service as cfg
from ..services.notifications import notify

log_event = qe.log_event


def audit(db: Session, actor: User | None, action: str, entity_type: str, entity_id: int | None, **details) -> None:
    db.add(AuditLog(actor_user_id=actor.user_id if actor else None, action=action, entity_type=entity_type,
                    entity_id=entity_id, details=details))


def get_token_or_404(db: Session, token_id: int) -> QueueToken:
    t = db.get(QueueToken, token_id)
    if not t:
        raise HTTPException(404, "Token not found")
    cfg.set_location(db, t.service.location_id)           # operate inside the token's organization
    restrict = db.info.get("restrict_location")           # staff are pinned to the organization they work at
    if restrict and t.service.location_id != restrict:
        raise HTTPException(404, "Token not found")
    return t


def _conflict(msg: str) -> HTTPException:
    return HTTPException(status.HTTP_409_CONFLICT, msg)


# ------------------------------------------------------------------ customer
def join_queue(db: Session, outbox: Outbox, user: User, service_id: int, priority: Priority) -> QueueToken:
    service = db.execute(select(Service).where(Service.service_id == service_id).with_for_update()).scalar_one_or_none()
    if not service or service.status != ServiceStatus.active:
        raise HTTPException(404, "Service not found or not accepting customers")
    cfg.set_location(db, service.location_id)            # everything below happens inside the service's organization
    loc = cfg.get_location(db)
    if not loc.is_active:
        raise HTTPException(400, f"{loc.name} is not accepting queues right now.")
    settings = cfg.get_settings_map(db, loc.location_id)
    local = cfg.local_now(loc)
    if settings["enforce_operating_hours"]:
        hhmm = local.strftime("%H:%M")
        if not (settings["open_time"] <= hhmm < settings["close_time"]):
            raise HTTPException(400, f"The service centre is closed. Opening hours {settings['open_time']}–{settings['close_time']}.")

    def has_active() -> bool:
        return db.scalar(select(func.count(QueueToken.token_id)).where(
            QueueToken.user_id == user.user_id, QueueToken.service_id == service_id, QueueToken.status.in_(ACTIVE_STATUSES))) > 0

    if has_active():
        raise _conflict("You already have an active token for this service.")

    last_ns = db.scalar(select(QueueEvent.timestamp).join(QueueToken, QueueToken.token_id == QueueEvent.token_id).where(
        QueueToken.user_id == user.user_id, QueueToken.service_id == service_id, QueueEvent.event_type == "no_show")
        .order_by(QueueEvent.event_id.desc()).limit(1))
    cooldown = float(settings["rejoin_cooldown_minutes"])
    if last_ns and utcnow() - last_ns < timedelta(minutes=cooldown):
        mins = int(cooldown - (utcnow() - last_ns).total_seconds() / 60) + 1
        raise _conflict(f"You missed your last turn for this service. You can rejoin in about {mins} min.")

    today = local.date()
    token = None
    for _ in range(4):                      # retry on a (service, date, number) race
        try:
            with db.begin_nested():
                n = (db.scalar(select(func.max(QueueToken.token_number)).where(
                    QueueToken.service_id == service_id, QueueToken.queue_date == today)) or 0) + 1
                token = QueueToken(user_id=user.user_id, service_id=service_id, queue_date=today, token_number=n,
                                   token_label=f"{service.code}-{n:03d}", priority_type=priority, status=TokenStatus.booked,
                                   is_demo=False, created_at=utcnow())
                db.add(token)
                db.flush()
            break
        except IntegrityError:
            token = None
            if has_active():
                raise _conflict("You already have an active token for this service.")
    if token is None:
        raise _conflict("Could not allocate a token number, please try again.")

    log_event(db, token, "token_created", user.user_id, priority=priority.value)
    notify(db, outbox, user.user_id, "token_generated", f"Token {token.token_label} generated",
           f"You joined the {service.service_name} queue. We'll update your arrival window as the queue moves.", token.token_id)
    return token


def _ensure_owner_or_staff(token: QueueToken, user: User) -> None:
    if token.user_id != user.user_id and user.role.value == "customer":
        raise HTTPException(403, "This token belongs to another customer")


def cancel_token(db: Session, outbox: Outbox, token: QueueToken, actor: User, reason: str | None = None) -> None:
    _ensure_owner_or_staff(token, actor)
    if token.status not in ACTIVE_STATUSES or token.status == TokenStatus.serving:
        raise _conflict(f"A token in status '{token.status.value}' cannot be cancelled.")
    by_staff = actor.user_id != token.user_id
    token.status, token.queue_position, token.counter_id = TokenStatus.cancelled, None, None
    log_event(db, token, "cancelled", actor.user_id, by="staff" if by_staff else "customer", reason=reason)
    if by_staff:
        audit(db, actor, "token_cancelled", "queue_token", token.token_id, reason=reason)
    notify(db, outbox, token.user_id, "cancellation", f"Token {token.token_label} cancelled",
           "Your token has been cancelled." + (" You can rejoin at any time." if not by_staff else " Please contact the desk if this is unexpected."),
           token.token_id)
    outbox.to_user(token.user_id, {"type": "token_update", "token": {"token_id": token.token_id, "status": "cancelled"}})


def confirm_arrival(db: Session, token: QueueToken, user: User, mode: str) -> None:
    _ensure_owner_or_staff(token, user)
    if token.status not in WAITING_STATUSES:
        raise _conflict(f"A token in status '{token.status.value}' cannot be updated.")
    if mode == "on_my_way":
        if token.status == TokenStatus.booked:
            token.status = TokenStatus.confirmed
        log_event(db, token, "confirmed_on_my_way", user.user_id)
    else:
        token.arrival_time = utcnow()
        if token.status in (TokenStatus.booked, TokenStatus.confirmed):
            token.status = TokenStatus.waiting
        log_event(db, token, "arrived", user.user_id)


# --------------------------------------------------------------------- staff
def _staff_counter_for(db: Session, user: User) -> Counter | None:
    staff = db.scalar(select(Staff).where(Staff.user_id == user.user_id))
    if not staff:
        return None
    return db.scalar(select(Counter).where(Counter.assigned_staff_id == staff.staff_id))


def head_of_line(snap: qe.Snapshot, counter: Counter) -> QueueToken | None:
    supported = set(counter.service_ids)
    cands = [t for t in snap.waiting if t.service_id in supported]
    return min(cands, key=lambda t: (PRIORITY_RANK[t.priority_type], t.created_at, t.token_id), default=None)


def _validated_counter(db: Session, snap: qe.Snapshot, counter_id: int, token: QueueToken | None) -> Counter:
    counter = next((c for c in snap.counters if c.counter_id == counter_id), None)
    if not counter:
        raise HTTPException(404, "Counter not found")
    if not qe.counter_available(counter):
        raise _conflict(f"{counter.counter_name} is not open / staffed.")
    if counter.counter_id in snap.busy_counter_ids:
        raise _conflict(f"{counter.counter_name} is already serving a customer.")
    if token is not None and token.service_id not in counter.service_ids:
        raise _conflict(f"{counter.counter_name} does not support this service.")
    return counter


def call_token(db: Session, outbox: Outbox, actor: User, token: QueueToken, counter_id: int | None, override_reason: str | None) -> None:
    if token.status not in WAITING_STATUSES:
        raise _conflict(f"A token in status '{token.status.value}' cannot be called.")
    snap = qe.build_snapshot(db)
    if counter_id is None:
        own = _staff_counter_for(db, actor)
        counter_id = own.counter_id if own else None
    if counter_id is None:   # admin without a counter: pick the first idle eligible counter
        free = [c for c in snap.counters if qe.counter_available(c) and c.counter_id not in snap.busy_counter_ids
                and token.service_id in c.service_ids]
        if not free:
            raise _conflict("No idle counter supports this service.")
        counter_id = free[0].counter_id
    counter = _validated_counter(db, snap, counter_id, token)
    head = head_of_line(snap, counter)
    out_of_order = head is not None and head.token_id != token.token_id
    if out_of_order and not (override_reason and override_reason.strip()):
        raise _conflict(f"Token {head.token_label} is next in line for {counter.counter_name}. Provide an override reason to call out of order.")
    token.status, token.counter_id, token.queue_position = TokenStatus.called, counter.counter_id, None
    log_event(db, token, "called", actor.user_id, counter_id=counter.counter_id, out_of_order=out_of_order)
    audit(db, actor, "call_out_of_order" if out_of_order else "call", "queue_token", token.token_id,
          counter_id=counter.counter_id, reason=override_reason, skipped=head.token_label if out_of_order else None)
    notify(db, outbox, token.user_id, "counter_assigned", f"Please go to {counter.counter_name}",
           f"Token {token.token_label}, it's your turn at {counter.counter_name}.", token.token_id)


def call_next(db: Session, outbox: Outbox, actor: User, counter_id: int) -> QueueToken:
    snap = qe.build_snapshot(db)
    counter = _validated_counter(db, snap, counter_id, None)
    head = head_of_line(snap, counter)
    if not head:
        raise HTTPException(404, "No customers are waiting for this counter's services.")
    call_token(db, outbox, actor, head, counter.counter_id, None)
    return head


def start_service(db: Session, actor: User, token: QueueToken) -> None:
    if token.status != TokenStatus.called:
        raise _conflict("Only a called token can start service.")
    token.status = TokenStatus.serving
    db.add(ServiceRecord(token_id=token.token_id, counter_id=token.counter_id, service_start_time=utcnow()))
    log_event(db, token, "service_started", actor.user_id, counter_id=token.counter_id)


def complete_service(db: Session, actor: User, token: QueueToken) -> None:
    if token.status != TokenStatus.serving:
        raise _conflict("Only a serving token can be completed.")
    rec = db.scalar(select(ServiceRecord).where(ServiceRecord.token_id == token.token_id))
    now = utcnow()
    rec.service_end_time = now
    rec.actual_service_duration = round((now - rec.service_start_time).total_seconds() / 60, 2)
    rec.actual_wait_minutes = round((rec.service_start_time - token.created_at).total_seconds() / 60, 2)
    token.status = TokenStatus.completed
    log_event(db, token, "service_completed", actor.user_id, duration=rec.actual_service_duration)
    qe.clear_caches()


def mark_no_show(db: Session, outbox: Outbox, actor: User, token: QueueToken) -> None:
    if token.status != TokenStatus.called:
        raise _conflict("Only a called token can be marked no-show.")
    token.status, token.counter_id = TokenStatus.no_show, None
    log_event(db, token, "no_show", actor.user_id)
    audit(db, actor, "no_show", "queue_token", token.token_id)
    notify(db, outbox, token.user_id, "no_show", f"Token {token.token_label} missed",
           "You were called but did not arrive. You can rejoin after a short wait.", token.token_id)


def patch_token(db: Session, actor: User, token: QueueToken, priority: Priority | None, reason: str) -> None:
    if token.status not in WAITING_STATUSES:
        raise _conflict("Only waiting tokens can be edited.")
    if priority and priority != token.priority_type:
        old = token.priority_type
        token.priority_type = priority
        log_event(db, token, "priority_changed", actor.user_id, old=old.value, new=priority.value, reason=reason)
        audit(db, actor, "priority_override", "queue_token", token.token_id, old=old.value, new=priority.value, reason=reason)
