"""Location-level configuration (admin-editable thresholds) + small helpers shared across services."""
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Location, LocationSetting

DEFAULTS: dict[str, float | int | str | bool] = {
    "congestion_queue_length": 25,         # alert when waiting tokens exceed this
    "wait_threshold_minutes": 30,          # recommend an extra counter when predicted wait exceeds this
    "rapid_growth_delta": 8,               # alert when the queue grew by this many in 15 minutes
    "approaching_ahead": 3,                # "approaching turn" when this many or fewer are ahead
    "arrival_buffer_minutes": 15,          # safety buffer for arrival-window recommendations
    "delay_notify_minutes": 10,            # tell the customer when their ETA slips by this much
    "rejoin_cooldown_minutes": 15,         # no-show customers wait this long before rejoining the same service
    "capacity_alert_ratio": 1.0,           # predicted workload / capacity above which demand alert fires
    "target_utilization": 0.85,
    "open_time": "09:00",
    "close_time": "17:00",
    "enforce_operating_hours": False,
}


def set_location(db: Session, location_id: int | None) -> None:
    """Make `location_id` the organization the rest of this request operates on."""
    if location_id:
        db.info["location_id"] = location_id


def get_location(db: Session, location_id: int | None = None) -> Location:
    """Explicit id > the request's scoped location (X-Location-Id / token / service) > the first location."""
    lid = location_id or db.info.get("location_id")
    if lid:
        found = db.get(Location, lid)
        if found:
            return found
    loc = db.scalar(select(Location).order_by(Location.location_id).limit(1))
    if loc is None:
        loc = Location(name="Main Service Centre")
        db.add(loc)
        db.flush()
    return loc


def get_settings_map(db: Session, location_id: int | None = None) -> dict:
    loc_id = location_id or get_location(db).location_id
    rows = db.scalars(select(LocationSetting).where(LocationSetting.location_id == loc_id)).all()
    merged = dict(DEFAULTS)
    merged.update({r.key: r.value for r in rows if r.key in DEFAULTS})
    return merged


def update_settings(db: Session, values: dict, user_id: int | None) -> dict:
    loc = get_location(db)
    for key, value in values.items():
        if key not in DEFAULTS:
            raise ValueError(f"Unknown setting: {key}")
        expected = type(DEFAULTS[key])
        if expected is float or expected is int:
            if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
                raise ValueError(f"{key} must be a non-negative number")
        elif expected is bool and not isinstance(value, bool):
            raise ValueError(f"{key} must be true/false")
        row = db.get(LocationSetting, (loc.location_id, key))
        if row is None:
            db.add(LocationSetting(location_id=loc.location_id, key=key, value=value, updated_by=user_id))
        else:
            row.value, row.updated_by = value, user_id
    db.flush()
    return get_settings_map(db, loc.location_id)


def local_tz(loc: Location):
    try:
        return ZoneInfo(loc.timezone)
    except Exception:  # tzdata missing on some platforms -> UTC rather than crash
        return timezone.utc


def local_now(loc: Location) -> datetime:
    return datetime.now(local_tz(loc))


def local_today(loc: Location) -> date:
    return local_now(loc).date()
