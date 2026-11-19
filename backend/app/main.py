import logging
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import get_settings
from .db import Base, SessionLocal, engine
from .routers import admin, analytics, auth, customer, ws
from .services import settings_service

settings = get_settings()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("queueless")


@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.jwt_secret == "change-me-in-.env" and not settings.is_sqlite:
        raise RuntimeError("Set JWT_SECRET in the environment before running against a real database.")
    if settings.is_sqlite or settings.auto_create_tables:
        from . import models  # noqa: F401  (register tables)
        Base.metadata.create_all(engine)
    with SessionLocal() as db:
        settings_service.get_location(db)
        db.commit()
    log.info("QueueLess API started (db=%s, ml=%s)", "sqlite" if settings.is_sqlite else "postgres", settings.ml_enabled)
    yield


app = FastAPI(title="QueueLess API", version="1.0.0", lifespan=lifespan,
              description="Predictive queue management: virtual queue, ML wait-time prediction, arrival windows, demand forecasts.")
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_list, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

_hits: dict[tuple[str, bool], deque] = defaultdict(deque)


@app.middleware("http")
async def rate_limit(request: Request, call_next):
    """Sliding-window limiter per client IP (in-memory: use Redis/edge limits when running several instances)."""
    if request.url.path in ("/health", "/docs", "/openapi.json"):
        return await call_next(request)
    is_auth = request.url.path.startswith("/auth/")
    limit = settings.auth_rate_limit_per_minute if is_auth else settings.rate_limit_per_minute
    ip = request.client.host if request.client else "unknown"
    q, now = _hits[(ip, is_auth)], time.monotonic()
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= limit:
        return JSONResponse({"detail": "Too many requests. Please slow down."}, status_code=429, headers={"Retry-After": "30"})
    q.append(now)
    return await call_next(request)


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    log.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse({"detail": "Internal server error"}, status_code=500)


@app.get("/health", tags=["meta"])
def health():
    from .ml import predictor
    return {"status": "ok", "ml_wait_model": (predictor.wait_model_info() or {}).get("version"), "demo_mode": settings.demo_mode}


for r in (auth.router, customer.router, admin.router, analytics.router, ws.router):
    app.include_router(r)
