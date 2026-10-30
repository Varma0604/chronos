import time

import redis

from app.config import DEAD_LETTER_QUEUE_KEY, QUEUE_KEY, REDIS_URL, WORKER_LEASE_SECONDS

client = redis.Redis.from_url(REDIS_URL, decode_responses=True)


def _score(run_at_epoch: float, priority: int) -> float:
    # Earlier due time wins; within the same second, priority 9 beats priority 0.
    return run_at_epoch * 100 + (9 - priority)


def enqueue(task_id: str, run_at_epoch: float, priority: int):
    client.zadd(QUEUE_KEY, {task_id: _score(run_at_epoch, priority)})


def dead_letter(task_id: str):
    """Keep a durable Redis reference to a task that exhausted its retries."""
    client.lpush(DEAD_LETTER_QUEUE_KEY, task_id)


def pop_due() -> str | None:
    now = time.time() * 100 + 99
    candidates = client.zrangebyscore(QUEUE_KEY, "-inf", now, start=0, num=1)
    if not candidates:
        return None
    task_id = candidates[0]
    return task_id if client.zrem(QUEUE_KEY, task_id) else None


def requeue_stale_rows(db):
    """Repair lost queue entries and recover work whose worker lease expired."""
    from app.models import Task
    import datetime as dt
    now = dt.datetime.now(dt.timezone.utc)
    rows = db.query(Task).filter(
        (Task.status == "queued") | ((Task.status == "retrying") & (Task.run_at <= dt.datetime.now(dt.timezone.utc))) |
        ((Task.status == "running") & (Task.lease_expires_at <= now))
    ).all()
    for task in rows:
        if task.status == "running":
            task.status = "queued"
            task.lease_owner = None
            task.lease_expires_at = None
            task.error = "Worker lease expired; task was requeued (handler may run more than once)."
            db.commit()
        run_at = task.run_at
        if run_at.tzinfo is None:
            run_at = run_at.replace(tzinfo=dt.timezone.utc)
        enqueue(task.id, run_at.timestamp(), task.priority)
