# Task: User-controlled command signing — cryptographic proof of user intent on every agent run

**Goal.** Give users cryptographic assurance that **no one can dispatch agent runs (or any other
execution command) to their daemon without their active participation** — including the company
hosting Synapse. A stolen password, a compromised cloud, or a malicious operator should not be
able to cause agents to execute on a user's machine.

This document specifies the threat model, the signing scheme, every wire-format change, and the
implementation units.

---

## 1. The current gap

The daemon connects *outbound-only* (no inbound ports — a hard architectural invariant). But
once that WebSocket is open, **the cloud drives execution**:

```
Web UI  ──(HTTPS)──► Cloud  ──(authenticated WS)──► Daemon
                        ↑
                 company controls this box
```

Today's `wire.py` command frame:
```json
{"type":"command","seq":12,"command_type":"agent.run",
 "payload":{"agent_id":"...","run_id":"..."},"idempotency_key":"..."}
```

There is no field proving *a specific user authorized this run*. The cloud just sends it.
TLS protects the transport, but TLS terminates at the cloud. Everything the cloud
sends to the daemon is inherently trusted.

**What this means in practice:**
- A compromised cloud host → agents execute arbitrary payloads on every connected machine
- A malicious insider at the hosting company → same
- `agent.deploy` can overwrite agent prompts and tool configs before `agent.run` fires —
  an attacker with cloud access can chain both without the user ever clicking anything

Encrypted secrets (env vars) are already zero-knowledge — the cloud relays sealed-box
ciphertext it cannot read. This task closes the same gap on the *execution* side.

---

## 2. Threat model (what we're protecting against)

| Threat | Protected after this task? |
|--------|---------------------------|
| Network-level MitM / injected frames | ✅ (cloud signature covers transport integrity) |
| Compromised cloud host — executing arbitrary runs | ✅ (user signature required) |
| Malicious cloud operator sending `agent.run` | ✅ (user session key never leaves browser) |
| Replay attack (re-send a previously valid command) | ✅ (nonce + expiry in signed envelope) |
| Stolen user password only (no device) | ✅ (signing key is in-browser / on-device) |
| User's own device fully compromised | ❌ (out of scope — daemon trust terminates here) |
| Scheduled/automated runs with no live user | ✅ with pre-signed schedule tokens (§5) |

---

## 3. Signing scheme

Two independent signatures on every sensitive command frame:

```
┌──────────────────────────────────────────────┐
│  CommandAuth envelope (JSON, signed twice)    │
│                                              │
│  command_type    "agent.run"                 │
│  agent_id        "uuid"                      │
│  daemon_id       "uuid"                      │
│  org_id          "uuid"                      │
│  actor           "user-uuid"                 │
│  nonce           "32 random hex chars"       │
│  not_before      "2026-06-09T03:00:00Z"      │
│  expires_at      "2026-06-09T03:00:30Z"      │  ← 30-second window
│  payload_hash    SHA-256(canonical payload)  │
│                                              │
│  user_sig        Ed25519(envelope, U_priv)   │  ← user's session key
│  cloud_sig       Ed25519(envelope, C_priv)   │  ← relay proof
└──────────────────────────────────────────────┘
```

**`user_sig`** — signed with an ephemeral Ed25519 key generated in the browser at login.
The private key lives only in `sessionStorage` (in-memory equivalent — cleared on tab close)
or IndexedDB (`CryptoKey`, non-extractable). It **never leaves the browser**. The cloud
receives and forwards the `user_sig` but cannot produce it. The corresponding public key
is registered in `users.command_public_key` on every login.

**`cloud_sig`** — signed with the existing `GRANT_SIGNING_KEY` (already used for
orchestration grants in `synapse_cloud/orchestration_crypto.py`). Proves the command was
relayed by this specific cloud deployment — not an injected frame from a rogue proxy.

**Both signatures must verify.** The daemon rejects any sensitive command where either
is absent, expired, replayed (nonce seen before), or invalid.

### 3.1 Canonical bytes

Identical to the grant scheme in `orchestration_crypto.py`:
```
canonical = sort_keys(compact_json(envelope_without_sigs))
sig_input  = SHA-256(canonical)   # sign the hash, not raw JSON
```

Both sides sign and verify the same `sig_input` so neither has to trust the other's
JSON serialisation.

### 3.2 Which commands require a `CommandAuth`

Commands in the **human-triggered** set:

| Command type | Notes |
|---|---|
| `agent.run` | Any live run dispatch |
| `agent.cancel` | Cancelling a run |
| `agent.deploy` | Deploying/updating an agent's config |
| `agent.update_prompt` | Updating the agent prompt |
| `hitl.resolve` | Human approving/rejecting a HITL gate |
| `run.recover` | Recovering a run to a different daemon |
| `env.set` | Setting an env var (already E2E encrypted for value, now also auth-signed) |
| `env.delete` | Deleting an env var |
| `daemon.revoke` | Self-revocation / forced logout |

Commands in the **automated** set (no live user present):

| Command type | Auth mechanism |
|---|---|
| Scheduled `agent.run` | Pre-signed schedule token (§5) |
| `run.reconcile` | Cloud-only — no user, no auth needed (no side-effects on user files) |
| Telemetry acks | Control frames — no auth needed |

Commands the daemon can always refuse:
- Any command not in either whitelist above arrives without `command_auth` → rejected with a warning audit event

### 3.3 Wire format change

`synapse_worker/wire.py` `CloudCommand` gains an optional field:

```python
@dataclass
class CloudCommand:
    seq: Optional[int]
    command_type: str
    payload: dict[str, Any]
    idempotency_key: Optional[str] = None
    command_auth: Optional[CommandAuth] = None   # NEW
```

Where `CommandAuth` is:
```python
@dataclass(frozen=True)
class CommandAuth:
    envelope: dict[str, Any]   # the signed dict above
    user_sig: str              # base64 Ed25519
    cloud_sig: str             # base64 Ed25519
```

The JSON wire frame becomes:
```json
{
  "type": "command",
  "seq": 12,
  "command_type": "agent.run",
  "payload": {"agent_id":"..."},
  "idempotency_key": "...",
  "command_auth": {
    "envelope": {
      "command_type":"agent.run","agent_id":"...","daemon_id":"...",
      "org_id":"...","actor":"user-uuid","nonce":"abc123",
      "not_before":"2026-06-09T03:00:00Z","expires_at":"2026-06-09T03:00:30Z",
      "payload_hash":"sha256hex"
    },
    "user_sig":"base64...",
    "cloud_sig":"base64..."
  }
}
```

The daemon's `parse_command()` in `wire.py` populates `command_auth` when present.

---

## 4. New components

### 4.1 Frontend — session signing key (`synapse_web/src/lib/commandSigning.ts`)

Generates and persists the user's Ed25519 keypair for the current session:

```ts
// Generate on login; store in sessionStorage (cleared on tab close).
// Uses WebCrypto subtle — Ed25519 is available in all modern browsers.
export async function ensureSessionSigningKey(): Promise<CryptoKeyPair>
export async function signCommandAuth(envelope: CommandAuthEnvelope): Promise<string>  // base64
export async function getPublicKeyBase64(): Promise<string>
export function clearSessionSigningKey(): void  // call on sign-out
```

On login (`auth.tsx`, after `SIGNED_IN` auth state change):
1. Generate keypair: `crypto.subtle.generateKey({ name: "Ed25519" }, false, ["sign", "verify"])`
2. Export public key to base64, register it: `POST /auth/command-key` with `{ public_key }` — cloud writes `users.command_public_key`
3. Store `CryptoKeyPair` in module-level memory (not in storage — it's a handle only)

On sign-out: `clearSessionSigningKey()`.

### 4.2 Frontend — command authorization helper (`synapse_web/src/lib/commandAuth.ts`)

Used by every REST call that triggers a command dispatch:

```ts
export async function buildCommandAuth(
  commandType: string,
  agentId: string,
  daemonId: string,
  orgId: string,
  actorId: string,
  payloadHash: string,
): Promise<CommandAuthToken>
```

Returns `{ envelope, user_sig }` (cloud adds `cloud_sig` server-side before forwarding).
Callers pass this in the request body alongside the usual fields.

### 4.3 Backend — `CommandAuth` minting (`synapse_cloud/command_auth.py`)

Receives `{ envelope, user_sig }` from the Web UI:
1. Verifies `user_sig` against the caller's `users.command_public_key` (from DB)
2. Checks `envelope.expires_at` is in the future and `not_before` is in the past
3. Checks `envelope.actor == principal.user_id`
4. Checks `envelope.payload_hash` matches the actual command payload being sent
5. Adds `cloud_sig` using `orchestration_crypto._signing_key()` (existing, already in prod)
6. Returns the fully signed `CommandAuth` to attach to the command frame

Attach the `command_auth` when calling `command_bus.send()`. The existing `DaemonCommandBus`
interface gains an optional `command_auth` argument to `send()`.

### 4.4 Backend — public key registration endpoint (`synapse_cloud/routers/auth_command_key.py`)

```
POST /auth/command-key
Body: { "public_key": "<base64 Ed25519 public key>" }
Auth: valid Supabase session (get_principal)
```

Writes `users.command_public_key = body.public_key` for `principal.user_id`.
No other fields changed. Public key rotation is handled by calling this endpoint again
(each new session generates a fresh key).

### 4.5 Daemon — `CommandAuth` verifier (`synapse_worker/command_auth.py`)

Loaded once at startup (or cached with a short TTL). Verifies:

1. `cloud_sig` against the cloud's Ed25519 public key (distributed at daemon pairing in the
   `daemon.register` response, stored in keychain — same mechanism as the grant verify key)
2. `user_sig` against the actor's public key (fetched from `GET /auth/command-key/{user_id}`,
   cached in the daemon's local `command_keys` SQLite table with a 15-minute TTL)
3. `envelope.expires_at > now()`
4. `envelope.not_before <= now()`
5. `envelope.nonce` not in the daemon's `seen_nonces` store (SQLite, pruned hourly)
6. `envelope.payload_hash == SHA-256(canonical(command.payload))`
7. `envelope.command_type == command.command_type`
8. `envelope.daemon_id == this_daemon_id` (prevents cross-daemon replay)

Returns `VerifyResult(ok: bool, reason: str)`.

Plugged into `router.py`'s `dispatch()` — before calling handlers, if the command type is
in the human-triggered set and `command.command_auth is None` or
`verifier.verify(command.command_auth).ok is False`, the daemon **refuses** (logs, audits,
does not ack so the cloud retries — but the daemon never executes).

### 4.6 Daemon — user public key cache (`synapse_worker/store.py` or new `command_keys.py`)

Minimal SQLite table:
```sql
CREATE TABLE IF NOT EXISTS command_keys (
    user_id TEXT PRIMARY KEY,
    public_key TEXT NOT NULL,
    fetched_at REAL NOT NULL   -- unix timestamp
);
```

On cache miss or TTL expiry: `GET /auth/command-key/{user_id}` against the cloud. If the
cloud is unreachable and the key is stale (>15 min): fall back to the last known key with a
warning log (avoids blocking runs during brief disconnects).

---

## 5. Scheduled / automated runs (no live user)

Scheduled `agent.run` commands have no user at the keyboard. The scheme uses a
**pre-signed schedule token** instead:

When a user creates or updates a schedule, the Web UI signs a `ScheduleAuth`:
```json
{
  "type": "schedule_auth",
  "schedule_id": "uuid",
  "agent_id": "uuid",
  "daemon_id": "uuid",
  "org_id": "uuid",
  "actor": "user-uuid",
  "signed_at": "2026-06-09T...",
  "max_run_count": 0,     // 0 = unlimited
  "expires_at": null      // null = never (or a date for temp schedules)
}
```

This `schedule_auth` is stored server-side in the `schedules` table (signed, not forged by
the cloud). When the scheduler fires a run, the daemon receives the `schedule_auth` instead
of a live `command_auth`. Verification: cloud_sig + user_sig still present; `not_before`/
`expires_at` govern the schedule's lifetime rather than a 30-second window.

The daemon keeps a copy of schedule_auth blobs (synced via `schedule.sync` command) so it
can verify even when temporarily disconnected from the cloud.

---

## 6. Schema changes

One additive migration (`tools/supabase/migrations/20260608000100_0018_command_signing.sql`):

```sql
-- User session command-signing public key (rotated each login).
ALTER TABLE users ADD COLUMN command_public_key text;

-- Index for daemon key-cache refresh lookups.
CREATE INDEX ON users (id) WHERE command_public_key IS NOT NULL;

-- Pre-signed schedule authorization blobs (stored alongside the schedule).
ALTER TABLE schedules ADD COLUMN schedule_auth jsonb;
```

---

## 7. Key distribution — how the daemon learns trust anchors

At daemon pairing (`daemon.register` response from the cloud), the cloud already sends the
grant verify key (`grant_public_key_b64`) which the daemon stores in its keychain. Extend
this response to also carry `command_verify_key_b64` (the same key, or a dedicated one —
using the same `GRANT_SIGNING_KEY` is fine for now; they can be split later).

The daemon stores this in the keychain under `synapse:daemon` / `command_verify_public_key`.
On reconnect it is refreshed if the cloud reports a key rotation.

User public keys are fetched on demand (§4.5) — no pre-distribution needed, which keeps the
pairing flow simple and handles key rotation automatically (each new session issues a new key).

---

## 8. Graceful rollout / backward compatibility

The `command_auth` field is **optional** in the wire format during rollout. The daemon uses
a per-org / per-daemon feature flag stored in `daemons.settings` JSONB:
`require_command_auth: false` (default).

Rollout sequence:
1. **Deploy cloud + daemon changes** — both understand `command_auth` but don't require it.
2. **Web UI ships** — starts sending `command_auth` on all human-triggered commands.
3. **Monitor** for any daemon version mismatch (old daemons silently ignore the extra field).
4. **Flip** `require_command_auth: true` per-org as users upgrade their daemon version.
5. Once all active daemons are on the new version, make `require_command_auth: true` the
   default for new daemon registrations.

This means no hard cut-over — old daemons keep working, new daemons gain the protection.

---

## 9. Implementation units

| # | Unit | Files | Notes |
|---|------|-------|-------|
| 1 | Schema migration | `tools/supabase/migrations/20260608000100_0018_command_signing.sql` | `users.command_public_key`, `schedules.schedule_auth` |
| 2 | Backend: command-key endpoint + `CommandAuth` minting | `synapse_cloud/routers/auth_command_key.py`, `synapse_cloud/command_auth.py` | Key registration + `cloud_sig` addition before dispatch |
| 3 | Backend: attach `command_auth` to command bus | `synapse_cloud/command_bus.py`, `synapse_cloud/ws_hub/` (command send path), all routers that call `command_bus.send()` for human-triggered commands | Pass `command_auth` through to wire frame |
| 4 | Daemon: `CommandAuth` verifier + nonce store | `synapse_worker/command_auth.py`, `synapse_worker/store.py` (add `seen_nonces` + `command_keys` tables), `synapse_worker/router.py` | Verify before dispatch; reject unsigned sensitive commands (flag-gated) |
| 5 | Daemon: key distribution at pairing | `synapse_worker/connection/manager.py` (`_send_register` / register response parsing), `synapse_worker/auth/keys.py` | Store `command_verify_public_key` in keychain |
| 6 | Frontend: session signing key | `synapse_web/src/lib/commandSigning.ts`, `synapse_web/src/lib/auth.tsx` (call `ensureSessionSigningKey` on SIGNED_IN) | WebCrypto Ed25519, in-memory only |
| 7 | Frontend: attach `command_auth` to run/deploy calls | `synapse_web/src/api/client.ts` (or per-call sites), `synapse_web/src/lib/commandAuth.ts` | Every REST call that triggers a human-triggered command |
| 8 | Scheduled run pre-signing | `synapse_web/src/screens/agent/tabs/Schedule.tsx` (sign on create/update), `synapse_cloud/routers/schedules.py` (store `schedule_auth`), daemon scheduler handler | Lower priority — can ship after units 1–7 |

---

## 10. Risks & open questions

| Risk | Mitigation |
|------|-----------|
| Browser tab close clears the session key → next tab open must re-register | Key regenerated and re-registered on every `SIGNED_IN` event. Daemon's 15-min cache TTL means a new key propagates quickly. |
| Clock skew between browser and daemon | `not_before` / `expires_at` have a ±30 second tolerance. Daemon logs a warning if envelope clock is >5s off. |
| Ed25519 not yet available in all browsers | As of 2025, Ed25519 in WebCrypto is Baseline 2024 (Chrome 113+, Firefox 130+, Safari 17+). Provide a WASM fallback (`@noble/ed25519`) for older browsers. |
| Daemon version skew during rollout | `require_command_auth` flag (§8) keeps old daemons working. The Web UI always sends `command_auth`; old daemons simply ignore it. |
| Nonce store grows unbounded | Prune nonces older than `max(expiry_window)` = 60 seconds on a background interval. The nonce store is bounded to at most a few hundred rows at any time. |
| Schedule tokens are long-lived — what if user account is compromised? | Owner/admin can delete a schedule (server-side), which invalidates the stored `schedule_auth` at the cloud level. Daemon syncs schedule deletions via existing `schedule.sync`. |

---

## 11. Acceptance criteria

- `agent.run` / `agent.deploy` dispatched from the Web UI carry a valid `command_auth` with
  both `user_sig` and `cloud_sig`.
- A daemon with `require_command_auth: true` refuses any `agent.run` frame that arrives
  without a valid `command_auth` (verified in `tools/tests/`).
- A forged `command_auth` (wrong `user_sig`) is rejected; the run does not start.
- A replayed `command_auth` (same nonce) is rejected on the second delivery.
- Scheduled runs from the built-in scheduler succeed using pre-signed `schedule_auth`.
- Old daemon versions (without `command_auth.py`) continue to work (field silently ignored,
  `require_command_auth: false` default).
- `npm run build` and Python tests remain green throughout.
