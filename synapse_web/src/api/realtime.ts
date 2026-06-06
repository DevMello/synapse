// Synapse Web UI — Supabase Realtime wiring (web-ui.md §5). Subscriptions patch the
// TanStack Query cache so live views update without manual refetch. RLS gates what
// each subscriber receives. No-ops in mock mode (no Supabase configured).
import { useEffect } from "react";
import { useQueryClient, type QueryClient } from "@tanstack/react-query";
import { supabase, isSupabaseConfigured } from "../lib/supabase";

/**
 * Subscribe to fleet-level live events (runs, hitl_requests, anomaly_events,
 * daemon_presence) and invalidate the matching queries. Returns an unsubscribe fn.
 */
export function subscribeFleet(queryClient: QueryClient): () => void {
  if (!isSupabaseConfigured || !supabase) return () => {};
  const client = supabase;
  const channel = client
    .channel("fleet")
    .on("postgres_changes", { event: "*", schema: "public", table: "runs" }, () => {
      queryClient.invalidateQueries({ queryKey: ["runs"] });
    })
    .on("postgres_changes", { event: "*", schema: "public", table: "hitl_requests" }, () => {
      queryClient.invalidateQueries({ queryKey: ["approvals"] });
    })
    .on("postgres_changes", { event: "*", schema: "public", table: "anomaly_events" }, () => {
      queryClient.invalidateQueries({ queryKey: ["alerts"] });
    })
    .on("postgres_changes", { event: "*", schema: "public", table: "daemon_presence" }, () => {
      queryClient.invalidateQueries({ queryKey: ["daemons"] });
    })
    .subscribe();
  return () => {
    client.removeChannel(channel);
  };
}

/**
 * Subscribe to a single agent's run/telemetry channel while its detail view is open.
 * No-op in mock mode or without an agentId. Cleans up on unmount / agentId change.
 */
export function useAgentRealtime(agentId: string | undefined): void {
  const queryClient = useQueryClient();
  useEffect(() => {
    if (!isSupabaseConfigured || !supabase || !agentId) return;
    const client = supabase;
    const channel = client
      .channel(`agent:${agentId}`)
      .on(
        "postgres_changes",
        { event: "*", schema: "public", table: "runs", filter: `agent_id=eq.${agentId}` },
        () => queryClient.invalidateQueries({ queryKey: ["runs"] }),
      )
      .on(
        "postgres_changes",
        { event: "*", schema: "public", table: "logs", filter: `agent_id=eq.${agentId}` },
        () => queryClient.invalidateQueries({ queryKey: ["logs", agentId] }),
      )
      .on(
        "postgres_changes",
        { event: "*", schema: "public", table: "reasoning_traces", filter: `agent_id=eq.${agentId}` },
        () => queryClient.invalidateQueries({ queryKey: ["traceLines", agentId] }),
      )
      .subscribe();
    return () => {
      client.removeChannel(channel);
    };
  }, [agentId, queryClient]);
}
