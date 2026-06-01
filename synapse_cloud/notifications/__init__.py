"""Notification service package (spec §7). Real adapters live in unit 10."""
from .base import Notifier, ConsoleNotifier, FakeNotifier, get_notifier, set_notifier

__all__ = ["Notifier", "ConsoleNotifier", "FakeNotifier", "get_notifier", "set_notifier"]
