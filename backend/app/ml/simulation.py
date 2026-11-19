"""Discrete-event simulation of a multi-counter service centre.

Wait-time labels are NOT produced by a formula over the features. They emerge from an event-driven
process (stochastic arrivals, lognormal service times, priority dispatch, counter breaks, reneging,
no-shows) and are measured exactly as in production: service_start - queue_entry.

Everything produced here is SIMULATED. Metrics from models trained on it say nothing about real-world accuracy.
"""
from __future__ import annotations

import heapq
import math
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd

from .calendar_utils import is_default_holiday
from .features import (
    DEFAULT_HISTORICAL_WAIT, CounterState, QueuedToken, WaitSnapshotContext, compute_wait_features,
)

SERVICES = [
    dict(service_id=1, code="G", name="General Enquiry", description="Questions, forms and general help", mean=6.0, cv=0.6, share=0.30),
    dict(service_id=2, code="P", name="Payments & Billing", description="Fee payments, receipts and billing queries", mean=5.0, cv=0.5, share=0.30),
    dict(service_id=3, code="D", name="Document Verification", description="Certificate and ID verification", mean=11.0, cv=0.5, share=0.25),
    dict(service_id=4, code="N", name="New Applications", description="New registrations and applications", mean=18.0, cv=0.45, share=0.15),
]
COUNTERS = [
    (1, "Counter 1", frozenset({1, 2})),
    (2, "Counter 2", frozenset({1, 2})),
    (3, "Counter 3", frozenset({2, 3})),
    (4, "Counter 4", frozenset({3, 4})),
    (5, "Counter 5", frozenset({4, 1})),
]
HOUR_PROFILE = {9: 0.8, 10: 1.3, 11: 1.5, 12: 1.0, 13: 0.7, 14: 1.2, 15: 1.1, 16: 0.6}
DOW_FACTOR = {0: 1.30, 1: 1.00, 2: 0.95, 3: 1.00, 4: 1.15, 5: 0.65}   # Sunday closed
PRIORITIES = [("none", 0.86, 2), ("senior", 0.07, 1), ("disabled", 0.03, 1), ("pregnant", 0.03, 1), ("emergency", 0.01, 0)]
NO_SHOW_GRACE_MIN = 2.0


@dataclass
class SimConfig:
    days: int = 120
    start_date: date = date(2025, 1, 6)        # a Monday
    seed: int = 42
    base_per_hour: float = 32.0
    open_hour: int = 9
    close_hour: int = 17
    patience_mean_min: float = 60.0
    early_cancel_p: float = 0.04
    event_day_p: float = 0.05
    event_multiplier: float = 1.45
    holiday_multiplier: float = 0.35


@dataclass
class SimResult:
    tokens: pd.DataFrame
    event_dates: list[date] = field(default_factory=list)
    holiday_dates: list[date] = field(default_factory=list)
    config: SimConfig | None = None


ARRIVE, RENEGE, SERVICE_END, BREAK_START, BREAK_END, NOSHOW_END = range(6)


def _lognormal(rng: np.random.Generator, mean: float, cv: float) -> float:
    sigma2 = math.log(1 + cv * cv)
    return float(rng.lognormal(math.log(mean) - sigma2 / 2, math.sqrt(sigma2)))


def simulate(cfg: SimConfig | None = None, *, services=None, counters=None) -> SimResult:
    cfg = cfg or SimConfig()
    services = services or SERVICES
    counters_cfg = counters or COUNTERS
    rng = np.random.default_rng(cfg.seed)
    svc_by_id = {s["service_id"]: s for s in services}
    shares = np.array([s["share"] for s in services]); shares = shares / shares.sum()
    efficiency = {cid: float(rng.uniform(0.9, 1.15)) for cid, _, _ in counters_cfg}   # staff speed differences

    recent_dur = {s["service_id"]: deque(maxlen=50) for s in services}
    day_wait_sum: dict[int, dict[tuple, list]] = {}     # day_index -> (service, hour) -> [sum, n]
    rows: list[dict] = []
    event_dates, holiday_dates = [], []
    next_id = 1

    for day_idx in range(cfg.days):
        d = cfg.start_date + timedelta(days=day_idx)
        if d.weekday() == 6:        # Sunday closed
            continue
        holiday = is_default_holiday(d)
        event = (not holiday) and rng.random() < cfg.event_day_p
        (holiday_dates if holiday else event_dates if event else []).append(d)
        day_mult = cfg.holiday_multiplier if holiday else cfg.event_multiplier if event else 1.0

        # -- historical average wait table from PREVIOUS days only (no leakage)
        hist: dict[tuple, list] = defaultdict(lambda: [0.0, 0])
        for past in range(max(0, day_idx - 28), day_idx):
            for k, (s, n) in day_wait_sum.get(past, {}).items():
                hist[k][0] += s; hist[k][1] += n
        today_wait: dict[tuple, list] = defaultdict(lambda: [0.0, 0])

        # -- today's roster
        working = {cid: bool(rng.random() < 0.88) for cid, _, _ in counters_cfg}
        while sum(working.values()) < 2:
            working[int(rng.choice([c[0] for c in counters_cfg]))] = True
        cstate = {cid: dict(cid=cid, svc=sv, working=working[cid], busy=False, on_break=False, pending_break=False,
                            break_len=float(rng.uniform(20, 35))) for cid, _, sv in counters_cfg}

        events: list = []
        seq = 0

        def push(t, kind, data):
            nonlocal seq
            seq += 1
            heapq.heappush(events, (t, seq, kind, data))

        for cid, st in cstate.items():
            if st["working"] and rng.random() < 0.7:
                push(float(rng.uniform(12 * 60, 14 * 60)), BREAK_START, cid)

        # -- arrivals (non-homogeneous Poisson via per-minute draws)
        toks: dict[int, dict] = {}
        per_service_no: dict[int, int] = defaultdict(int)
        for minute in range(cfg.open_hour * 60, cfg.close_hour * 60):
            lam = cfg.base_per_hour / 60 * HOUR_PROFILE.get(minute // 60, 1.0) * DOW_FACTOR[d.weekday()] * day_mult
            for _ in range(int(rng.poisson(lam))):
                t = minute + float(rng.random())
                sid = int(rng.choice([s["service_id"] for s in services], p=shares))
                pr_name, _, pr_rank = PRIORITIES[int(rng.choice(len(PRIORITIES), p=[p[1] for p in PRIORITIES]))]
                tid = next_id; next_id += 1
                if rng.random() < cfg.early_cancel_p:
                    renege = t + float(rng.uniform(0.5, 6))
                elif pr_name == "emergency":
                    renege = math.inf
                else:
                    renege = t + float(rng.exponential(cfg.patience_mean_min))
                toks[tid] = dict(token_id=tid, service_id=sid, priority=pr_name, rank=pr_rank, t=t, renege=renege)
                push(t, ARRIVE, tid)

        waiting: list[QueuedToken] = []
        qmap: dict[int, QueuedToken] = {}
        arrivals: deque = deque()
        done = {}

        def states() -> list[CounterState]:
            return [CounterState(cid, st["svc"], st["working"] and not st["on_break"], st["busy"])
                    for cid, st in cstate.items()]

        def start_service(now: float, cid: int, q: QueuedToken):
            info = toks[q.token_id]
            wait = now - info["t"]
            info["called"] = now
            info["counter_id"] = cid
            cstate[cid]["busy"] = True
            p_ns = min(0.25, 0.03 + 0.0015 * wait)
            if rng.random() < p_ns:
                info["outcome"] = "no_show"
                push(now + NO_SHOW_GRACE_MIN, NOSHOW_END, (cid, q.token_id))
                return
            s = svc_by_id[q.service_id]
            dur = _lognormal(rng, s["mean"], s["cv"]) * efficiency[cid] * (1.1 if now >= 14 * 60 else 1.0)
            info.update(outcome="served", start=now, end=now + dur, wait=wait, dur=dur)
            push(now + dur, SERVICE_END, (cid, q.token_id))

        def dispatch(now: float):
            for cid, st in cstate.items():
                if not (st["working"] and not st["on_break"] and not st["busy"]):
                    continue
                cands = [w for w in waiting if w.service_id in st["svc"]]
                if cands:
                    best = min(cands, key=lambda w: w.order_key)
                    waiting.remove(best)
                    start_service(now, cid, best)

        while events:
            now, _, kind, data = heapq.heappop(events)
            if kind == ARRIVE:
                info = toks[data]
                q = QueuedToken(data, info["service_id"], info["rank"], info["t"])
                waiting.append(q); qmap[data] = q
                while arrivals and arrivals[0] < now - 30:
                    arrivals.popleft()
                arrivals.append(now)
                sid = info["service_id"]
                durs = recent_dur[sid]
                avg_s = float(np.mean(durs)) if durs else svc_by_id[sid]["mean"]
                h = hist.get((sid, int(now // 60)))
                ctx = WaitSnapshotContext(
                    hour=int(now // 60), day_of_week=d.weekday(), average_service_time=avg_s,
                    current_arrival_rate=len(arrivals) * 2.0,
                    historical_average_wait=(h[0] / h[1]) if h and h[1] >= 3 else DEFAULT_HISTORICAL_WAIT)
                info["features"] = compute_wait_features(q, waiting, states(), ctx)
                if info["renege"] < math.inf:
                    push(info["renege"], RENEGE, data)
                dispatch(now)
            elif kind == RENEGE:
                q = qmap.get(data)
                if q in waiting:
                    waiting.remove(q)
                    toks[data]["outcome"] = "cancelled"
                    toks[data]["cancel_at"] = now
            elif kind == SERVICE_END:
                cid, tid = data
                info = toks[tid]
                recent_dur[info["service_id"]].append(info["dur"])
                k = (info["service_id"], int(info["t"] // 60))
                today_wait[k][0] += info["wait"]; today_wait[k][1] += 1
                _free(cstate[cid], now, push)
                dispatch(now)
            elif kind == NOSHOW_END:
                cid, _ = data
                _free(cstate[cid], now, push)
                dispatch(now)
            elif kind == BREAK_START:
                st = cstate[data]
                if st["busy"]:
                    st["pending_break"] = True
                else:
                    st["on_break"] = True
                    push(now + st["break_len"], BREAK_END, data)
            elif kind == BREAK_END:
                cstate[data]["on_break"] = False
                dispatch(now)

        day_wait_sum[day_idx] = {k: tuple(v) for k, v in today_wait.items()}
        counters_working = sum(working.values())
        per_service_counter: dict[int, int] = defaultdict(int)
        for tid, info in sorted(toks.items(), key=lambda kv: kv[1]["t"]):
            per_service_counter[info["service_id"]] += 1
            base = datetime(d.year, d.month, d.day)
            outcome = info.get("outcome", "cancelled")
            if outcome == "cancelled" and "cancel_at" not in info:
                info["cancel_at"] = cfg.close_hour * 60.0      # never served (e.g. no counter supports the service today): expires at close
            rows.append({
                "token_id": tid, "date": d, "token_number": per_service_counter[info["service_id"]],
                "service_id": info["service_id"], "priority": info["priority"], "outcome": outcome,
                "entered_at": base + timedelta(minutes=info["t"]),
                "called_at": base + timedelta(minutes=info["called"]) if "called" in info else pd.NaT,
                "service_start": base + timedelta(minutes=info["start"]) if "start" in info else pd.NaT,
                "service_end": base + timedelta(minutes=info["end"]) if "end" in info else pd.NaT,
                "cancel_at": base + timedelta(minutes=info["cancel_at"]) if "cancel_at" in info else pd.NaT,
                "counter_id": info.get("counter_id"),
                "actual_wait_minutes": info.get("wait"),
                "service_minutes": info.get("dur"),
                "is_holiday": int(holiday), "special_event": int(event), "counters_working": counters_working,
                **info["features"],
            })

    df = pd.DataFrame(rows)
    return SimResult(df, event_dates, holiday_dates, cfg)


def _free(st: dict, now: float, push) -> None:
    """Counter finished a customer; start a deferred break if one was pending."""
    st["busy"] = False
    if st["pending_break"]:
        st["pending_break"] = False
        st["on_break"] = True
        push(now + st["break_len"], BREAK_END, st["cid"])
