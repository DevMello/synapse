// Env-var hooks (per-agent) → Supabase env_var_refs. Metadata only; secret values
// are never selected (value_plain is null for secret rows).
import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import { supabase, isSupabaseConfigured } from "../../lib/supabase";
import * as mock from "../../data/mock";
import type { EnvVar } from "../../types";
import { useCurrentAgent } from "../../screens/agent/context";
import { toEnvVar } from "../adapters/env";

export function useEnvVars(): UseQueryResult<EnvVar[]> {
  const agentId = useCurrentAgent().id;
  return useQuery({
    queryKey: ["env", agentId],
    queryFn: async () => {
      if (isSupabaseConfigured && supabase) {
        const { data, error } = await supabase
          .from("env_var_refs")
          .select("*")
          .eq("agent_id", agentId)
          .order("name");
        if (error) throw error;
        return data.map(toEnvVar);
      }
      return mock.envVars;
    },
  });
}
