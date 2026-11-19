# QueueLess

**Know When to Arrive. Skip the Wait.** — predictive queue management: virtual queue, ML waiting-time prediction with uncertainty, smart arrival windows, demand forecasting and rule-based congestion advice for service centres. Database: **Supabase (PostgreSQL)**.

## What works today

| Area | Status |
|---|---|
| Customer app: register/login, service discovery with live estimates, join/cancel, live token tracking (WebSocket), ML wait + range, arrival window, notifications, history, profile | ✅ |
| Staff/admin: live queue (call/start/complete/no-show/cancel/override, audited), counters & staff, settings/thresholds, audit log | ✅ |
| Analytics: KPIs, hourly/daily/weekly/monthly traffic, waits, utilization, queue length, predicted-vs-actual arrivals, daily report (JSON/CSV/PDF) | ✅ |
| ML: discrete-event simulator, **waiting-time** benchmark (LR/RF/GBR/XGB, MAE-selected, calibrated 80 % interval), **demand forecast** 30/60/120 min, registry, retraining script | ✅ trained on **simulated** data |
| **Organizations:** admin adds hospitals / colleges / banks / government centres / other (typed templates), switches between them, manages each one's services; customers choose where to go | ✅ |
| Rule engine + greedy counter allocation, actionable alerts (admin clicks “apply”) | ✅ |
| Non-ML fallback when no model / no model result (labelled, no fake range) | ✅ |
| Supabase schema with RLS locked down | ✅ written, **not yet run on a live Supabase** |
| FCM push | 🟡 server adapter only (needs your Firebase project + web client) |
| No-show model, digital-twin UI, multi-location UI | ⏳ roadmap (`docs/05`) |

**Read this:** the bundled models and every accuracy number come from a simulator. They prove the pipeline works, not that predictions will be accurate at your site. The UI labels estimates “trained on simulated data”, and the *ML monitoring* page separates real-customer accuracy (empty until real services are completed) from demo data.

## Interface

Palette: `#aec3b0` sage · `#eff6e0` cream · `#598392` teal · `#124559` deep teal · `#01161e` ink (tokens in `frontend/src/index.css`). Type: Inter for text, Space Grotesk for headings. Admin shell has a full sidebar with live badges and an honest model-status note; the overview has a live "Right now" panel with a one-click recommended action; live queue has a selected-token panel with its event timeline; customer screens are mobile-first with a range bar for the wait estimate and a bottom-sheet join flow.

## Quick start (local, no Supabase needed — uses SQLite)

Requirements: Python 3.11+, Node 20+.

```bash
# 1. Backend
cd backend
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m scripts.seed_demo                           # flagged demo data (is_demo=true)
uvicorn app.main:app --reload                         # API http://localhost:8000  ·  docs /docs

# 2. Frontend (new terminal)
cd frontend
cp .env.example .env
npm install && npm run dev                            # http://localhost:5173
```

Demo accounts (created only by the seed script; password = `DEMO_PASSWORD`, default `Demo@12345`):
`admin@queueless.demo` (admin) · `staff1@queueless.demo` … `staff4@…` (staff) · `customer1@queueless.demo` … `customer130@…` (customers). Change or delete them before any real deployment.

## Use Supabase as the database

1. Create a Supabase project, run `supabase/migrations/0001_queueless_schema.sql`, then `0002_organizations.sql`, in the SQL editor.
2. Put the connection string in `backend/.env` → `DATABASE_URL` and set `JWT_SECRET`.
3. `python -m scripts.seed_demo` (optional) and `uvicorn app.main:app`.

Full steps, pooler notes, Docker and Render/Vercel deployment: [`docs/07-DEPLOYMENT.md`](docs/07-DEPLOYMENT.md).

## ML workflows

```bash
python ml/train_wait_time.py      # simulate → clean → benchmark → calibrate → backend/models/ + ml/reports/
python ml/train_demand.py         # 30/60/120-min demand models
python ml/retrain_wait_time.py    # Phase 2: gated retraining on REAL data (refuses below 2,000 labelled rows)
```

Reports: `ml/reports/wait_time_report.md`, `ml/reports/demand_report.md`. Pipeline design: [`docs/04-ML-PIPELINE.md`](docs/04-ML-PIPELINE.md).

## Tests

```bash
cd backend && python -m pytest -q          # 17 tests, SQLite, ML off
```
Details and gaps: [`docs/08-TESTING.md`](docs/08-TESTING.md).

## Documentation

| | |
|---|---|
| [01 PRD](docs/01-PRD.md) | requirements, definitions, assumptions, gaps |
| [02 Architecture](docs/02-ARCHITECTURE.md) | components, flows, security, folder structure |
| [03 Database](docs/03-DATABASE.md) | ER diagram, deviations from the brief, integrity rules |
| [04 ML pipeline](docs/04-ML-PIPELINE.md) | simulator, models, calibration, retraining |
| [05 Tasks](docs/05-TASK-BREAKDOWN.md) | phased plan with dependencies and status |
| [06 API](docs/06-API.md) | endpoint reference (live OpenAPI at `/docs`) |
| [07 Deployment](docs/07-DEPLOYMENT.md) | Supabase, Docker, Render/Vercel |
| [08 Testing](docs/08-TESTING.md) | what was and was not verified |

## Key design decisions

* **Predictions never decide who is served.** Order = priority category, then joining time. Out-of-order calls need a recorded reason.
* **Honest uncertainty.** ML estimates show an empirical 80 % range; fallback estimates show none; “no counter open” shows no number at all.
* **One feature implementation** (`backend/app/ml/features.py`) is used by the simulator, training and the live API — no train/serve skew.
* **Backend is the only door to the data**: Supabase RLS is on with no policies; JWT + RBAC in the API.
* **Demo ≠ real**: `is_demo` flags, a banner in the UI, separate accuracy figures, and retraining ignores demo rows.
