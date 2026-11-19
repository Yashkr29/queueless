"""SQLAlchemy models. Mirrors supabase/migrations/0001_queueless_schema.sql (the authoritative DDL)."""
import enum
from datetime import date, datetime, timezone

from sqlalchemy import (
    JSON, BigInteger, Boolean, CheckConstraint, Date, DateTime, Enum, ForeignKey, Index, Integer,
    Numeric, SmallInteger, String, Text, TypeDecorator, UniqueConstraint, func, text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base

BigPK = BigInteger().with_variant(Integer, "sqlite")   # SQLite only autoincrements INTEGER PKs
BigFK = BigInteger().with_variant(Integer, "sqlite")
JsonType = JSON().with_variant(JSONB, "postgresql")


class UTCDateTime(TypeDecorator):
    """Always timezone-aware UTC in Python (SQLite drops tzinfo)."""
    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is not None and value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc) if value is not None else None

    def process_result_value(self, value, dialect):
        if value is not None and value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _enum(py_enum: type[enum.Enum], name: str) -> Enum:
    return Enum(py_enum, name=name, create_type=False, values_callable=lambda e: [m.value for m in e])


class Role(str, enum.Enum):
    customer = "customer"
    staff = "staff"
    admin = "admin"


class ServiceStatus(str, enum.Enum):
    active = "active"
    paused = "paused"
    archived = "archived"


class CounterStatus(str, enum.Enum):
    open = "open"
    closed = "closed"
    unavailable = "unavailable"


class StaffAvailability(str, enum.Enum):
    available = "available"
    busy = "busy"
    off = "off"


class Priority(str, enum.Enum):
    none = "none"
    senior = "senior"
    disabled = "disabled"
    pregnant = "pregnant"
    emergency = "emergency"


class TokenStatus(str, enum.Enum):
    booked = "booked"
    confirmed = "confirmed"
    waiting = "waiting"
    approaching = "approaching"
    called = "called"
    serving = "serving"
    completed = "completed"
    cancelled = "cancelled"
    no_show = "no_show"


# Tokens that are still "in the queue" (not yet called) / active at all.
WAITING_STATUSES = (TokenStatus.booked, TokenStatus.confirmed, TokenStatus.waiting, TokenStatus.approaching)
ACTIVE_STATUSES = WAITING_STATUSES + (TokenStatus.called, TokenStatus.serving)
PRIORITY_RANK = {Priority.emergency: 0, Priority.senior: 1, Priority.disabled: 1, Priority.pregnant: 1, Priority.none: 2}


class DeliveryStatus(str, enum.Enum):
    pending = "pending"
    sent = "sent"
    failed = "failed"
    read = "read"


LOCATION_TYPES = ("hospital", "college", "bank", "government", "other")


class Location(Base):
    """An organization / site that runs its own queues (hospital, college, bank, government office, ...)."""
    __tablename__ = "locations"
    location_id: Mapped[int] = mapped_column(BigPK, primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    location_type: Mapped[str] = mapped_column(Text, default="other")
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    timezone: Mapped[str] = mapped_column(Text, default="Asia/Kolkata")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class LocationSetting(Base):
    __tablename__ = "location_settings"
    location_id: Mapped[int] = mapped_column(BigFK, ForeignKey("locations.location_id", ondelete="CASCADE"), primary_key=True)
    key: Mapped[str] = mapped_column(Text, primary_key=True)
    value: Mapped[dict] = mapped_column(JsonType)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)
    updated_by: Mapped[int | None] = mapped_column(BigFK, nullable=True)


class User(Base):
    __tablename__ = "users"
    __table_args__ = (Index("users_email_lower_uq", func.lower(text("email")), unique=True),)
    user_id: Mapped[int] = mapped_column(BigPK, primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    email: Mapped[str] = mapped_column(Text)
    phone: Mapped[str | None] = mapped_column(Text, nullable=True)
    password_hash: Mapped[str] = mapped_column(Text)
    role: Mapped[Role] = mapped_column(_enum(Role, "user_role"), default=Role.customer)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class PushDevice(Base):
    __tablename__ = "push_devices"
    device_id: Mapped[int] = mapped_column(BigPK, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigFK, ForeignKey("users.user_id", ondelete="CASCADE"), index=True)
    fcm_token: Mapped[str] = mapped_column(Text, unique=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Service(Base):
    __tablename__ = "services"
    __table_args__ = (UniqueConstraint("location_id", "code"), UniqueConstraint("location_id", "service_name"))
    service_id: Mapped[int] = mapped_column(BigPK, primary_key=True)
    location_id: Mapped[int] = mapped_column(BigFK, ForeignKey("locations.location_id"))
    service_name: Mapped[str] = mapped_column(Text)
    code: Mapped[str] = mapped_column(String(3))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    average_service_duration: Mapped[float] = mapped_column(Numeric(6, 2, asdecimal=False), default=8)
    status: Mapped[ServiceStatus] = mapped_column(_enum(ServiceStatus, "service_status"), default=ServiceStatus.active)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Staff(Base):
    __tablename__ = "staff"
    staff_id: Mapped[int] = mapped_column(BigPK, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigFK, ForeignKey("users.user_id", ondelete="CASCADE"), unique=True)
    location_id: Mapped[int | None] = mapped_column(BigFK, ForeignKey("locations.location_id"), nullable=True, index=True)
    availability: Mapped[StaffAvailability] = mapped_column(
        _enum(StaffAvailability, "staff_availability"), default=StaffAvailability.available)
    user: Mapped[User] = relationship()


class CounterService(Base):
    __tablename__ = "counter_services"
    counter_id: Mapped[int] = mapped_column(BigFK, ForeignKey("counters.counter_id", ondelete="CASCADE"), primary_key=True)
    service_id: Mapped[int] = mapped_column(BigFK, ForeignKey("services.service_id", ondelete="CASCADE"), primary_key=True, index=True)


class Counter(Base):
    __tablename__ = "counters"
    __table_args__ = (
        UniqueConstraint("location_id", "counter_name"),
        Index("counters_staff_uq", "assigned_staff_id", unique=True,
              postgresql_where=text("assigned_staff_id is not null"), sqlite_where=text("assigned_staff_id is not null")),
    )
    counter_id: Mapped[int] = mapped_column(BigPK, primary_key=True)
    location_id: Mapped[int] = mapped_column(BigFK, ForeignKey("locations.location_id"))
    counter_name: Mapped[str] = mapped_column(Text)
    status: Mapped[CounterStatus] = mapped_column(_enum(CounterStatus, "counter_status"), default=CounterStatus.closed)
    assigned_staff_id: Mapped[int | None] = mapped_column(BigFK, ForeignKey("staff.staff_id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    staff: Mapped[Staff | None] = relationship()
    service_links: Mapped[list[CounterService]] = relationship(cascade="all, delete-orphan")

    @property
    def service_ids(self) -> list[int]:
        return sorted(l.service_id for l in self.service_links)


_ACTIVE_SQL = "status in ('booked','confirmed','waiting','approaching','called','serving')"


class QueueToken(Base):
    __tablename__ = "queue_tokens"
    __table_args__ = (
        UniqueConstraint("service_id", "queue_date", "token_number"),
        Index("queue_tokens_one_active_uq", "user_id", "service_id", unique=True,
              postgresql_where=text(_ACTIVE_SQL), sqlite_where=text(_ACTIVE_SQL)),
        Index("queue_tokens_service_status_idx", "service_id", "status"),
        Index("queue_tokens_user_idx", "user_id", "created_at"),
        Index("queue_tokens_created_idx", "created_at"),
    )
    token_id: Mapped[int] = mapped_column(BigPK, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigFK, ForeignKey("users.user_id"))
    service_id: Mapped[int] = mapped_column(BigFK, ForeignKey("services.service_id"))
    counter_id: Mapped[int | None] = mapped_column(BigFK, ForeignKey("counters.counter_id"), nullable=True)
    queue_date: Mapped[date] = mapped_column(Date)
    token_number: Mapped[int] = mapped_column(Integer)
    token_label: Mapped[str] = mapped_column(Text)
    queue_position: Mapped[int | None] = mapped_column(Integer, nullable=True)
    priority_type: Mapped[Priority] = mapped_column(_enum(Priority, "priority_type"), default=Priority.none)
    status: Mapped[TokenStatus] = mapped_column(_enum(TokenStatus, "token_status"), default=TokenStatus.booked)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    arrival_time: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)

    user: Mapped[User] = relationship()
    service: Mapped[Service] = relationship()
    counter: Mapped[Counter | None] = relationship()


class QueueEvent(Base):
    __tablename__ = "queue_events"
    __table_args__ = (Index("queue_events_token_idx", "token_id", "timestamp"),
                      Index("queue_events_type_idx", "event_type", "timestamp"))
    event_id: Mapped[int] = mapped_column(BigPK, primary_key=True)
    token_id: Mapped[int] = mapped_column(BigFK, ForeignKey("queue_tokens.token_id", ondelete="CASCADE"))
    event_type: Mapped[str] = mapped_column(Text)
    actor_user_id: Mapped[int | None] = mapped_column(BigFK, ForeignKey("users.user_id"), nullable=True)
    timestamp: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    metadata_: Mapped[dict] = mapped_column("metadata", JsonType, default=dict)


class ServiceRecord(Base):
    __tablename__ = "service_records"
    __table_args__ = (Index("service_records_counter_idx", "counter_id", "service_start_time"),
                      Index("service_records_start_idx", "service_start_time"))
    record_id: Mapped[int] = mapped_column(BigPK, primary_key=True)
    token_id: Mapped[int] = mapped_column(BigFK, ForeignKey("queue_tokens.token_id", ondelete="CASCADE"), unique=True)
    counter_id: Mapped[int] = mapped_column(BigFK, ForeignKey("counters.counter_id"))
    service_start_time: Mapped[datetime] = mapped_column(UTCDateTime)
    service_end_time: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    actual_service_duration: Mapped[float | None] = mapped_column(Numeric(8, 2, asdecimal=False), nullable=True)
    actual_wait_minutes: Mapped[float | None] = mapped_column(Numeric(8, 2, asdecimal=False), nullable=True)
    rating: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    token: Mapped[QueueToken] = relationship()


class Prediction(Base):
    __tablename__ = "predictions"
    __table_args__ = (Index("predictions_token_idx", "token_id", "prediction_timestamp"),)
    prediction_id: Mapped[int] = mapped_column(BigPK, primary_key=True)
    token_id: Mapped[int] = mapped_column(BigFK, ForeignKey("queue_tokens.token_id", ondelete="CASCADE"))
    predicted_waiting_time: Mapped[float] = mapped_column(Numeric(8, 2, asdecimal=False))
    prediction_lower_bound: Mapped[float | None] = mapped_column(Numeric(8, 2, asdecimal=False), nullable=True)
    prediction_upper_bound: Mapped[float | None] = mapped_column(Numeric(8, 2, asdecimal=False), nullable=True)
    method: Mapped[str] = mapped_column(Text)
    model_version: Mapped[str] = mapped_column(Text)
    features: Mapped[dict | None] = mapped_column(JsonType, nullable=True)
    prediction_timestamp: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class DemandForecast(Base):
    __tablename__ = "demand_forecasts"
    __table_args__ = (UniqueConstraint("service_id", "interval_start", "horizon_minutes", "model_version"),)
    forecast_id: Mapped[int] = mapped_column(BigPK, primary_key=True)
    service_id: Mapped[int] = mapped_column(BigFK, ForeignKey("services.service_id", ondelete="CASCADE"))
    interval_start: Mapped[datetime] = mapped_column(UTCDateTime)
    horizon_minutes: Mapped[int] = mapped_column(Integer)
    predicted_arrivals: Mapped[float] = mapped_column(Numeric(8, 2, asdecimal=False))
    actual_arrivals: Mapped[int | None] = mapped_column(Integer, nullable=True)
    method: Mapped[str] = mapped_column(Text, default="ml")
    model_version: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (Index("notifications_user_idx", "user_id", "created_at"),)
    notification_id: Mapped[int] = mapped_column(BigPK, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigFK, ForeignKey("users.user_id", ondelete="CASCADE"))
    token_id: Mapped[int | None] = mapped_column(BigFK, ForeignKey("queue_tokens.token_id", ondelete="SET NULL"), nullable=True)
    notification_type: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    message: Mapped[str] = mapped_column(Text)
    delivery_status: Mapped[DeliveryStatus] = mapped_column(_enum(DeliveryStatus, "delivery_status"), default=DeliveryStatus.pending)
    read_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    audit_id: Mapped[int] = mapped_column(BigPK, primary_key=True)
    actor_user_id: Mapped[int | None] = mapped_column(BigFK, ForeignKey("users.user_id"), nullable=True)
    action: Mapped[str] = mapped_column(Text)
    entity_type: Mapped[str] = mapped_column(Text)
    entity_id: Mapped[int | None] = mapped_column(BigFK, nullable=True)
    details: Mapped[dict] = mapped_column(JsonType, default=dict)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)


class SpecialEvent(Base):
    __tablename__ = "special_events"
    event_date: Mapped[date] = mapped_column(Date, primary_key=True)
    location_id: Mapped[int] = mapped_column(BigFK, ForeignKey("locations.location_id", ondelete="CASCADE"), primary_key=True)
    label: Mapped[str] = mapped_column(Text)
    is_holiday: Mapped[bool] = mapped_column(Boolean, default=False)
