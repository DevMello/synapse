// Version + prompt hooks (per-agent). Worker unit 10 fills the configured branch.
import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import { supabase, isSupabaseConfigured } from "../../lib/supabase";
import * as mock from "../../data/mock";
import type { Version } from "../../types";
import { useCurrentAgent } from "../../screens/agent/context";

export function useVersions(): UseQueryResult<Version[]> {
  const agentId = useCurrentAgent().id;
  return useQuery({
    queryKey: ["versions", agentId],
    queryFn: async () => {
      if (isSupabaseConfigured && supabase) {
        // TODO(worker:versions): agent_versions for agentId, order version desc → toVersion
        return mock.versions;
      }
      return mock.versions;
    },
  });
}

export function usePrompt(): UseQueryResult<string> {
  const agentId = useCurrentAgent().id;
  return useQuery({
    queryKey: ["prompt", agentId],
    queryFn: async () => {
      if (isSupabaseConfigured && supabase) {
        // TODO(worker:versions): agent_versions.prompt of the agent's current_version
        return mock.PROMPT;
      }
      return mock.PROMPT;
    },
  });
}
