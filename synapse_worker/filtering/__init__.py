"""Input/Output filtering middleware package — base in :mod:`filtering.base`.

Layer A (redaction) and Layer B (injection/jailbreak guard) are added by feature units
and registered into the shared :class:`~synapse_worker.filtering.base.FilterChain`.
"""
from __future__ import annotations
