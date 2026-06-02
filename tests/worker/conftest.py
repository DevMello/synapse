"""Isolated fixtures for the worker daemon unit tests.

Fully self-contained: NO Supabase, NO network, NO real keychain. Each test gets a fresh
``~/.synapse`` under a tmp dir (via ``SYNAPSE_HOME``), ``SYNAPSE_WORKER_ENV=test`` (so the
keystore/uplink default to in-memory fakes), and all module singletons reset around it.

Fixtures:
  * ``settings`` — the cached :class:`Settings` for the tmp home.
  * ``store``    — a connected :class:`LocalStore` on the tmp db, installed as the singleton.
  * ``uplink``   — the in-memory uplink (records frames).
  * ``mock_cloud`` — a running :class:`MockCloud` WS hub (for connection/telemetry units).
"""
from __future__ import annotations

import os

import pytest
import pytest_asyncio

from synapse_worker import config as _config
from synapse_worker.capabilities import registry as _caps
from synapse_worker.crypto import reset_keystore, get_keystore
from synapse_worker.filtering import base as _filtering
from synapse_worker.plugins import base as _plugins
from synapse_worker.router import clear_handlers
from synapse_worker.ruleset import base as _ruleset
from synapse_worker.store import LocalStore, reset_store, set_store
from synapse_worker.uplink import get_uplink, reset_uplink

from .mock_cloud import MockCloud


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    """Point the daemon at a tmp home and reset every singleton around each test."""
    monkeypatch.setenv("SYNAPSE_WORKER_ENV", "test")
    monkeypatch.setenv("SYNAPSE_HOME", str(tmp_path / "home"))
    _config.reset_settings_cache()
    reset_store()
    reset_uplink()
    reset_keystore()
    _filtering.reset_filter_chain()
    _ruleset.reset_ruleset()
    _caps.reset_capability_registry()
    _plugins.reset_plugin_registry()
    clear_handlers()
    yield
    _config.reset_settings_cache()
    reset_store()
    reset_uplink()
    reset_keystore()
    clear_handlers()


@pytest.fixture
def settings():
    return _config.get_settings()


@pytest_asyncio.fixture
async def store(settings):
    from synapse_worker.paths import paths_for

    paths = paths_for(settings)
    paths.ensure_layout()
    s = await LocalStore(paths.db_path).connect()
    set_store(s)
    try:
        yield s
    finally:
        await s.close()


@pytest.fixture
def uplink():
    return get_uplink()


@pytest.fixture
def keystore():
    return get_keystore()


@pytest_asyncio.fixture
async def mock_cloud():
    cloud = await MockCloud().start()
    try:
        yield cloud
    finally:
        await cloud.stop()
