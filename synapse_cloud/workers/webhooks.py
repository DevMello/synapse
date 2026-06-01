"""Reusable helpers for webhook ingress.

The webhook ingress (`POST /hooks/{token}`) does its work inline in the request
handler: verify the HMAC signature, map the inbound JSON through the webhook's
`payload_template`, insert a `runs` row, and dispatch `agent.run`. There is no
Arq task — the work is cheap and the command bus is already async — but the
signature/template logic lives here so it can be unit-tested without spinning up
the full request stack, and reused if a future unit moves dispatch off-request.

No `tasks` / `cron_jobs` are exported, so the worker autodiscovery picks up
nothing from this module.
"""
from __future__ import annotations

import hashlib
import hmac
from typing import Any

# Signature header format: "X-Synapse-Signature: sha256=<hex>".
SIGNATURE_PREFIX = "sha256="


def compute_signature(secret: str, raw_body: bytes) -> str:
    """HMAC-SHA256 of the raw request body with the webhook secret (hex digest)."""
    return hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()


def parse_signature_header(header: str | None) -> str | None:
    """Extract the hex digest from a `sha256=<hex>` header value.

    Returns None when the header is missing or not in the expected form.
    """
    if not header:
        return None
    header = header.strip()
    if not header.startswith(SIGNATURE_PREFIX):
        return None
    return header[len(SIGNATURE_PREFIX):].strip() or None


def apply_payload_template(
    template: dict[str, Any] | None, body: Any
) -> dict[str, Any]:
    """Map an inbound webhook body through a simple field-mapping template.

    The template is a flat dict of ``{out_key: source}`` entries merged over the
    body. A string ``source`` that names a top-level key of an object body is
    resolved to that field's value; any other ``source`` (or a non-object body)
    is used as a literal default. With no template the body is returned as-is
    (wrapped in ``{"body": ...}`` when it is not already an object).
    """
    if isinstance(body, dict):
        base: dict[str, Any] = dict(body)
    else:
        base = {"body": body}

    if not template:
        return base

    mapped: dict[str, Any] = dict(base)
    for out_key, source in template.items():
        if isinstance(source, str) and isinstance(body, dict) and source in body:
            mapped[out_key] = body[source]
        else:
            mapped[out_key] = source
    return mapped
