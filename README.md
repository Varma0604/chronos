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
- Built-in handlers are deterministic demonstrations, not a general-purpose arbitrary-code execution environment.
- No throughput or recovery-rate benchmark is claimed yet. Measure it using a documented workload before publishing performance figures.

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
