# QueueLess — Supabase setup & deployment

> I could not create or reach your Supabase project from the build environment, so **nothing here has been run against Supabase**. The app and seed script were exercised only against the local SQLite fallback. The migration was checked with the PostgreSQL parser (`pglast`: valid syntax, 42 statements) and the SQLAlchemy models were compiled for the PostgreSQL dialect (16 tables, matching the SQL) — but it has **not been executed on a Postgres server**. Run steps 1–3 and fix anything Postgres reports before deploying.

## 1. Create the database in Supabase

1. supabase.com → **New project** (pick a region near your users; save the database password).
2. **SQL Editor → New query**, paste `supabase/migrations/0001_queueless_schema.sql`, **Run**; then the same for `0002_organizations.sql` (organization types, staff location). (Or `supabase link` + `supabase db push`.)
3. **Project Settings → Database → Connection string**. Choose one:
   * **Session pooler / direct (port 5432)** — simplest for a long-running API container.
   * **Transaction pooler (port 6543)** — for serverless; the app auto-disables prepared statements when it sees `:6543`.
   Copy the URI and put it in `backend/.env` as `DATABASE_URL` (`postgresql://…` is rewritten to the psycopg3 driver automatically).

Security notes: the migration enables **RLS on every table with no policies**, so the Supabase anon/authenticated REST API can read nothing. Never put the `service_role` key or DB password in the frontend. The frontend only knows `VITE_API_URL`.

## 2. Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                      # fill DATABASE_URL, JWT_SECRET, CORS_ORIGINS
python -m scripts.seed_demo                               # optional: flagged demo data
uvicorn app.main:app --reload                             # http://localhost:8000/docs
```

Generate a secret: `python -c "import secrets;print(secrets.token_urlsafe(48))"`. With a non-SQLite database the API **refuses to start** with the placeholder `JWT_SECRET`.

Create the first real admin (no demo seed): insert a user with role `admin` using a bcrypt hash — e.g.

```bash
python - <<'PY'
from app.db import SessionLocal; from app.models import User, Role; from app.security import hash_password
with SessionLocal() as db:
    db.add(User(name="Admin", email="you@example.com", password_hash=hash_password("choose-a-strong-one"), role=Role.admin)); db.commit()
PY
```

## 3. Frontend

```bash
cd frontend && cp .env.example .env     # VITE_API_URL=http://localhost:8000
npm install && npm run dev               # http://localhost:5173
```

## 4. Docker (local or any container host)

```bash
cp .env.example .env        # DATABASE_URL (Supabase), JWT_SECRET, CORS_ORIGINS
docker compose up --build   # api :8000, web :8080
```

The database is Supabase, so compose has no Postgres container. `backend/models/` is mounted read-only so you can swap trained models without rebuilding.

## 5. Cloud deployment

| Piece | Where | Settings |
|---|---|---|
| Database | Supabase | step 1 |
| API | Render / Railway / Fly (Docker) | root `backend/`, env: `DATABASE_URL`, `JWT_SECRET`, `CORS_ORIGINS=https://<your-web-domain>`, `DEMO_MODE=false` for pilots. Start: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`. **Single instance** (in-memory WebSocket hub + rate limiter) |
| Web | Vercel | root `frontend/`, build `npm run build`, output `dist`, env `VITE_API_URL=https://<api-domain>`; `vercel.json` provides the SPA rewrite |
| Push (optional) | Firebase | create a service account JSON, mount it, set `FCM_CREDENTIALS_FILE`; add Firebase web SDK + service worker to the frontend to register tokens via `POST /notifications/devices` |

Checklist before a pilot: strong `JWT_SECRET`; HTTPS everywhere (WebSockets become `wss://` automatically from `https://` API URLs); `CORS_ORIGINS` exact; `DEMO_MODE=false` and **no demo seed** in the production database; Supabase backups enabled; rotate the DB password if it was ever pasted anywhere insecure.

## 6. Scaling beyond one instance (not built)

WebSocket hub → Supabase Realtime or Redis pub/sub; rate limiter → Redis; scheduled jobs (forecast back-fill, retraining checks) → cron / Supabase scheduled functions.
