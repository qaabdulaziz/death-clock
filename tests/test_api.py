from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DEATHCLOCK_DB_PATH", str(tmp_path / "test.db"))
    from app import db
    from app.main import app

    db.reset_connection()
    with TestClient(app) as test_client:
        yield test_client
    db.reset_connection()


def test_first_run_creates_only_default_settings(client: TestClient):
    response = client.get("/api/settings")
    assert response.status_code == 200
    assert response.json() == {
        "id": 1,
        "date_of_birth": None,
        "life_expectancy_years": 80.0,
        "starting_balance": 0.0,
        "monthly_contribution": 0.0,
        "annual_return_rate": 7.0,
        "currency": "USD",
        "setup_complete": False,
    }
    assert client.get("/api/projects").json() == []


def test_settings_support_partial_updates_and_normalize_currency(client: TestClient):
    response = client.put("/api/settings", json={"currency": " eur ", "monthly_contribution": 250})

    assert response.status_code == 200
    assert response.json()["currency"] == "EUR"
    assert response.json()["monthly_contribution"] == 250.0
    assert response.json()["life_expectancy_years"] == 80.0


def test_settings_reject_invalid_currency_and_life_expectancy(client: TestClient):
    assert client.put("/api/settings", json={"currency": "US"}).status_code == 422
    assert client.put("/api/settings", json={"life_expectancy_years": 0}).status_code == 422
    assert client.put("/api/settings", json={"life_expectancy_years": 151}).status_code == 422
    assert client.put("/api/settings", json={"annual_return_rate": 101}).status_code == 422
    assert client.put("/api/settings", json={"starting_balance": 1e16}).status_code == 422
    assert client.put(
        "/api/settings",
        json={"date_of_birth": "9999-12-31", "life_expectancy_years": 150},
    ).status_code == 422


def test_setup_cannot_be_completed_without_a_birth_date(client: TestClient):
    response = client.put("/api/settings", json={"setup_complete": True})
    assert response.status_code == 422
    assert client.get("/api/settings").json()["setup_complete"] is False


def test_birth_date_can_be_cleared(client: TestClient):
    client.put(
        "/api/settings",
        json={"date_of_birth": "2000-01-01", "setup_complete": True},
    )
    response = client.put("/api/settings", json={"date_of_birth": None})
    assert response.status_code == 200
    assert response.json()["date_of_birth"] is None
    assert response.json()["setup_complete"] is False


def test_project_crud(client: TestClient):
    created = client.post("/api/projects", json={"name": "Plan", "cost": 500})
    assert created.status_code == 201
    project_id = created.json()["id"]

    listed = client.get("/api/projects").json()
    assert len(listed) == 1
    assert listed[0]["name"] == "Plan"

    updated = client.put(f"/api/projects/{project_id}", json={"name": "Updated", "cost": 450})
    assert updated.status_code == 200
    assert updated.json()["cost"] == 450.0

    assert client.delete(f"/api/projects/{project_id}").status_code == 204
    assert client.get("/api/projects").json() == []


def test_project_validation_and_missing_ids(client: TestClient):
    assert client.post("/api/projects", json={"name": "", "cost": 1}).status_code == 422
    assert client.post("/api/projects", json={"name": "Plan", "cost": -1}).status_code == 422
    assert client.put("/api/projects/999", json={"name": "Plan", "cost": 1}).status_code == 404
    assert client.delete("/api/projects/999").status_code == 404


def test_projection_endpoint_recomputes_after_project_changes(client: TestClient):
    client.put(
        "/api/settings",
        json={
            "date_of_birth": "2000-01-01",
            "life_expectancy_years": 80,
            "starting_balance": 0,
            "monthly_contribution": 100,
            "annual_return_rate": 0,
            "setup_complete": True,
        },
    )
    project = client.post("/api/projects", json={"name": "Plan", "cost": 100}).json()

    projection = client.get("/api/projection")
    assert projection.status_code == 200
    computed = next(item for item in projection.json()["projects"] if item["id"] == project["id"])
    assert computed["start_month"] is not None


def test_projection_requires_a_birth_date(client: TestClient):
    response = client.get("/api/projection")
    assert response.status_code == 409


def test_reset_wipes_projects_and_restores_defaults(client: TestClient):
    client.put("/api/settings", json={"currency": "EUR", "setup_complete": True})
    client.post("/api/projects", json={"name": "Plan", "cost": 10})

    response = client.post("/api/reset")

    assert response.status_code == 200
    assert response.json()["setup_complete"] is False
    assert response.json()["currency"] == "USD"
    assert client.get("/api/projects").json() == []


def test_cross_origin_reset_is_rejected(client: TestClient):
    response = client.post(
        "/api/reset",
        headers={"Origin": "https://unrelated.invalid"},
    )
    assert response.status_code == 403


def test_dns_rebinding_host_is_rejected(client: TestClient):
    invalid_hosts = (
        "rebind.attacker.invalid",
        "[::1]attacker.invalid",
        "attacker.invalid@localhost",
        "localhost:evil",
        "::1",
        "[::1]:evil",
        "localhost:0",
        "localhost:65536",
    )
    for host in invalid_hosts:
        response = client.post(
            "/api/reset",
            headers={"Host": host, "Origin": f"http://{host}"},
        )
        assert response.status_code == 400


def test_local_ipv4_ipv6_and_hostname_authorities_are_allowed(client: TestClient):
    for host in ("localhost:8000", "127.0.0.1:8000", "[::1]:8000", "testserver"):
        assert client.get("/api/settings", headers={"Host": host}).status_code == 200


def test_frontend_is_served(client: TestClient):
    response = client.get("/")
    assert response.status_code == 200
    assert "Death Clock" in response.text
