// Log hooks (per-agent) → Supabase logs.
import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import { supabase, isSupabaseConfigured } from "../../lib/supabase";
import * as mock from "../../data/mock";
import type { LogLine } from "../../types";
import { useCurrentAgent } from "../../screens/agent/context";
import { toLogLine } from "../adapters/logs";

export function useLogLines(): UseQueryResult<LogLine[]> {
  const agentId = useCurrentAgent().id;
  return useQuery({
    queryKey: ["logs", agentId],
    queryFn: async () => {
      if (isSupabaseConfigured && supabase) {
        const { data, error } = await supabase
          .from("logs")
          .select("*")
          .eq("agent_id", agentId)
          .order("created_at", { ascending: true })
          .limit(200);
        if (error) throw error;
        return data.map(toLogLine);
      }
      return mock.logLines;
    },
  });
}
