"""Background worker modules — periodic (cron-style) jobs.

Each module here exports a module-level ``periodic_jobs`` list of
:class:`synapse_cloud.scheduler.PeriodicJob`. The in-process
:class:`~synapse_cloud.scheduler.Scheduler` (started by the FastAPI app lifespan)
aggregates them via :func:`synapse_cloud.scheduler.discover_periodic_jobs` and runs
them on their intervals — **no separate worker process and no Redis**. Single-execution
across multiple app instances is guarded by a Postgres lease (``job_leases``).

Every job is also a plain ``async def f(ctx=None)`` so it can be invoked directly
(that's how the tests exercise them).
"""
