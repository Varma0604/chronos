"""Benchmark a running Chronos API without hiding workload or failure details."""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time
import uuid

import httpx


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[round((len(ordered) - 1) * fraction)]


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8001")
    parser.add_argument("--tasks", type=int, default=300)
    parser.add_argument("--concurrency", type=int, default=15)
    parser.add_argument("--workers", type=int, required=True)
    parser.add_argument("--poll-interval", type=float, default=0.05)
    args = parser.parse_args()
    if args.tasks < 1 or args.concurrency < 1 or args.workers < 1:
        raise SystemExit("tasks, concurrency, and workers must all be positive")

    semaphore = asyncio.Semaphore(args.concurrency)
    submitted: list[tuple[str, float]] = []

    async with httpx.AsyncClient(base_url=args.base_url, timeout=30) as client:
        async def submit(index: int) -> None:
            async with semaphore:
                started = time.perf_counter()
                response = await client.post(
                    "/api/v1/tasks",
                    headers={"Idempotency-Key": f"benchmark-{uuid.uuid4()}"},
                    json={"kind": "sum", "payload": {"values": [index, 1]}, "priority": 5},
                )
                response.raise_for_status()
                submitted.append((response.json()["task_id"], started))

        wall_started = time.perf_counter()
        await asyncio.gather(*(submit(index) for index in range(args.tasks)))

        async def wait_for_result(task_id: str, started: float) -> tuple[str, float]:
            while True:
                response = await client.get(f"/api/v1/tasks/{task_id}")
                response.raise_for_status()
                status = response.json()["status"]
                if status in {"succeeded", "failed"}:
                    return status, (time.perf_counter() - started) * 1000
                await asyncio.sleep(args.poll_interval)

        outcomes = await asyncio.gather(*(wait_for_result(*item) for item in submitted))
        elapsed = time.perf_counter() - wall_started

    latencies = [latency for _, latency in outcomes]
    failed = sum(status == "failed" for status, _ in outcomes)
    print(json.dumps({
        "workload": {"tasks": args.tasks, "task_kind": "sum", "concurrent_submitters": args.concurrency,
                     "configured_workers": args.workers},
        "result": {"succeeded": args.tasks - failed, "failed": failed,
                   "wall_clock_seconds": round(elapsed, 3),
                   "completed_tasks_per_second": round(args.tasks / elapsed, 2),
                   "p50_end_to_end_ms": round(statistics.median(latencies), 2),
                   "p95_end_to_end_ms": round(percentile(latencies, 0.95), 2)},
    }, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
