# Why Chronos chooses at-least-once execution

## The failure

A worker can finish a handler's external side effect and crash in the small
window before it writes `status=succeeded` to PostgreSQL. For example, a
handler might charge a payment provider, send an email, or call another API;
the process can die before Chronos records the success transition.

From durable state alone, the task still looks `running` with an expired lease.
Treating that state as success would silently lose work when the handler had
actually failed. Chronos instead favors recovery: it returns the task to the
queue, and another worker claims it.

## The choice

This provides **at-least-once** execution, not exactly-once execution. A task
may run twice around the crash/commit boundary. The system preserves progress
and exposes the transition history, but downstream effects must be made
idempotent by the caller—for example, with a payment-provider idempotency key
or a unique operation ID at the receiving service.

## Reproducible proof

`tests/test_worker.py::test_task_can_run_twice_when_worker_crashes_after_side_effect`
models a first worker that completed an external side effect but died before it
recorded success. Lease repair requeues the task; the replacement worker runs
it again. The test asserts two executions and the durable timeline:

```text
lease_expired -> claimed -> succeeded
```

The Docker recovery demonstration complements the unit test by killing a live
worker while it owns a 30-second task, then verifying the replacement completes
the task on attempt 2.
