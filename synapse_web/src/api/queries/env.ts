// Env-var hooks (per-agent). Worker unit 7 fills the configured branch.
// NEVER select secret values — env_var_refs holds metadata only; value_plain is
// present only for non-secret vars.
import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import { supabase, isSupabaseConfigured } from "../../lib/supabase";
import * as mock from "../../data/mock";
import type { EnvVar } from "../../types";
import { useCurrentAgent } from "../../screens/agent/context";

export function useEnvVars(): UseQueryResult<EnvVar[]> {
  const agentId = useCurrentAgent().id;
  return useQuery({
    queryKey: ["env", agentId],
    queryFn: async () => {
      if (isSupabaseConfigured && supabase) {
        // TODO(worker:env): env_var_refs for agentId → toEnvVar (secret/value_plain, origin map)
        return mock.envVars;
      }
      return mock.envVars;
    },
  });
}
