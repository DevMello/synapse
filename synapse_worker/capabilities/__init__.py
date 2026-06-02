"""Capability selection package — registry in :mod:`capabilities.registry`.

Tracks the two-tier model (§4.11): daemon-tier *available* capabilities and agent-tier
*attached* selections. The plugin unit provisions; this registry records selection.
"""
from __future__ import annotations
