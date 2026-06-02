"""Structured logging setup for the daemon.

A single ``synapse_worker`` logger tree. Feature units do
``log = get_logger(__name__)`` and never configure handlers themselves.
"""
from __future__ import annotations

import logging
import sys

_CONFIGURED = False
_ROOT = "synapse_worker"


def configure_logging(level: int | str = logging.INFO) -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    logger = logging.getLogger(_ROOT)
    logger.setLevel(level)
    handler = logging.StreamHandler(stream=sys.stderr)
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    )
    logger.addHandler(handler)
    logger.propagate = False
    _CONFIGURED = True


def get_logger(name: str | None = None) -> logging.Logger:
    if name and not name.startswith(_ROOT):
        name = f"{_ROOT}.{name.rsplit('.', 1)[-1]}"
    return logging.getLogger(name or _ROOT)
