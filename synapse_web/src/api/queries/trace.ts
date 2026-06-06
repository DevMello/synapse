// Trace hooks (per-agent live trace) → Supabase reasoning_traces.
import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import { supabase, isSupabaseConfigured } from "../../lib/supabase";
import * as mock from "../../data/mock";
import type { TraceLine } from "../../types";
import { useCurrentAgent } from "../../screens/agent/context";
import { toTraceLine } from "../adapters/trace";

export function useTraceLines(): UseQueryResult<TraceLine[]> {
  const agentId = useCurrentAgent().id;
  return useQuery({
    queryKey: ["traceLines", agentId],
    queryFn: async () => {
      if (isSupabaseConfigured && supabase) {
        const { data, error } = await supabase
          .from("reasoning_traces")
          .select("*")
          .eq("agent_id", agentId)
          .order("seq", { ascending: true })
          .limit(200);
        if (error) throw error;
        return data.map(toTraceLine);
      }
      return mock.traceLines;
    },
  });
}
