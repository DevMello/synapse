// Minimal REST client for the Synapse Cloud Backend (FastAPI). Reads come from the
// Supabase data API directly (RLS); a few writes must go through the backend because
// they do server-side work the browser can't — e.g. minting a *signed* orchestration
// grant (§2.3). Carries the Supabase session JWT so the backend resolves org/role.
import { supabase } from "../lib/supabase";

const API_BASE = (import.meta.env.VITE_API_BASE ?? "").replace(/\/$/, "");

export function isApiConfigured(): boolean {
  return Boolean(API_BASE);
}

async function authHeaders(): Promise<Record<string, string>> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (supabase) {
    const { data } = await supabase.auth.getSession();
    const token = data.session?.access_token;
    if (token) headers.Authorization = `Bearer ${token}`;
  }
  return headers;
}

export async function apiGet<T = unknown>(path: string): Promise<T> {
  if (!API_BASE) throw new Error("Cloud API not configured (VITE_API_BASE)");
  const res = await fetch(`${API_BASE}${path}`, {
    method: "GET",
    headers: await authHeaders(),
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`${res.status} ${res.statusText}${text ? `: ${text}` : ""}`);
  }
  return (await res.json()) as T;
}

export async function apiPost<T = unknown>(path: string, body?: unknown): Promise<T> {
  if (!API_BASE) throw new Error("Cloud API not configured (VITE_API_BASE)");
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: await authHeaders(),
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`${res.status} ${res.statusText}${text ? `: ${text}` : ""}`);
  }
  return (await res.json()) as T;
}
