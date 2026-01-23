from __future__ import annotations


def test_health_endpoint(openai_client):
    r = openai_client.get("/healthz")
    assert r.status_code == 200
    assert r.json().get("ok") is True

