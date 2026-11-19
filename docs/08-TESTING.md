# QueueLess — Testing

## What exists and was run

`cd backend && python -m pytest -q` → **17 tests** against an isolated SQLite database with ML disabled (deterministic):

| Area | Test |
|---|---|
| Auth / RBAC | duplicate email, wrong password, customer blocked from `/admin/*`, anonymous 401, customer cannot self-assign `emergency` |
| Join | token numbering, duplicate active token → 409, other service allowed, position/ahead counting across shared counters, **fallback estimate labelled and without a fake range**, arrival window ordering |
| Lifecycle | call → start → complete, service record and wait computed, notifications created, rejoin allowed after completion |
| Fairness | priority customer jumps the queue; calling out of order is refused without a reason and **audited** when a reason is given |
| Privacy | other customer's token → 404 for read and cancel |
| Cancel | positions update automatically |
| No-show | cooldown blocks immediate rejoin; closed counter cannot call |
| Degradation | no open counter → `method:"unavailable"`, no invented number, critical alert with “open counter” action |
| Admin | counter CRUD + conflicts, RBAC on counters, settings validation |
| Reports | JSON, CSV and a valid PDF |
| WebSocket | bad token rejected; authenticated client receives pushes after a join |
| Organizations | admin creates a hospital from a template; services/counters/queues isolated per organization; customers pick an organization and join there; staff pinned to their own organization and blocked from others' tokens; service add/pause hides from customers; deactivation and last-active guard; hours/timezone/type validation and audit |
| Feature contract | `compute_wait_features` and the fallback formula on a hand-built case |

Also verified manually (local, seeded SQLite, ML on): all analytics endpoints, join with an ML estimate and range, and the browser flows — admin overview, live queue, forecast & alerts, customer home and live token page.

## What has NOT been tested

* **Anything executed against Supabase/Postgres** (partial unique indexes, enums, identity columns, pooler settings). Only static checks were done: the migration parses with `pglast`, and the ORM models compile to PostgreSQL DDL with the same 16 tables. Run the migration and `pytest` with `DATABASE_URL` pointing at a throw-away Supabase/Postgres to confirm.
* Frontend automated tests (none written), cross-browser, screen-reader pass, and mobile/tablet layouts (responsive classes and a bottom nav exist, but they were not viewed on a small screen).
* Load / concurrency (simultaneous joins on Postgres, WebSocket fan-out), FCM delivery, deployment on Render/Vercel.
* Model accuracy on real data (none exists yet).

## Suggested next tests

1. `pytest` against Postgres (set `DATABASE_URL`, `AUTO_CREATE_TABLES=false`, apply the migration first).
2. Concurrency: 50 parallel `POST /queue/join` for distinct users → unique consecutive numbers, no 500s.
3. Playwright: register → join → staff calls → customer sees “It's your turn” without refresh.
4. ML: re-run `ml/train_wait_time.py` with several seeds; check MAE spread and interval coverage stay stable.
