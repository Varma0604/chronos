# Chronos

Chronos is a small durable task scheduler. A FastAPI service stores task definitions and state transitions in a configured SQL database, then places task IDs in a Redis sorted-set queue. A separate worker claims due tasks, runs a registered handler, and records the outcome. The Docker Compose deployment uses PostgreSQL and Redis; the local development default is SQLite.

## Run locally

```bash
docker compose up --build
```

The API is at `http://localhost:8001`; interactive docs are at `/docs`. Create an immediate task:

```bash
curl -X POST http://localhost:8001/api/v1/tasks \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: demo-sum-001' \
  -d '{"kind":"sum","payload":{"values":[2,3,5]},"priority":8,"max_attempts":3}'
```

Use `GET /api/v1/tasks/{task_id}` to follow execution and `GET /api/v1/tasks` for recent history. `kind` is currently `echo` or `sum`. Supply an ISO-8601 `run_at` value to schedule the task in the future.

## Reliability model

- Task state and payloads are stored in the configured SQL database; Redis is the due-work index. The Docker Compose deployment uses PostgreSQL, while the local development default is SQLite. The worker periodically repairs queued rows that were not enqueued after a process interruption.
- Idempotency keys prevent duplicate task creation for the same client request.
- Failed handlers retry with capped exponential backoff and transition to `failed` after `max_attempts`.
- A worker lease that remains `running` for over a minute is requeued. This is at-least-once execution: a handler can run again after a crash, so external handlers must be idempotent.
- Built-in handlers are deterministic demonstrations, not a general-purpose arbitrary-code execution environment. `echo` and `sum` support normal demos; the bounded `sleep` handler is used only for repeatable worker-crash recovery testing.
- **Recorded throughput benchmark (November 2, 2026):** three runs of 300
  deterministic `sum` tasks, 15 concurrent submitters, and three Docker
  workers completed all 900 tasks without failure. Median wall-clock time was
  **5.088 seconds** (**58.96 tasks/second**), with median P50/P95 end-to-end
  latencies of **3.35s / 4.48s**. This is a local-machine workload, not a
  production capacity claim.

## Development

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
pytest
```

GitHub Actions runs the test suite with PostgreSQL and Redis services.

## Repeatable Docker benchmark

After Docker Desktop is running, start the real stack with three workers:

```bash
docker compose up --build --scale worker=3
python scripts/benchmark.py --workers 3 --tasks 300 --concurrency 15
```

The benchmark submits deterministic `sum` tasks, waits for every task to reach
`succeeded` or `failed`, and prints a JSON record containing the workload,
configured worker count, throughput, latency percentiles, and failure count.
It does not infer the actual worker count from Docker; keep the `--workers`
value aligned with the Compose command used for that run.

## Worker-crash recovery demonstration

For a short, observable recovery test, start one worker with a ten-second
lease, then use the verification script:

```bash
WORKER_LEASE_SECONDS=10 docker compose up --build --scale worker=1
# In a second terminal with the Chronos virtual environment active:
python scripts/verify_worker_recovery.py --lease-seconds 10
```

The script submits a 30-second `sleep` task, kills the only worker after it
claims the task, starts a replacement, and verifies that the replacement
requeues and completes the task on a later attempt. This demonstrates
at-least-once processing; an external handler must therefore be idempotent.

**Recorded recovery verification (November 2, 2026):** one deliberately
terminated in-flight task was requeued and completed successfully on attempt 2
by a replacement worker.
