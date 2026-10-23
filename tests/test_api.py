from contextlib import contextmanager
from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from psycopg import OperationalError

from app.config import Settings
from app.main import create_app


@pytest.fixture
def api():
    conn = MagicMock()
    pool = MagicMock()

    @contextmanager
    def connection():
        yield conn

    pool.connection.side_effect = connection
    settings = Settings(_env_file=None, database_url="postgresql://test/test", demo_api_token="test-secret")
    with TestClient(create_app(settings, pool)) as client:
        yield client, conn


AUTH = {"Authorization": "Bearer test-secret"}
BASE = "/api/v1/customers/2"
MEASUREMENTS = BASE + "/meters/10/measurements"
INTERVAL = {"from": "2025-01-01T00:00:00", "to": "2025-01-02T00:00:00"}


def test_health_and_openapi(api):
    client, _ = api
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/openapi.json").status_code == 200


def test_authentication_and_customer_scope(api):
    client, conn = api
    assert client.get(BASE).status_code == 401
    assert client.get(BASE, headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert client.get("/api/v1/customers/3", headers=AUTH).status_code == 403
    conn.execute.assert_not_called()


def test_missing_customer_and_empty_connections(api):
    client, conn = api
    conn.execute.return_value.fetchone.return_value = None
    assert client.get(BASE, headers=AUTH).status_code == 404
    conn.execute.return_value.fetchone.return_value = {"data": {"customer_id": 2, "connections": []}}
    assert client.get(BASE + "/connections", headers=AUTH).json()["connections"] == []
    conn.execute.return_value.fetchone.return_value = {"data": None}
    assert client.get(BASE + "/meters", headers=AUTH).status_code == 404


@pytest.mark.parametrize("interval", [
    {"from": "2025-02-01", "to": "2025-01-01"},
    {"from": "2025-01-01", "to": "2025-03-01"},
    {"from": "2025-01-01T00:00:00Z", "to": "2025-01-02T00:00:00"},
    {"from": "bad", "to": "2025-01-02"},
])
def test_invalid_interval(api, interval):
    client, conn = api
    assert client.get(MEASUREMENTS, params=interval, headers=AUTH).status_code == 422
    conn.execute.assert_not_called()


def test_foreign_meter_never_queries_measurements(api):
    client, conn = api
    conn.execute.return_value.fetchone.return_value = {"data": {"connections": [{"meters": [{"measurement_meter_id": None}]}]}}
    assert client.get(MEASUREMENTS, params=INTERVAL, headers=AUTH).status_code == 404
    assert conn.execute.call_count == 1


def test_measurements_preserve_precision_duplicates_and_boundaries(api):
    client, conn = api
    conn.execute.return_value.fetchone.return_value = {"data": {"connections": [{"meters": [{"measurement_meter_id": 10}]}]}}
    row = {"meter_id": 10, "observed_at": datetime(2025, 1, 1), "energy_kwh": Decimal("1.1234567890123456789"), "source_file_id": 1}
    conn.execute.return_value.fetchall.return_value = [row, row]
    response = client.get(MEASUREMENTS, params=INTERVAL, headers=AUTH)
    assert response.status_code == 200
    assert len(response.json()["items"]) == 2
    assert response.json()["items"][0]["energy_kwh"] == "1.1234567890123456789"
    sql, params = conn.execute.call_args.args
    assert "observed_at >= %s AND observed_at < %s" in sql
    assert params == (10, datetime(2025, 1, 1), datetime(2025, 1, 2), 10001)
    limited = client.get(MEASUREMENTS, params={**INTERVAL, "limit": 1}, headers=AUTH).json()
    assert limited["truncated"] is True
    assert len(limited["items"]) == 1


def test_database_outage_hides_details(api):
    client, conn = api
    conn.execute.side_effect = OperationalError("secret connection details")
    response = client.get("/ready")
    assert response.status_code == 503
    assert "secret" not in response.text


def test_no_configured_token_is_locked():
    settings = Settings(_env_file=None, database_url="postgresql://test/test", demo_api_token="")
    with TestClient(create_app(settings, MagicMock())) as client:
        assert client.get(BASE, headers=AUTH).status_code == 401
