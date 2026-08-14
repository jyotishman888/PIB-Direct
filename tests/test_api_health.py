def test_health_returns_ok(api_client):
    client, _ = api_client

    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
