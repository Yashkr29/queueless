import os
import tempfile
from pathlib import Path

# Must be set before the app is imported: isolated SQLite DB, ML disabled by default (deterministic fallback tests).
_tmp = Path(tempfile.mkdtemp(prefix="queueless_test_"))
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp / 'test.db'}"
os.environ["ML_ENABLED"] = "false"
os.environ["RATE_LIMIT_PER_MINUTE"] = "100000"
os.environ["AUTH_RATE_LIMIT_PER_MINUTE"] = "100000"
os.environ["DEMO_MODE"] = "true"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Counter, CounterService, CounterStatus, Role, Service, Staff, User  # noqa: E402
from app.security import hash_password  # noqa: E402
from app.services import settings_service  # noqa: E402
from app.engine import queue_engine  # noqa: E402

PASSWORD = "TestPass123"


@pytest.fixture()
def client():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    queue_engine.clear_caches()
    with SessionLocal() as db:
        loc = settings_service.get_location(db)
        s1 = Service(location_id=loc.location_id, service_name="General Enquiry", code="G", average_service_duration=6)
        s2 = Service(location_id=loc.location_id, service_name="Documents", code="D", average_service_duration=12)
        db.add_all([s1, s2]); db.flush()
        admin = User(name="Admin", email="admin@test.dev", password_hash=hash_password(PASSWORD), role=Role.admin)
        staff_u = User(name="Sam Staff", email="staff@test.dev", password_hash=hash_password(PASSWORD), role=Role.staff)
        db.add_all([admin, staff_u]); db.flush()
        st = Staff(user_id=staff_u.user_id, location_id=loc.location_id); db.add(st); db.flush()
        c1 = Counter(location_id=loc.location_id, counter_name="Counter 1", status=CounterStatus.open, assigned_staff_id=st.staff_id)
        c2 = Counter(location_id=loc.location_id, counter_name="Counter 2", status=CounterStatus.closed)
        db.add_all([c1, c2]); db.flush()
        db.add_all([CounterService(counter_id=c1.counter_id, service_id=s1.service_id), CounterService(counter_id=c1.counter_id, service_id=s2.service_id),
                    CounterService(counter_id=c2.counter_id, service_id=s1.service_id)])
        db.commit()
    with TestClient(app) as c:
        yield c


def login(client, email, password=PASSWORD):
    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def register(client, n: int):
    r = client.post("/auth/register", json={"name": f"Cust {n}", "email": f"c{n}@test.dev", "password": PASSWORD})
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}
