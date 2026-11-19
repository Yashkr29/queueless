from conftest import login, register

from app.ml.features import CounterState, QueuedToken, WaitSnapshotContext, compute_wait_features, fallback_wait_minutes


def join(client, h, service_id=1, priority="none"):
    return client.post("/queue/join", json={"service_id": service_id, "priority_type": priority}, headers=h)


def test_auth_and_rbac(client):
    h = register(client, 1)
    assert client.get("/auth/me", headers=h).json()["role"] == "customer"
    assert client.post("/auth/register", json={"name": "x", "email": "C1@test.dev", "password": "TestPass123"}).status_code == 409
    assert client.post("/auth/login", json={"email": "c1@test.dev", "password": "wrong-password"}).status_code == 401
    assert client.get("/admin/queue", headers=h).status_code == 403          # customer cannot use staff endpoints
    assert client.get("/admin/queue").status_code == 401                      # anonymous
    assert client.post("/queue/join", json={"service_id": 1, "priority_type": "emergency"}, headers=h).status_code == 422


def test_join_token_fallback_estimate_and_duplicates(client):
    h = register(client, 1)
    r = join(client, h)
    assert r.status_code == 201, r.text
    t = r.json()
    assert t["token_label"] == "G-001" and t["queue_position"] == 1 and t["customers_ahead"] == 0
    assert t["estimate"]["method"] == "fallback" and t["estimate"]["lower_minutes"] is None   # labelled non-ML, no fake range
    assert t["arrival_window"]["window_start"] <= t["arrival_window"]["recommended_arrival"] <= t["arrival_window"]["window_end"]
    assert join(client, h).status_code == 409                                  # duplicate active token
    assert join(client, h, service_id=2).status_code == 201                    # other service is fine
    h2 = register(client, 2)
    t2 = join(client, h2).json()
    # ahead = G-001 and D-001: Counter 1 serves both services, so the Documents token competes for the same counter
    assert t2["token_label"] == "G-002" and t2["customers_ahead"] == 2
    assert t2["estimate"]["wait_minutes"] > t["estimate"]["wait_minutes"]


def test_full_service_cycle_and_event_log(client):
    cust = register(client, 1)
    staff = login(client, "staff@test.dev")
    tid = join(client, cust).json()["token_id"]
    r = client.post("/admin/queue/call-next", json={"counter_id": 1}, headers=staff)
    assert r.status_code == 200, r.text
    assert client.get(f"/queue/{tid}", headers=cust).json()["status"] == "called"
    assert client.post(f"/admin/queue/{tid}/start", headers=staff).status_code == 200
    assert client.post(f"/admin/queue/{tid}/complete", headers=staff).status_code == 200
    t = client.get(f"/queue/{tid}", headers=cust).json()
    assert t["status"] == "completed" and t["estimate"] is None
    notes = client.get("/notifications", headers=cust).json()["items"]
    assert {"token_generated", "counter_assigned"} <= {n["notification_type"] for n in notes}
    ov = client.get("/analytics/overview", headers=staff).json()
    assert ov["served_today"] == 1 and ov["currently_waiting"] == 0
    # same customer may rejoin after completion
    assert join(client, cust).status_code == 201


def test_priority_order_and_out_of_order_override_is_audited(client):
    regular, senior = register(client, 1), register(client, 2)
    staff, admin = login(client, "staff@test.dev"), login(client, "admin@test.dev")
    t_reg = join(client, regular).json()
    t_sen = join(client, senior, priority="senior").json()
    assert t_sen["queue_position"] == 1 and client.get(f"/queue/{t_reg['token_id']}", headers=regular).json()["customers_ahead"] == 1
    # calling the regular customer first is out of order -> needs a reason
    r = client.post(f"/admin/queue/{t_reg['token_id']}/call", json={"counter_id": 1}, headers=staff)
    assert r.status_code == 409
    r = client.post(f"/admin/queue/{t_reg['token_id']}/call", json={"counter_id": 1, "override_reason": "Customer has a train to catch"}, headers=staff)
    assert r.status_code == 200
    audit = client.get("/admin/audit", headers=admin).json()["items"]
    assert any(a["action"] == "call_out_of_order" and a["details"]["reason"] for a in audit)


def test_cancel_updates_positions_and_privacy(client):
    a, b = register(client, 1), register(client, 2)
    ta, tb = join(client, a).json(), join(client, b).json()
    assert client.get(f"/queue/{ta['token_id']}", headers=b).status_code == 404          # other customers' tokens are invisible
    assert client.post(f"/queue/{ta['token_id']}/cancel", headers=b).status_code == 404
    assert client.post(f"/queue/{ta['token_id']}/cancel", headers=a).json()["status"] == "cancelled"
    assert client.get(f"/queue/{tb['token_id']}", headers=b).json()["queue_position"] == 1


def test_no_show_cooldown_and_counter_rules(client):
    cust, staff = register(client, 1), login(client, "staff@test.dev")
    tid = join(client, cust).json()["token_id"]
    client.post("/admin/queue/call-next", json={"counter_id": 1}, headers=staff)
    assert client.post(f"/admin/queue/{tid}/no-show", headers=staff).status_code == 200
    r = join(client, cust)
    assert r.status_code == 409 and "rejoin" in r.json()["detail"]
    assert client.post("/admin/queue/call-next", json={"counter_id": 2}, headers=staff).status_code == 409   # closed counter


def test_no_open_counter_gives_unavailable_not_fake_estimate(client):
    admin, cust = login(client, "admin@test.dev"), register(client, 1)
    assert client.patch("/admin/counters/1", json={"status": "closed"}, headers=admin).status_code == 200
    t = join(client, cust).json()
    assert t["estimate"]["method"] == "unavailable" and t["estimate"]["wait_minutes"] is None and t["arrival_window"] is None
    alerts = client.get("/admin/alerts", headers=admin).json()["alerts"]
    assert any(a["type"] == "no_counter_available" and a["action"]["type"] == "open_counter" for a in alerts)


def test_counter_admin_and_settings(client):
    admin, staff = login(client, "admin@test.dev"), login(client, "staff@test.dev")
    r = client.post("/admin/counters", json={"counter_name": "Counter 3", "status": "open", "service_ids": [1, 2]}, headers=admin)
    assert r.status_code == 201 and r.json()["service_ids"] == [1, 2]
    assert client.post("/admin/counters", json={"counter_name": "Counter 3"}, headers=admin).status_code == 409
    assert client.post("/admin/counters", json={"counter_name": "X"}, headers=staff).status_code == 403
    assert client.patch("/admin/settings", json={"values": {"wait_threshold_minutes": 12}}, headers=admin).json()["settings"]["wait_threshold_minutes"] == 12
    assert client.patch("/admin/settings", json={"values": {"nope": 1}}, headers=admin).status_code == 422


def test_reports_csv_pdf(client):
    staff = login(client, "staff@test.dev")
    assert client.get("/analytics/reports/daily", headers=staff).status_code == 200
    csv = client.get("/analytics/reports/daily?format=csv", headers=staff)
    assert csv.status_code == 200 and "QueueLess daily report" in csv.text
    pdf = client.get("/analytics/reports/daily?format=pdf", headers=staff)
    assert pdf.content[:4] == b"%PDF"


def test_websocket_requires_auth_and_pushes_updates(client):
    from starlette.websockets import WebSocketDisconnect
    import pytest
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "auth", "token": "garbage"})
            ws.receive_json()
    cust = register(client, 1)
    token = cust["Authorization"].split()[1]
    with client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "auth", "token": token})
        assert ws.receive_json()["type"] == "ready"
        join(client, cust)
        types = {ws.receive_json()["type"] for _ in range(2)}
        assert "token_update" in types or "notification" in types


def test_feature_contract_and_fallback_formula():
    q = [QueuedToken(i, 1, 2, float(i)) for i in range(5)]
    counters = [CounterState(1, frozenset({1}), True, True), CounterState(2, frozenset({1}), True, False), CounterState(3, frozenset({2}), False, False)]
    f = compute_wait_features(q[3], q, counters, WaitSnapshotContext(10, 2, 6.0, 20.0))
    assert f["customers_ahead"] == 3 and f["queue_length"] == 4 and f["active_counters"] == 2 and f["busy_counters"] == 1
    assert abs(f["staff_availability"] - 2 / 3) < 1e-3
    assert fallback_wait_minutes(f) == round(3 / 2 * 6 + 0.5 * 3, 2)
    f0 = compute_wait_features(q[0], q, [CounterState(3, frozenset({2}), True)], WaitSnapshotContext(10, 2, 6.0, 20.0))
    assert fallback_wait_minutes(f0) is None
