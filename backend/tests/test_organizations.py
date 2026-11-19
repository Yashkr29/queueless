from conftest import login, register


def H(h, loc):
    return {**h, "X-Location-Id": str(loc)}


def make_org(client, admin, name="City Hospital", kind="hospital", **extra):
    r = client.post("/admin/locations", json={"name": name, "location_type": kind, **extra}, headers=admin)
    assert r.status_code == 201, r.text
    return r.json()


def test_admin_creates_hospital_from_template(client):
    admin = login(client, "admin@test.dev")
    org = make_org(client, admin)
    assert org["location_type"] == "hospital" and org["services"] == 4 and org["counters"] == 4
    assert org["open_time"] == "08:00" and org["close_time"] == "20:00"
    assert org["created"] == {"services": 4, "counters": 4}
    # its services are isolated from the first organization's
    mine = client.get("/services", headers=H(admin, org["location_id"])).json()
    assert {s["service"]["service_name"] for s in mine} >= {"General OPD", "Pharmacy"}
    first = client.get("/services", headers=H(admin, 1)).json()
    assert {s["service"]["service_name"] for s in first} == {"General Enquiry", "Documents"}
    counters = client.get("/admin/counters", headers=H(admin, org["location_id"])).json()
    assert len(counters) == 4 and all(c["status"] == "closed" and len(c["service_ids"]) == 2 for c in counters)


def test_empty_org_and_validation(client):
    admin, staff, cust = login(client, "admin@test.dev"), login(client, "staff@test.dev"), register(client, 1)
    org = make_org(client, admin, "Blank College", "college", use_template=False)
    assert org["services"] == 0 and org["counters"] == 0
    assert client.post("/admin/locations", json={"name": "Blank College", "location_type": "bank"}, headers=admin).status_code == 409
    assert client.post("/admin/locations", json={"name": "X Bank", "location_type": "bank", "timezone": "Mars/Base"}, headers=admin).status_code == 422
    assert client.post("/admin/locations", json={"name": "X Bank", "location_type": "bank", "open_time": "18:00", "close_time": "09:00"}, headers=admin).status_code == 422
    assert client.post("/admin/locations", json={"name": "X Bank", "location_type": "zoo"}, headers=admin).status_code == 422
    assert client.post("/admin/locations", json={"name": "Nope Bank", "location_type": "bank"}, headers=staff).status_code == 403
    assert client.post("/admin/locations", json={"name": "Nope Bank", "location_type": "bank"}, headers=cust).status_code == 403


def test_customer_sees_active_orgs_and_joins_in_the_right_one(client):
    admin, cust = login(client, "admin@test.dev"), register(client, 1)
    org = make_org(client, admin, "Metro Bank", "bank")
    assert client.patch("/admin/counters/%d" % client.get("/admin/counters", headers=H(admin, org["location_id"])).json()[0]["counter_id"],
                        json={"status": "open"}, headers=H(admin, org["location_id"])).status_code == 200
    locs = client.get("/locations", headers=cust).json()
    assert [l["name"] for l in locs] == ["Main Service Centre", "Metro Bank"]
    svc = client.get("/services", headers=H(cust, org["location_id"])).json()[0]["service"]
    t = client.post("/queue/join", json={"service_id": svc["service_id"]}, headers=H(cust, org["location_id"]))
    assert t.status_code == 201, t.text
    assert t.json()["estimate"]["method"] in ("fallback", "unavailable")
    # the same customer can hold a token at the other organization too, and the lists do not leak across
    t2 = client.post("/queue/join", json={"service_id": 1}, headers=cust)
    assert t2.status_code == 201
    mine = client.get("/queue/mine", headers=cust).json()
    assert {x["token_label"][0] for x in mine} == {"G", "C"} or len(mine) == 2
    # queue size / positions are per organization
    assert client.get("/admin/queue", headers=H(admin, org["location_id"])).json()["total"] == 1
    assert client.get("/admin/queue", headers=H(admin, 1)).json()["total"] == 1


def test_staff_are_pinned_to_their_own_organization(client):
    admin, staff, cust = login(client, "admin@test.dev"), login(client, "staff@test.dev"), register(client, 1)
    org = make_org(client, admin, "Gov Centre", "government")
    # header is ignored for staff: they still see only their own organization
    assert client.get("/admin/counters", headers=H(staff, org["location_id"])).json()[0]["counter_name"] == "Counter 1"
    assert [l["name"] for l in client.get("/admin/locations", headers=staff).json()] == ["Main Service Centre"]
    svc = client.get("/services", headers=H(cust, org["location_id"])).json()[0]["service"]
    # open a counter there so the join succeeds, then try to operate on that token as the first org's staff
    cid = client.get("/admin/counters", headers=H(admin, org["location_id"])).json()[0]["counter_id"]
    client.patch(f"/admin/counters/{cid}", json={"status": "open"}, headers=H(admin, org["location_id"]))
    tid = client.post("/queue/join", json={"service_id": svc["service_id"]}, headers=H(cust, org["location_id"])).json()["token_id"]
    assert client.post(f"/admin/queue/{tid}/cancel", headers=staff).status_code == 404
    assert client.post(f"/admin/queue/{tid}/cancel", headers=admin).status_code == 200      # admin may act on any organization


def test_service_management_and_deactivation(client):
    admin, cust = login(client, "admin@test.dev"), register(client, 1)
    org = make_org(client, admin, "Study Hub", "college", use_template=False)
    ha = H(admin, org["location_id"])
    r = client.post("/admin/services", json={"service_name": "Library Desk", "code": "lb", "average_service_duration": 4}, headers=ha)
    assert r.status_code == 201 and r.json()["code"] == "LB"
    assert client.post("/admin/services", json={"service_name": "Library Desk", "code": "LD"}, headers=ha).status_code == 409
    sid = r.json()["service_id"]
    assert client.patch(f"/admin/services/{sid}", json={"average_service_duration": 6, "status": "paused"}, headers=ha).json()["status"] == "paused"
    assert client.get("/services", headers=H(cust, org["location_id"])).json() == []                 # paused services are hidden from customers
    assert len(client.get("/admin/services", headers=ha).json()) == 1                                 # but admins still see them
    # deactivating an organization hides it and blocks joins; the last active one cannot be deactivated
    assert client.patch(f"/admin/locations/{org['location_id']}", json={"is_active": False}, headers=admin).json()["is_active"] is False
    assert [l["name"] for l in client.get("/locations", headers=cust).json()] == ["Main Service Centre"]
    assert client.patch("/admin/locations/1", json={"is_active": False}, headers=admin).status_code == 409


def test_location_hours_and_templates_endpoint(client):
    admin = login(client, "admin@test.dev")
    tpl = client.get("/admin/location-templates", headers=admin).json()
    assert set(tpl) == {"hospital", "college", "bank", "government", "other"} and len(tpl["hospital"]["services"]) == 4
    org = make_org(client, admin, "Night Clinic", "hospital", open_time="18:00", close_time="23:00")
    assert (org["open_time"], org["close_time"]) == ("18:00", "23:00")
    upd = client.patch(f"/admin/locations/{org['location_id']}", json={"name": "Night Clinic 24", "close_time": "23:30", "address": "12 Main Rd"}, headers=admin).json()
    assert upd["name"] == "Night Clinic 24" and upd["close_time"] == "23:30" and upd["address"] == "12 Main Rd"
    audit = client.get("/admin/audit", headers=admin).json()["items"]
    assert {"location_created", "location_updated"} <= {a["action"] for a in audit}
