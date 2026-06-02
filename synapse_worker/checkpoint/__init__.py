"""Checkpointing, resume & recovery (§4.12).

Durable execution for agent runs: a write-ahead journal over the local ``checkpoints``
table records each run step *before* and *after* a tool call, so a crash or network blip
never loses progress or re-fires an expensive/dangerous side effect.

Public surface (so sibling units/tests depend on the interface, not the file layout):

  * :class:`CheckpointJournal` — append/latest/history over the journal.
  * :class:`ResumePlan` / :class:`StepDecision` — what to skip / re-run / gate on resume.
  * :func:`plan_resume` — derive a resume plan from the journal.
  * :func:`sync_checkpoint` — E2E-seal a checkpoint to the org recovery key + emit upstream.
  * :func:`auto_resume_all` — on boot, plan resumes for interrupted runs.
"""
from __future__ import annotations

from .journal import (
    STATUS_COMMITTED,
    STATUS_IN_FLIGHT,
    STATUS_PENDING,
    CheckpointJournal,
)
from .recovery import (
    ResumePlan,
    StepDecision,
    auto_resume_all,
    plan_resume,
    sync_checkpoint,
)

__all__ = [
    "CheckpointJournal",
    "STATUS_PENDING",
    "STATUS_IN_FLIGHT",
    "STATUS_COMMITTED",
    "ResumePlan",
    "StepDecision",
    "plan_resume",
    "sync_checkpoint",
    "auto_resume_all",
]
