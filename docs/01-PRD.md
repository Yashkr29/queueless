# QueueLess — Product Requirements Document (v1.0)

> **Tagline:** Know When to Arrive. Skip the Wait.
> **Status:** Refined from the original brief. Items marked **[Assumption]** or **[Gap]** are decisions the brief did not make for us.

## 1. Product summary

QueueLess is a predictive queue-management platform. It does three things a token-booking app does not:

1. **Predicts** when each customer will be served (ML waiting-time model with an uncertainty range, and an honest non-ML fallback).
2. **Recommends** when the customer should arrive (smart arrival window) so they do not wait physically.
3. **Advises** the service provider (demand forecast + rule-based optimization engine) so congestion is handled *before* it happens. Admins stay in control: the system recommends, humans apply.

**Scope:** multiple organizations (hospital, college, bank, government centre, other), each with multiple counters and configurable service types. Admins add organizations in the app; staff are pinned to one organization; customers pick where they are going.

## 2. Users and jobs-to-be-done

| Persona | Job to be done |
|---|---|
| Customer (patient, bank/college/government visitor) | "Tell me honestly when I'll be served, and when I can leave home." |
| Counter staff | "Call the next person, record service, handle no-shows, with minimum clicks." |
| Administrator / branch manager | "See congestion coming, decide on counters/staff, and prove performance with reports." |

## 3. Goals and success metrics

| Area | Metric | Source |
|---|---|---|
| Customer experience | Avg. waiting time; abandonment rate; % arriving inside recommended window; satisfaction (Phase 2 survey) | `service_records`, `queue_events` |
| Operations | Avg. service duration; counter utilization; customers/hour; peak-congestion frequency | `service_records`, counters |
| ML | Wait-time MAE/RMSE; demand WAPE; no-show F1 (Phase 2); drift | `predictions` vs `service_records`, `demand_forecasts` |

**Honesty rule:** all ML metrics produced before real operation are *simulated-data* metrics. The UI, reports and model registry label them as such. Real-world accuracy is only reported from `predictions` joined to real `service_records` (rows with `is_demo = false`).

## 4. Definitions (the operational conventions the brief asked us to define)

| Term | Definition |
|---|---|
| **Queue entry time** | `queue_tokens.created_at` — when the token is issued (virtual queue joined). |
| **Actual waiting time** | `service_start_time − queue entry time`, in minutes. Cancelled / no-show tokens have no waiting label (they are *censored*, excluded from wait-model training, counted in abandonment). |
| **Why entry time, not physical arrival** | The virtual queue order is by entry time + priority, so that is what the customer actually waits through. Physical arrival is recorded separately (`arrival_time`) and is used for the "arrived inside window" KPI. |
| **Customers ahead** | Active tokens ahead of this one in dispatch order that compete for at least one counter able to serve its service. |
| **Dispatch order** | `priority rank` (emergency < senior/disabled/pregnant < regular), then entry time. |
| **Active counter (for a service)** | Counter that is `open`, has staff `available`, and supports that service. |
| **Approaching turn** | `customers_ahead <= approaching_threshold` (admin-configurable, default 3). |

## 5. Token lifecycle

```
booked ─► confirmed ─► waiting ─► approaching ─► called ─► serving ─► completed
   │          │           │            │            │
   └──────────┴───────────┴────────────┴─► cancelled (customer or staff)
                                         called ─► no_show (staff, after grace period)
```

* `booked`: token issued remotely. `confirmed`: customer pressed "I'm on my way" (reminder acknowledgement). `waiting`: customer checked in physically (`arrival_time` set). `approaching`: set by the queue engine.
* `called → no_show` never happens automatically. **The ML no-show score never skips, denies or reorders a customer.**

## 6. Functional requirements (refined from the brief)

Priority: **P0** = MVP, **P1** = MVP-stretch / Phase 2, **P2** = post-MVP.

### Module A — Customer app

| ID | Requirement | Pri | Status in this repo |
|---|---|---|---|
| A1 | Register / login (JWT), profile, history, roles | P0 | ✅ |
| A2 | Service discovery with live queue length + estimated wait | P0 | ✅ |
| A3 | Join virtual queue; unique token; cancel; priority categories; **no duplicate active token per service** (DB partial unique index + service check) | P0 | ✅ |
| A4 | Live tracking (position, ahead, ETA, counter, status) over WebSocket | P0 | ✅ |
| A5 | ML waiting time + range + model version; recalculates on queue/counter changes; clearly labelled fallback | P0 | ✅ (fallback always; ML once a model is trained) |
| A6 | Smart arrival window (expected service − travel/safety buffer, widened by prediction uncertainty) | P0 | ✅ |
| A7 | Notifications (in-app + WebSocket now; FCM provider pluggable) | P0/P1 | ✅ in-app, FCM adapter wired but needs your Firebase credentials |
| A8 | Cancel; rejoin rules (cooldown after no-show, configurable); delay notices | P1 | ✅ cancel + cooldown; delay notices when ETA moves ≥ threshold |

### Module B — Staff / admin dashboard

| ID | Requirement | Pri | Status |
|---|---|---|---|
| B1 | KPI overview | P0 | ✅ |
| B2 | Live queue: call / start / complete / no-show / cancel / reassign counter; priority override; every action audited | P0 | ✅ |
| B3 | Counter CRUD, open/close, staff assignment, supported services, utilization | P0 | ✅ |
| B4 | Demand analytics (Recharts) | P0 | ✅ (hourly, daily, wait trend, utilization, predicted-vs-actual) |
| B5 | Predictive congestion alerts **with actions** | P0 | ✅ |
| B6 | Counter/staff optimization recommendations; admin applies | P1 | ✅ (greedy, transparent) |
| B7 | Daily report, CSV + PDF | P1 | ✅ |

### ML & optimization

| ID | Requirement | Pri | Status |
|---|---|---|---|
| M1 | Waiting-time model: LR vs RF vs GBR vs XGBoost, chronological split, MAE primary, interval from held-out residuals | P0 | ✅ pipeline + trained artifact on **simulated** data |
| M2 | Demand forecast 30/60/120 min: RF vs GBR vs XGBoost (+ seasonal-naive baseline), WAPE | P1 | ✅ pipeline; Prophet left as optional candidate |
| M3 | No-show classifier | P1 (Phase 2) | ⏳ designed, not built (needs real booking history; see ML doc) |
| O1 | Rule engine with admin-configurable thresholds | P0 | ✅ |
| O2 | Greedy counter-allocation recommender | P1 | ✅ |
| O3 | Audit trail of manual overrides | P0 | ✅ |
| X1 | Digital-twin what-if simulator | P2 | ⏳ (simulator core exists and is reusable; UI not built) |
| X2 | Multi-location: admin adds hospitals / colleges / banks / government centres / other, each with its own services, counters, staff, hours and thresholds | P1 | ✅ (cross-location comparison dashboard still ⏳) |

## 7. Non-functional requirements

* **Resilience:** all queue operations work with no ML model/service. Fallback estimate = `ceil(eligible_customers_ahead / active_counters) × avg_service_time` (+ in-service residual), labelled `method: "fallback"`.
* **Security:** JWT, bcrypt, RBAC (`customer`, `staff`, `admin`), Pydantic validation, ORM-only SQL, CORS allow-list, in-memory rate limiting (Redis for multi-instance), WebSocket JWT auth, audit log, env-based secrets, Supabase RLS enabled with *no* public policies (backend is the only data path).
* **Data integrity:** token numbering and join are transactional; unique `(service_id, queue_date, token_number)`; partial unique index preventing two active tokens per user per service; append-only `queue_events`.
* **Privacy:** customers only read their own tokens; staff views show name + token only; no phone/email in queue lists; customer data export/delete hooks documented as Phase 2.
* **Performance targets [Assumption]:** ≤ 300 ms p95 for `/queue/join` and status reads at ≤ 50 concurrent users on a 512 MB instance; WebSocket fan-out per service ≤ 200 connections.
* **Accessibility:** WCAG AA contrast, keyboard focus states, labels on controls, no colour-only status.

## 8. Missing requirements identified & assumptions

| # | Gap in the brief | Decision |
|---|---|---|
| 1 | **Database** — brief said PostgreSQL; request says Supabase | **Supabase Postgres** is the database. Backend connects with SQLAlchemy over the Supabase connection string. Schema ships as a Supabase migration. Supabase Auth is *not* used (brief requires `password_hash` + own JWT); RLS is enabled with no policies so the public Supabase REST API exposes nothing. |
| 2 | Supabase credentials | Not available to the build. You must create the project and paste `DATABASE_URL` into `.env`. Local dev/tests fall back to SQLite so nothing blocks. |
| 3 | Operating hours | Per-location settings `open_time` / `close_time` (default 09:00–17:00), timezone default `Asia/Kolkata` **[Assumption]**. |
| 4 | Priority categories | `emergency`, `senior`, `disabled`, `pregnant`, `none`. Only staff/admin may assign `emergency`; others are self-declared at join and verified at the counter **[Assumption]**. |
| 5 | Rejoin rule | After a `no_show`, same user/service blocked for `rejoin_cooldown_minutes` (default 15). Cancel has no cooldown. |
| 6 | Service-type ↔ counter mapping | Brief lists `counters.service_id`; we use a `counter_services` join table so one counter can serve several services (B3). `staff.assigned_counter` is derived from `counters.assigned_staff_id` (single source of truth; avoids a circular FK). |
| 7 | Holidays / special events | Configurable fixed-date holiday list + admin-entered special-event flag per date (table `special_events`) **[Assumption: India national dates as defaults]**. |
| 8 | Staff break / unavailability | Counter status `open / closed / unavailable`; staff availability `available / busy / off`. |
| 9 | Cancelled-customer wait labels | Censored; excluded from model training; counted in abandonment. |
| 10 | Notification channels | In-app (DB + WebSocket) is the system of record; FCM push is a delivery channel behind an interface. SMS/email out of scope. |
| 11 | Pilot data volume | Assume < 500 tokens/day; model retraining is scheduled/threshold-based (≥ 2,000 new real labelled rows or MAE drift > 20 %), never per-transaction. |
| 12 | Demo vs real data | `is_demo` flag on users and tokens; seed script labels everything; UI shows a "Demo data" banner; analytics can filter. |
| 13 | Customer satisfaction KPI | Needs a post-service rating; table column reserved (`service_records.rating`), UI capture is Phase 2. |
| 14 | Admin login screen | One login page with role-based redirect (separate admin URL is a presentation choice, not a security boundary). |
| 15 | Real-time scale | Single-process in-memory WebSocket hub. Horizontal scale needs a pub/sub (Supabase Realtime or Redis) — documented, not built. |

## 9. Out of scope for v1

SMS/email, payments, multi-tenant billing, native mobile apps (the customer web app is responsive/PWA-ready), industry-specific workflows (medical triage, KYC), Prophet service, Model 3 training.

## 10. Release plan

See [05-TASK-BREAKDOWN.md](05-TASK-BREAKDOWN.md). Timelines are targets, not commitments.
