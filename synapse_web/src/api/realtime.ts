// Synapse Web UI — Supabase Realtime wiring (foundation scaffold).
//
// Unit 16 fills these with `supabase.channel(...).on("postgres_changes", …)`
// subscriptions that patch the TanStack Query cache (web-ui.md §5). RLS gates what
// each subscriber actually receives. Keep subscriptions scoped to the open view and
// unsubscribe on unmount; logs/reasoning_traces are high-volume — subscribe only on
// the Logs/Trace view.
import type { QueryClient } from "@tanstack/react-query";

/**
 * Subscribe to fleet-level live events (runs, hitl_requests, anomaly_events,
 * daemon_presence) and patch the query cache. Returns an unsubscribe function.
 * Foundation: no-op. Unit 16 implements.
 */
export function subscribeFleet(_queryClient: QueryClient): () => void {
  // TODO(worker:realtime): supabase.channel("fleet").on("postgres_changes", …)
  return () => {};
}

/**
 * Subscribe to a single agent's run/telemetry channel while its detail view is
 * open. Foundation: no-op. Unit 16 implements (consumed by AgentDetail in unit 14).
 */
export function useAgentRealtime(_agentId: string | undefined): void {
  // TODO(worker:realtime): per-agent run/telemetry subscription
}
