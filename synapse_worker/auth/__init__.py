"""Auth & device login (§2).

The OAuth 2.0 Device Authorization Grant client, the production keystore (OS keychain
with an encrypted-file fallback), and the daemon / org-recovery E2E keypairs. The CLI
``synapse login`` / ``synapse init`` commands drive this package.
"""
from __future__ import annotations
