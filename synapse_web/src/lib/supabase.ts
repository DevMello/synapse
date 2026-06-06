import { createClient, type SupabaseClient } from "@supabase/supabase-js";
import type { Database } from "./database.types";

// The Web UI talks to Supabase directly (Auth + Realtime + data API). Per
// docs/web-ui.md the JWT carries org_id/role for RLS, and live telemetry arrives
// over Supabase Realtime channels. This is the single client seam; until the
// project is configured (env vars), it is null and the app runs on mock data.
const url = import.meta.env.VITE_SUPABASE_URL;
const anonKey = import.meta.env.VITE_SUPABASE_ANON_KEY;

export const supabase: SupabaseClient<Database> | null =
  url && anonKey ? createClient<Database>(url, anonKey) : null;

export const isSupabaseConfigured = Boolean(url && anonKey);
