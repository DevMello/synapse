// Orchestration lineage (§2.4): the child runs an agent initiated, as a tree.
import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import { supabase, isSupabaseConfigured } from "../../lib/supabase";
import type { RunLineage } from "../../types";
import { buildLineage } from "../adapters/lineage";

export function useAgentLineage(agentId: string | undefined): UseQueryResult<RunLineage[]> {
  return useQuery({
    queryKey: ["lineage", agentId],
    queryFn: async () => {
      if (isSupabaseConfigured && supabase && agentId) {
        const { data, error } = await supabase
          .from("runs")
          .select("*, agents(name)")
          .eq("initiator_agent_id", agentId)
          .order("created_at", { ascending: false })
          .limit(100);
        if (error) throw error;
        return buildLineage(data as unknown as Parameters<typeof buildLineage>[0]);
      }
      return [];
    },
    enabled: agentId != null,
  });
}
