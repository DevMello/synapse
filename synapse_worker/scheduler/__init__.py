"""Scheduler subpackage (§4.4).

The :class:`~synapse_worker.scheduler.service.SchedulerService` runs APScheduler with a
SQLite jobstore so cron/interval/date schedules survive a daemon restart. The
``schedule.set`` command handler and the ``scheduler`` service factory live in
``synapse_worker.commands.schedules`` (auto-imported at daemon assembly).
"""
from __future__ import annotations
