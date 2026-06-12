// Unified handoff trace (§11.6): the runs that share one root_run_id, ordered by hop, so
// the canvas can light up node-by-node. Live reads come from Supabase; mock mode returns
// an empty trace (the canvas drives a local draft-run animation instead).
import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import { supabase, isSupabaseConfigured } from "../../lib/supabase";

export interface TraceHop {
  runId: string;
  agentId: string;
  hop: number;
  mode: string | null;
  status: string;
  cost: number;
  parentRunId?: string;
}

export function useFlowTrace(rootRunId: string | undefined): UseQueryResult<TraceHop[]> {
  return useQuery({
    queryKey: ["flow-trace", rootRunId],
    queryFn: async (): Promise<TraceHop[]> => {
      if (isSupabaseConfigured && supabase && rootRunId) {
        const { data, error } = await supabase
          .from("runs")
          .select("id,agent_id,hop,handoff_mode,status,cost_usd,parent_run_id")
          .eq("root_run_id", rootRunId)
          .order("hop", { ascending: true });
        if (error) throw error;
        return (data ?? []).map((r) => ({
          runId: r.id,
          agentId: r.agent_id,
          hop: r.hop ?? 0,
          mode: r.handoff_mode,
          status: r.status,
          cost: Number(r.cost_usd ?? 0),
          parentRunId: r.parent_run_id ?? undefined,
        }));
      }
      return [];
    },
    enabled: rootRunId != null,
    refetchInterval: rootRunId ? 2000 : false,
  });
}
