from app.matching import match, scenarios
from test_api import api, AUTH


def test_time_overlap_and_price_limits():
    producer, daytime, evening, tdo, cheap = scenarios()
    good = match(producer, daytime)
    assert good["eligible"]
    assert good["score"] > match(producer, tdo)["score"]
    assert match(producer, evening)["shared_kwh"] == 0
    assert match(producer, cheap)["reason"] == "price_limit"
    for value, supply, demand in zip(good["interval_shared_kwh"], producer["profile_kwh"], daytime["profile_kwh"]):
        assert 0 <= value <= min(supply, demand)
    assert good["shared_kwh"] <= min(sum(producer["profile_kwh"]), sum(daytime["profile_kwh"]))


def test_demo_auth_ranking_and_no_database_access(api):
    client, conn = api
    base = "/api/v1/customers/2/demo"
    assert client.get(base + "/matches").status_code == 401
    assert client.get("/api/v1/customers/3/demo/matches", headers=AUTH).status_code == 403
    response = client.get(base + "/matches", headers=AUTH)
    assert response.status_code == 200
    body = response.json()
    assert body["data_source"] == "synthetic_demo"
    assert body["items"][0]["consumer_id"] == "day-home"
    assert len(client.get(base + "/scenarios", headers=AUTH).json()["items"]) == 5
    assert client.get(base + "/matches?scenario_id=unknown", headers=AUTH).status_code == 404
    assert client.get(base + "/matches?scenario_id=day-home", headers=AUTH).json()["items"][0]["producer_id"] == "solar-home"
    conn.execute.assert_not_called()
