"""Taskiq scheduler — periodic task scheduling per §8 of database_requirements.md.

Run with: taskiq scheduler app.tasks.scheduler:scheduler

Uses LabelScheduleSource — cron labels are set on tasks at declaration time.
"""

from taskiq import TaskiqScheduler
from taskiq.schedule_sources import LabelScheduleSource

from app.tasks import broker

# Import all task modules so their @broker.task decorators register with the broker
import app.tasks.cleanup  # noqa: F401
import app.tasks.reconciliation  # noqa: F401
import app.tasks.expiry  # noqa: F401
import app.tasks.streak_push  # noqa: F401

scheduler = TaskiqScheduler(
    broker=broker,
    sources=[LabelScheduleSource(broker)],
)
