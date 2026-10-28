import time

import redis

from app.config import QUEUE_KEY, REDIS_URL

client = redis.Redis.from_url(REDIS_URL, decode_responses=True)


def _score(run_at_epoch: float, priority: int) -> float:
    # Earlier due time wins; within the same second, priority 9 beats priority 0.
    return run_at_epoch * 100 + (9 - priority)


def enqueue(task_id: str, run_at_epoch: float, priority: int):
    client.zadd(QUEUE_KEY, {task_id: _score(run_at_epoch, priority)})


def pop_due() -> str | None:
    now = time.time() * 100 + 99
    candidates = client.zrangebyscore(QUEUE_KEY, "-inf", now, start=0, num=1)
    if not candidates:
        return None
    task_id = candidates[0]
    return task_id if client.zrem(QUEUE_KEY, task_id) else None


def requeue_stale_rows(db):
    """Heal a crash between committing a task and placing it in Redis."""
    from app.models import Task
    import datetime as dt
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=60)
    rows = db.query(Task).filter(
        (Task.status == "queued") | ((Task.status == "retrying") & (Task.run_at <= dt.datetime.now(dt.timezone.utc))) |
        ((Task.status == "running") & (Task.updated_at <= cutoff))
    ).all()
    for task in rows:
        if task.status == "running":
            task.status = "queued"
            task.error = "Worker lease expired; task will be retried (handler may run more than once)."
            db.commit()
        run_at = task.run_at
        if run_at.tzinfo is None:
            run_at = run_at.replace(tzinfo=dt.timezone.utc)
        enqueue(task.id, run_at.timestamp(), task.priority)
