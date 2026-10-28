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
