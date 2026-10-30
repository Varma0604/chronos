from fastapi.testclient import TestClient

import app.main as api
from app.main import app


def test_task_creation_is_idempotent(monkeypatch):
    monkeypatch.setattr(api, "enqueue", lambda *_args: None)
    with TestClient(app) as client:
        first = client.post("/api/v1/tasks", headers={"Idempotency-Key": "sample-1"}, json={
            "kind": "sum", "payload": {"values": [3, 4]}, "priority": 7
        })
        second = client.post("/api/v1/tasks", headers={"Idempotency-Key": "sample-1"}, json={
            "kind": "sum", "payload": {"values": [3, 4]}, "priority": 7
        })
        assert first.status_code == 202
        assert second.status_code == 202
        assert first.json()["task_id"] == second.json()["task_id"]


def test_dead_letter_route_is_not_captured_as_a_task_id():
    with TestClient(app) as client:
        response = client.get("/api/v1/tasks/dead-letter")
    assert response.status_code == 200
    assert response.json() == []
