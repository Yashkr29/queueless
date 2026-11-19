"""API data contracts. The React client (frontend/src/lib/api.js and the pages) consumes exactly these shapes;
OpenAPI is served at /docs."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator

from .models import CounterStatus, Priority, Role, ServiceStatus, StaffAvailability, TokenStatus


class ORM(BaseModel):
    model_config = {"from_attributes": True}


# ---- auth
class RegisterIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    phone: str | None = Field(default=None, max_length=20, pattern=r"^[0-9+\-\s()]*$")
    password: str = Field(min_length=8, max_length=72)


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(max_length=72)


class UserOut(ORM):
    user_id: int
    name: str
    email: str
    phone: str | None
    role: Role
    created_at: datetime


class AuthOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class ProfileUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    phone: str | None = Field(default=None, max_length=20, pattern=r"^[0-9+\-\s()]*$")


# ---- services & queue
class ServiceOut(ORM):
    service_id: int
    location_id: int
    service_name: str
    code: str
    description: str | None
    average_service_duration: float
    status: ServiceStatus


class EstimateOut(BaseModel):
    wait_minutes: float | None
    lower_minutes: float | None = None
    upper_minutes: float | None = None
    method: Literal["ml", "fallback", "unavailable"]
    model_version: str | None = None
    trained_on: str | None = None
    note: str


class ArrivalWindowOut(BaseModel):
    expected_service_time: datetime
    recommended_arrival: datetime
    window_start: datetime
    window_end: datetime
    arrive_now: bool


class CounterBrief(BaseModel):
    counter_id: int
    counter_name: str


class TokenOut(BaseModel):
    token_id: int
    token_label: str
    status: TokenStatus
    priority_type: Priority
    service: ServiceOut
    queue_position: int | None
    customers_ahead: int | None
    counter: CounterBrief | None
    created_at: datetime
    arrival_time: datetime | None
    estimate: EstimateOut | None
    arrival_window: ArrivalWindowOut | None


class ServiceStatusOut(BaseModel):
    service: ServiceOut
    queue_length: int
    active_counters: int
    open_counters: int
    estimate: EstimateOut


class JoinIn(BaseModel):
    service_id: int
    priority_type: Priority = Priority.none

    @field_validator("priority_type")
    @classmethod
    def _no_self_emergency(cls, v: Priority) -> Priority:
        if v == Priority.emergency:
            raise ValueError("Emergency priority can only be assigned by staff")
        return v


class ConfirmArrivalIn(BaseModel):
    mode: Literal["on_my_way", "arrived"] = "arrived"


# ---- admin
class CounterIn(BaseModel):
    counter_name: str = Field(min_length=1, max_length=60)
    status: CounterStatus = CounterStatus.closed
    assigned_staff_id: int | None = None
    service_ids: list[int] = []


class CounterPatch(BaseModel):
    counter_name: str | None = Field(default=None, min_length=1, max_length=60)
    status: CounterStatus | None = None
    assigned_staff_id: int | None = None
    unassign_staff: bool = False
    service_ids: list[int] | None = None


class CounterOut(BaseModel):
    counter_id: int
    counter_name: str
    status: CounterStatus
    assigned_staff_id: int | None
    staff_name: str | None
    service_ids: list[int]
    busy: bool
    current_token: str | None
    served_today: int


class StaffIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)


class StaffPatch(BaseModel):
    availability: StaffAvailability


class CallIn(BaseModel):
    counter_id: int | None = None
    override_reason: str | None = Field(default=None, max_length=300)


class CallNextIn(BaseModel):
    counter_id: int


class TokenPatchIn(BaseModel):
    priority_type: Priority | None = None
    reason: str = Field(min_length=3, max_length=300)


class ReasonIn(BaseModel):
    reason: str | None = Field(default=None, max_length=300)


class SettingsPatch(BaseModel):
    values: dict[str, float | int | str | bool]


class Page(BaseModel):
    items: list
    total: int
    page: int
    page_size: int


# ---- organizations (locations)
LocationType = Literal["hospital", "college", "bank", "government", "other"]
HHMM = r"^([01][0-9]|2[0-3]):[0-5][0-9]$"


class LocationIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    location_type: LocationType = "other"
    address: str | None = Field(default=None, max_length=300)
    timezone: str = Field(default="Asia/Kolkata", max_length=64)
    open_time: str | None = Field(default=None, pattern=HHMM)
    close_time: str | None = Field(default=None, pattern=HHMM)
    use_template: bool = True            # create the typical services + closed counters for this type


class LocationPatch(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    location_type: LocationType | None = None
    address: str | None = Field(default=None, max_length=300)
    timezone: str | None = Field(default=None, max_length=64)
    is_active: bool | None = None
    open_time: str | None = Field(default=None, pattern=HHMM)
    close_time: str | None = Field(default=None, pattern=HHMM)


class ServiceIn(BaseModel):
    service_name: str = Field(min_length=2, max_length=80)
    code: str = Field(min_length=1, max_length=3, pattern=r"^[A-Za-z0-9]+$")
    description: str | None = Field(default=None, max_length=200)
    average_service_duration: float = Field(default=8, gt=0, le=240)


class ServicePatch(BaseModel):
    service_name: str | None = Field(default=None, min_length=2, max_length=80)
    description: str | None = Field(default=None, max_length=200)
    average_service_duration: float | None = Field(default=None, gt=0, le=240)
    status: ServiceStatus | None = None
