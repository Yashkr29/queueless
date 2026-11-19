# QueueLess — API reference

Interactive OpenAPI docs are served by the running backend at **`/docs`** (Swagger) and `/redoc`. This page summarises the contract. All routes except `/auth/register`, `/auth/login`, `/health` need `Authorization: Bearer <JWT>`.

Errors: `{"detail": "message"}` with 400/401/403/404/409/422/429/500. Validation errors (422) return a list of Pydantic messages. Lists that can grow are paginated (`page`, `page_size`, `total`).

## Auth
| Method | Path | Notes |
|---|---|---|
| POST | `/auth/register` | `{name,email,phone?,password≥8}` → `{access_token,user}`; role is always `customer` |
| POST | `/auth/login` | generic 401 on failure; 20 req/min/IP |
| GET / PATCH | `/auth/me` | profile |

## Services & queue (customer)
| Method | Path | Notes |
|---|---|---|
| GET | `/services`, `/services/{id}` | `ServiceStatus`: service, queue_length, active/open counters, **estimate for a new joiner** |
| GET | `/queue/status/{service_id}` | same as above |
| POST | `/queue/join` | `{service_id, priority_type∈none/senior/disabled/pregnant}` → `TokenOut`. 409 duplicate active token / rejoin cooldown. `emergency` rejected (staff only) |
| GET | `/queue/mine?active_only&limit` | own tokens |
| GET | `/queue/{token_id}` | own token (other customers' → 404) |
| POST | `/queue/{token_id}/cancel` | |
| POST | `/queue/{token_id}/confirm-arrival` | `{mode: "on_my_way"|"arrived"}` |

`TokenOut.estimate = {wait_minutes, lower_minutes, upper_minutes, method: ml|fallback|unavailable, model_version, trained_on, note}` — `lower/upper` are **null** for fallback. `arrival_window = {expected_service_time, recommended_arrival, window_start, window_end, arrive_now}`.

## Staff operations (`staff` or `admin`)
| Method | Path | Notes |
|---|---|---|
| GET | `/admin/queue?service_id&status&active_only&page&page_size` | paginated, with estimates |
| GET | `/admin/queue/{id}/events` | append-only event history of one token (timeline in the live-queue side panel) |
| POST | `/admin/queue/call-next` | `{counter_id}` — head of line for that counter |
| POST | `/admin/queue/{id}/call` | `{counter_id?, override_reason?}` — calling out of order → 409 unless `override_reason` (audited) |
| POST | `/admin/queue/{id}/start` · `/complete` · `/no-show` | state-machine guarded |
| POST | `/admin/queue/{id}/cancel` | `{reason?}` |
| PATCH | `/admin/queue/{id}` | `{priority_type, reason}` — audited priority override |
| GET | `/admin/counters` | status, busy, current token, staff, services |
| GET | `/admin/staff` | |
| GET | `/admin/alerts` · `/admin/recommendations` | rules engine output; each item may carry an `action` payload |
| GET | `/admin/settings` | thresholds |

## Admin only
| Method | Path | Notes |
|---|---|---|
| POST / PATCH | `/admin/counters`, `/admin/counters/{id}` | status, staff, `service_ids`; audited |
| POST / PATCH | `/admin/staff`, `/admin/staff/{id}` | create staff account; availability |
| POST | `/admin/services` | `{service_name, code, average_service_duration, description}` |
| PATCH | `/admin/settings` | `{values:{key:number}}` |
| GET | `/admin/audit?page&page_size` | audit log |

## Organizations (multi-location)
Send `X-Location-Id: <id>` to choose the organization a request operates on (optional; defaults to the first). Staff are pinned to their own organization by the server.

| Method | Path | Notes |
|---|---|---|
| GET | `/locations` | active organizations, for customers to choose from |
| GET | `/admin/locations` | with counts (services, counters, staff, waiting); staff see only their own |
| GET | `/admin/location-templates` | admin: what "start with typical services" creates per type |
| POST | `/admin/locations` | admin: `{name, location_type, address?, timezone, open_time?, close_time?, use_template}` |
| PATCH | `/admin/locations/{id}` | admin: edit, hours, activate/deactivate (last active one cannot be deactivated) |
| GET / POST / PATCH | `/admin/services`, `/admin/services/{id}` | services of the active organization (add, edit typical minutes, pause/archive) |

## Predictions
| Method | Path | Notes |
|---|---|---|
| GET | `/predictions/wait-time/{token_id}` | estimate + arrival window (owner or staff) |
| GET | `/predictions/demand/{service_id}` | 30/60/120-min forecasts, workload vs capacity, peak hours, preparation advice (staff) |
| GET | `/predictions/congestion/{service_id}` | alerts for the service (staff) |
| GET | `/predictions/models` | model info + registry (staff) |

## Analytics (staff) — `?source=all|live|demo` on each
`/analytics/overview` · `/analytics/traffic?granularity=hour|day|week|month&days` · `/analytics/waiting-time?days` · `/analytics/counter-performance?days` · `/analytics/predicted-vs-actual-arrivals?day` · `/analytics/ml-monitoring?days` · `/analytics/reports/daily?day&format=json|csv|pdf`

## Notifications
`GET /notifications` · `POST /notifications/read-all` · `POST /notifications/devices {fcm_token}`

## WebSocket `/ws`
Send `{"type":"auth","token":"<JWT>"}` first. Receive `ready`, `token_update {token}`, `notification {notification}`, `queue_changed` (staff). Send the text `ping` for keep-alive.
