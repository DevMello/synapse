"""Service-install support (tui-daemon.md §2 "Running as a service").

Two layers, deliberately split so the side-effect-free part is trivially unit-testable:

  * :mod:`synapse_worker.service.units` — PURE generators that render a systemd unit, a
    launchd plist, or a Windows-service spec from parameters. No filesystem, no
    subprocess, no platform detection. Just string/spec in → string/spec out.
  * :mod:`synapse_worker.service.manager` — the side-effecting orchestration layer that
    detects the host OS, picks the right generator, writes the rendered unit to the
    correct path, and runs the enable/start commands. Every real mutation is guarded by a
    ``dry_run`` flag so the unit can be exercised (and tested) without root and without
    registering anything on the host.
"""
from __future__ import annotations
