// Ed25519 session signing key — generated at login, lives in browser memory only.
// The private key is non-extractable and cleared on sign-out / tab close.

let _keyPair: CryptoKeyPair | null = null;
let _keyPairPromise: Promise<CryptoKeyPair> | null = null;

export function ensureSessionSigningKey(): Promise<CryptoKeyPair> {
  if (_keyPair) return Promise.resolve(_keyPair);
  if (_keyPairPromise) return _keyPairPromise;
  _keyPairPromise = crypto.subtle
    .generateKey({ name: "Ed25519" } as AlgorithmIdentifier, false, ["sign", "verify"])
    .then((kp) => {
      _keyPair = kp as CryptoKeyPair;
      _keyPairPromise = null;
      return _keyPair;
    });
  return _keyPairPromise;
}

export async function getPublicKeyBase64(): Promise<string> {
  const kp = await ensureSessionSigningKey();
  const raw = await crypto.subtle.exportKey("raw", kp.publicKey);
  return btoa(String.fromCharCode(...new Uint8Array(raw)));
}

export async function signBytes(data: Uint8Array): Promise<string> {
  const kp = await ensureSessionSigningKey();
  // Use a fresh copy to avoid issues with subarray views sharing a larger buffer.
  const sig = await crypto.subtle.sign("Ed25519", kp.privateKey, data.slice().buffer as ArrayBuffer);
  return btoa(String.fromCharCode(...new Uint8Array(sig)));
}

export function clearSessionSigningKey(): void {
  _keyPair = null;
}
