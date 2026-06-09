import { signBytes } from "./commandSigning";

export interface CommandAuthEnvelope {
  command_type: string;
  agent_id: string;
  daemon_id: string;
  org_id: string;
  actor: string;
  nonce: string;
  not_before: string;
  expires_at: string;
  payload_hash: string;
}

export interface CommandAuthToken {
  envelope: CommandAuthEnvelope;
  user_sig: string;
}

async function sha256Hex(data: string): Promise<string> {
  const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(data));
  return Array.from(new Uint8Array(buf))
    .map(b => b.toString(16).padStart(2, "0"))
    .join("");
}

function randomNonce(): string {
  const buf = new Uint8Array(16);
  crypto.getRandomValues(buf);
  return Array.from(buf).map(b => b.toString(16).padStart(2, "0")).join("");
}

export async function buildCommandAuth(
  commandType: string,
  agentId: string,
  daemonId: string,
  orgId: string,
  actorId: string,
  payload: Record<string, unknown>,
): Promise<CommandAuthToken> {
  const now = new Date();
  const notBefore = now.toISOString();
  const expiresAt = new Date(now.getTime() + 30_000).toISOString();
  const nonce = randomNonce();

  // Canonical payload hash: sort keys, compact JSON
  const sortedPayload = Object.fromEntries(
    Object.keys(payload).sort().map(k => [k, payload[k]])
  );
  const payloadHash = await sha256Hex(JSON.stringify(sortedPayload));

  const envelope: CommandAuthEnvelope = {
    command_type: commandType,
    agent_id: agentId,
    daemon_id: daemonId,
    org_id: orgId,
    actor: actorId,
    nonce,
    not_before: notBefore,
    expires_at: expiresAt,
    payload_hash: payloadHash,
  };

  // sig_input = SHA-256(sort_keys compact JSON of envelope)
  const sortedEnvelope = Object.fromEntries(
    Object.keys(envelope).sort().map(k => [k, envelope[k as keyof CommandAuthEnvelope]])
  );
  const canonicalBuf = new TextEncoder().encode(JSON.stringify(sortedEnvelope));
  const sigInput = new Uint8Array(await crypto.subtle.digest("SHA-256", canonicalBuf));
  const userSig = await signBytes(sigInput);

  return { envelope, user_sig: userSig };
}
