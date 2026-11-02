"""Prove that a task survives a killed Chronos worker in a running Compose stack."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
import uuid

import httpx


def wait_for(client: httpx.Client, task_id: str, expected: set[str], timeout_seconds: int) -> dict:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            response = client.get(f"/api/v1/tasks/{task_id}")
            response.raise_for_status()
            task = response.json()
            if task["status"] in expected:
                return task
        except httpx.RequestError:
            # Compose can briefly reset an existing HTTP connection while a
            # replacement worker is created; polling is intentionally resilient.
            pass
        time.sleep(0.25)
    raise TimeoutError(f"task {task_id} did not reach {sorted(expected)} within {timeout_seconds} seconds")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8001")
    parser.add_argument("--lease-seconds", type=int, default=10)
    args = parser.parse_args()
    if args.lease_seconds < 5:
        raise SystemExit("lease-seconds must be at least 5")
    compose_env = {**os.environ, "WORKER_LEASE_SECONDS": str(args.lease_seconds)}

    # Make the demonstration self-contained even if a previous Compose command
    # started the worker with the default 60-second lease.
    subprocess.run(
        ["docker", "compose", "up", "-d", "--no-deps", "--force-recreate", "--scale", "worker=1", "worker"],
        check=True,
        env=compose_env,
    )

    with httpx.Client(base_url=args.base_url, timeout=30) as client:
        response = client.post(
            "/api/v1/tasks",
            headers={"Idempotency-Key": f"recovery-demo-{uuid.uuid4()}"},
            json={"kind": "sleep", "payload": {"seconds": 30}, "priority": 9, "max_attempts": 2},
        )
        response.raise_for_status()
        task_id = response.json()["task_id"]
        running = wait_for(client, task_id, {"running"}, timeout_seconds=15)

        subprocess.run(["docker", "compose", "kill", "worker"], check=True)
        subprocess.run(
            ["docker", "compose", "up", "-d", "--no-deps", "--scale", "worker=1", "worker"],
            check=True,
            env=compose_env,
        )

        completed = wait_for(client, task_id, {"succeeded", "failed"}, timeout_seconds=args.lease_seconds + 45)

    if completed["status"] != "succeeded" or completed["attempts"] < 2:
        raise RuntimeError(f"recovery verification failed: {completed}")
    print(json.dumps({
        "task_id": task_id,
        "killed_worker_lease_owner": running["lease_owner"],
        "result": {"status": completed["status"], "attempts": completed["attempts"],
                   "result": completed["result"], "recovered": True},
    }, indent=2))


if __name__ == "__main__":
    main()
