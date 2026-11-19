"""Rule-based optimization engine (separate from ML — PRD §7).

ML predicts; this module decides what to RECOMMEND. Thresholds come from admin-editable location settings.
Nothing here changes the system: every recommendation carries an `action` payload the admin may apply via the
normal counter endpoints, so humans stay in control and every change is audited there.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import CounterStatus, QueueEvent, QueueToken, Service, Staff, StaffAvailability
from ..services import demand_service
from . import queue_engine as qe

SEVERITY_ORDER = {"critical": 0, "warning": 1, "info": 2}


def _closed_counters_for(snap: qe.Snapshot, service_id: int):
    return [c for c in snap.counters if c.status != CounterStatus.open and service_id in c.service_ids]


def _open_action(c) -> dict:
    return {"type": "open_counter", "counter_id": c.counter_id, "label": f"Open {c.counter_name}"}


def evaluate(db: Session, snap: qe.Snapshot | None = None, service_id: int | None = None) -> list[dict]:
    snap = snap or qe.build_snapshot(db)
    s = snap.settings
    alerts: list[dict] = []
    est_all = qe.estimate_all(snap)
    waiting_by_service: dict[int, int] = defaultdict(int)
    for t in snap.waiting:
        waiting_by_service[t.service_id] += 1

    now = snap.now
    loc_id = snap.loc.location_id
    arrivals15 = db.scalar(select(func.count(QueueToken.token_id)).join(Service, Service.service_id == QueueToken.service_id).where(
        QueueToken.created_at >= now - timedelta(minutes=15), Service.location_id == loc_id)) or 0
    started15 = db.scalar(select(func.count(QueueEvent.event_id)).join(QueueToken, QueueToken.token_id == QueueEvent.token_id)
                          .join(Service, Service.service_id == QueueToken.service_id).where(
        QueueEvent.event_type == "called", QueueEvent.timestamp >= now - timedelta(minutes=15), Service.location_id == loc_id)) or 0

    for sid, svc in snap.services.items():
        if service_id and sid != service_id:
            continue
        active = [c for c in snap.counter_states if c.available and sid in c.service_ids]
        qlen = waiting_by_service.get(sid, 0)
        base = {"service_id": sid, "service_name": svc.service_name}

        if qlen > 0 and not active:
            closed = _closed_counters_for(snap, sid)
            alerts.append({**base, "severity": "critical", "type": "no_counter_available",
                           "message": f"{qlen} customer(s) waiting for {svc.service_name} but no eligible counter is open.",
                           "recommendation": f"Open {closed[0].counter_name}." if closed else "Add this service to an open counter.",
                           "action": _open_action(closed[0]) if closed else None})
        if qlen > s["congestion_queue_length"]:
            closed = _closed_counters_for(snap, sid)
            alerts.append({**base, "severity": "critical", "type": "queue_congestion",
                           "message": f"{svc.service_name}: {qlen} waiting (threshold {s['congestion_queue_length']}).",
                           "recommendation": f"Open {closed[0].counter_name} to clear the backlog." if closed else
                           "No closed counter supports this service; consider redistributing workload.",
                           "action": _open_action(closed[0]) if closed else None})
        if active or qlen:
            new_est = qe.estimate_new_joiner(snap, sid)
            if new_est.minutes is not None and new_est.minutes > s["wait_threshold_minutes"]:
                closed = _closed_counters_for(snap, sid)
                alerts.append({**base, "severity": "warning", "type": "long_wait",
                               "message": f"{svc.service_name}: a new customer would wait ~{new_est.minutes:.0f} min "
                                          f"(threshold {s['wait_threshold_minutes']}).",
                               "recommendation": f"Open {closed[0].counter_name}." if closed else "Consider pausing walk-in joins or redistributing workload.",
                               "action": _open_action(closed[0]) if closed else None})

        # predicted demand vs capacity (next 60 minutes)
        fc = demand_service.forecast_service(db, svc, persist=True)
        f60 = next(f for f in fc["forecasts"] if f["horizon_minutes"] == 60)
        workload = (qlen + f60["predicted_arrivals"]) * snap.avg_service.get(sid, 8.0)
        capacity = max(len(active), 0) * 60.0
        if workload > 0 and (capacity == 0 or workload / capacity > s["capacity_alert_ratio"]) and f60["predicted_arrivals"] >= 1:
            closed = _closed_counters_for(snap, sid)
            alerts.append({**base, "severity": "warning", "type": "demand_exceeds_capacity",
                           "message": f"{svc.service_name}: ~{f60['predicted_arrivals']:.0f} arrivals expected in the next hour "
                                      f"({f60['method'].upper()}); workload ≈ {workload:.0f} counter-min vs capacity {capacity:.0f}.",
                           "recommendation": f"Prepare to open {closed[0].counter_name} before the surge." if closed else "Prepare staff to redistribute workload.",
                           "action": _open_action(closed[0]) if closed else None})

    if not service_id and arrivals15 - started15 >= s["rapid_growth_delta"]:
        alerts.append({"service_id": None, "service_name": "All services", "severity": "warning", "type": "rapid_growth",
                       "message": f"Queue grew by {arrivals15 - started15} in the last 15 minutes ({arrivals15} joined, {started15} called).",
                       "recommendation": "Check counter availability and consider opening another counter.", "action": None})

    for c in snap.counters:
        if c.status == CounterStatus.unavailable and (not service_id or service_id in c.service_ids):
            alerts.append({"service_id": None, "service_name": c.counter_name, "severity": "warning", "type": "counter_unavailable",
                           "message": f"{c.counter_name} is unavailable; wait estimates were recalculated without it.",
                           "recommendation": "Reassign its staff or reopen the counter when ready.", "action": None})
    alerts.sort(key=lambda a: SEVERITY_ORDER[a["severity"]])
    return alerts


def recommend_allocation(db: Session, snap: qe.Snapshot | None = None) -> list[dict]:
    """Greedy, transparent counter/staff allocation.

    1. load_s   = (waiting_s + predicted 60-min arrivals_s) * avg_service_s   [counter-minutes needed this hour]
    2. cap_s    = sum over open counters supporting s of 60 / (number of services that counter supports with load>0)
    3. deficit services (load/cap > target) are served first, worst first:
         a. open a closed counter that supports the most deficit services
         b. else add the deficit service to an open counter whose services are all under 50% load (redistribution)
    """
    snap = snap or qe.build_snapshot(db)
    target = float(snap.settings["target_utilization"])
    load: dict[int, float] = {}
    for sid, svc in snap.services.items():
        waiting = sum(1 for t in snap.waiting if t.service_id == sid)
        f60 = next(f for f in demand_service.forecast_service(db, svc, persist=False)["forecasts"] if f["horizon_minutes"] == 60)
        load[sid] = (waiting + f60["predicted_arrivals"]) * snap.avg_service.get(sid, 8.0)

    def capacity(counter_set) -> dict[int, float]:
        cap: dict[int, float] = defaultdict(float)
        for c in counter_set:
            served = [x for x in c.service_ids if load.get(x, 0) > 0] or list(c.service_ids)
            for x in served:
                cap[x] += 60.0 / max(len(served), 1)
        return cap

    open_counters = [c for c in snap.counters if qe.counter_available(c)]
    cap = capacity(open_counters)
    ratio = {sid: (load[sid] / cap[sid] if cap.get(sid) else (float("inf") if load[sid] > 0 else 0.0)) for sid in snap.services}
    deficit = sorted([sid for sid, r in ratio.items() if r > target], key=lambda x: -ratio[x])
    recs: list[dict] = []
    used: set[int] = set()
    free_staff = db.scalars(select(Staff).where(Staff.availability == StaffAvailability.available,
                                                Staff.location_id == snap.loc.location_id)).all()
    assigned_ids = {c.assigned_staff_id for c in snap.counters if c.assigned_staff_id}
    spare_staff = [st for st in free_staff if st.staff_id not in assigned_ids]

    for sid in deficit:
        name = snap.services[sid].service_name
        r = ratio[sid]
        rtxt = "unserved" if r == float("inf") else f"{r:.0%} of capacity"
        closed = [c for c in _closed_counters_for(snap, sid) if c.counter_id not in used]
        if closed:
            best = max(closed, key=lambda c: sum(1 for x in c.service_ids if x in deficit))
            used.add(best.counter_id)
            has_staff = best.assigned_staff_id is not None or bool(spare_staff)
            recs.append({"priority": "high", "service_id": sid, "title": f"Open {best.counter_name}",
                         "rationale": f"{name} workload is {rtxt} for the next hour." + ("" if has_staff else " No staff is assigned yet — assign someone first."),
                         "action": _open_action(best)})
            continue
        donors = [c for c in open_counters if sid not in c.service_ids and c.counter_id not in used
                  and all(ratio.get(x, 0) < 0.5 for x in c.service_ids)]
        if donors:
            d = donors[0]
            used.add(d.counter_id)
            recs.append({"priority": "medium", "service_id": sid, "title": f"Let {d.counter_name} also serve {name}",
                         "rationale": f"{name} is at {rtxt}; {d.counter_name}'s current services are under 50% load.",
                         "action": {"type": "add_service", "counter_id": d.counter_id, "service_id": sid,
                                    "service_ids": sorted(set(d.service_ids) | {sid}), "label": f"Add {name} to {d.counter_name}"}})
        else:
            recs.append({"priority": "medium", "service_id": sid, "title": f"{name} is over capacity",
                         "rationale": f"At {rtxt} and no spare counter or donor is available. Consider extending hours or asking staff to prioritise short transactions.",
                         "action": None})
    if not deficit and snap.counters:
        under = [snap.services[s].service_name for s, r in ratio.items() if r < 0.3 and load[s] > 0]
        if under and len(open_counters) > 2:
            recs.append({"priority": "low", "service_id": None, "title": "Capacity is comfortable",
                         "rationale": f"Predicted demand is well below capacity ({', '.join(under)}). A counter could be closed for a break.", "action": None})
    return recs
