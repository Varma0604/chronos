# Chronos

Chronos is a small durable task scheduler. A FastAPI service stores task definitions and state transitions in PostgreSQL, then places task IDs in a Redis sorted-set queue. A separate worker claims due tasks, runs a registered handler, and records the outcome.

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

- Task state and payloads are stored in PostgreSQL; Redis is the due-work index. The worker periodically repairs queued rows that were not enqueued after a process interruption.
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
