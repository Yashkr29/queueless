"""Feature contracts shared by the simulator, the training scripts and the live backend.

Keeping ONE implementation of feature construction is how we avoid train/serve skew:
the simulator calls `compute_wait_features` on its own in-memory state, the API calls it on a
snapshot of the database. Same function, same definitions (see docs/01-PRD.md §4).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

# ------------------------------------------------------------------ Model 1 ----
# Spec name -> column name used here
#   Queue_Length            queue_length            waiting tokens at the location, excluding this one
#   Customers_Ahead         customers_ahead         tokens ahead in dispatch order competing for the same counters
#   Active_Counters         active_counters         open + staffed counters that support this token's service
#   Average_Service_Time    average_service_time    rolling mean of the last 50 completed services of this service type (min)
#   Current_Arrival_Rate    current_arrival_rate    location arrivals in the last 30 min, scaled to per hour
#   Hour / Day_Of_Week      hour / day_of_week      at queue entry (local time)
#   Service_Type            service_type            service_id (categorical)
#   Historical_Average_Wait historical_average_wait mean wait for same service & hour over the previous 28 days
#   Staff_Availability      staff_availability      available counters / configured counters at the location
#   Counter_Status          busy_counters           eligible counters currently serving someone
WAIT_FEATURES = [
    "queue_length", "customers_ahead", "active_counters", "busy_counters", "average_service_time",
    "current_arrival_rate", "hour", "day_of_week", "service_type", "historical_average_wait",
    "staff_availability",
]
WAIT_TARGET = "actual_wait_minutes"
CATEGORICAL = ["service_type"]

DEFAULT_HISTORICAL_WAIT = 10.0


@dataclass
class QueuedToken:
    token_id: int
    service_id: int
    priority_rank: int          # 0 emergency, 1 senior/disabled/pregnant, 2 regular
    entered_at: float           # any monotonic number (minutes or epoch seconds): ordering only

    @property
    def order_key(self) -> tuple:
        return (self.priority_rank, self.entered_at, self.token_id)


@dataclass
class CounterState:
    counter_id: int
    service_ids: frozenset[int]
    available: bool             # status == open AND staff available
    busy: bool = False          # currently serving a customer
    remaining_service_min: float | None = None   # estimate for the customer in service, if known


@dataclass
class WaitSnapshotContext:
    hour: int
    day_of_week: int
    average_service_time: float
    current_arrival_rate: float
    historical_average_wait: float = DEFAULT_HISTORICAL_WAIT
    extra: dict = field(default_factory=dict)


def eligible_counters(service_id: int, counters: list[CounterState]) -> list[CounterState]:
    return [c for c in counters if c.available and service_id in c.service_ids]


def compute_wait_features(target: QueuedToken, waiting: list[QueuedToken], counters: list[CounterState],
                          ctx: WaitSnapshotContext) -> dict:
    """`waiting` contains every not-yet-called token INCLUDING `target`."""
    elig = eligible_counters(target.service_id, counters)
    servable = set().union(*[c.service_ids for c in elig]) if elig else {target.service_id}
    key = target.order_key
    ahead = sum(1 for w in waiting if w.token_id != target.token_id and w.service_id in servable and w.order_key < key)
    total = max(len(counters), 1)
    return {
        "queue_length": sum(1 for w in waiting if w.token_id != target.token_id),
        "customers_ahead": ahead,
        "active_counters": len(elig),
        "busy_counters": sum(1 for c in elig if c.busy),
        "average_service_time": round(ctx.average_service_time, 3),
        "current_arrival_rate": round(ctx.current_arrival_rate, 3),
        "hour": ctx.hour,
        "day_of_week": ctx.day_of_week,
        "service_type": target.service_id,
        "historical_average_wait": round(ctx.historical_average_wait, 3),
        "staff_availability": round(sum(1 for c in counters if c.available) / total, 4),
    }


def fallback_wait_minutes(features: dict) -> float | None:
    """Non-ML estimate (PRD §7). Returns None when no eligible counter is available.

    ceil-free on purpose: wait = (ahead / counters) * avg_service + residual for customers currently in service.
    """
    n = features["active_counters"]
    if n <= 0:
        return None
    avg = features["average_service_time"]
    residual = (features["busy_counters"] / n) * (avg / 2.0)
    return round(features["customers_ahead"] / n * avg + residual, 2)


# ------------------------------------------------------------------ Model 2 ----
DEMAND_BIN_MINUTES = 30
DEMAND_HORIZONS = (30, 60, 120)
DEMAND_FEATURES = [
    "hour_of_day", "day_of_week", "prev_1h", "prev_3h", "prev_day_same", "prev_week_same",
    "historical_demand", "is_holiday", "special_event", "service_type",
]


def demand_feature_row(*, get_count, bin_index: int, horizon_bins: int, hour_of_day: float, day_of_week: int,
                       is_holiday: int, special_event: int, service_type: int) -> dict:
    """`get_count(i)` returns arrivals in 30-minute bin `i`; bins are numbered consecutively in
    wall-clock time (48 per day), so day = 48 bins, week = 336 bins. Missing bins must return 0.
    `historical_demand` = mean arrivals in the same window over the previous 4 weeks (past only)."""
    day, week = 24 * 60 // DEMAND_BIN_MINUTES, 7 * 24 * 60 // DEMAND_BIN_MINUTES
    window = range(horizon_bins)
    return {
        "hour_of_day": hour_of_day,
        "day_of_week": day_of_week,
        "prev_1h": sum(get_count(bin_index - k) for k in (1, 2)),
        "prev_3h": sum(get_count(bin_index - k) for k in range(1, 7)),
        "prev_day_same": sum(get_count(bin_index - day + k) for k in window),
        "prev_week_same": sum(get_count(bin_index - week + k) for k in window),
        "historical_demand": sum(sum(get_count(bin_index - week * k + j) for j in window) for k in (1, 2, 3, 4)) / 4,
        "is_holiday": is_holiday,
        "special_event": special_event,
        "service_type": service_type,
    }


def wape(y_true, y_pred) -> float:
    denom = float(sum(abs(v) for v in y_true))
    return float(sum(abs(a - b) for a, b in zip(y_true, y_pred)) / denom) if denom else math.nan
