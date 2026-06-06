// Skill hooks (per-agent). Worker unit 11 fills the configured branch.
import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import { supabase, isSupabaseConfigured } from "../../lib/supabase";
import * as mock from "../../data/mock";
import type { Skill } from "../../types";
import { useCurrentAgent } from "../../screens/agent/context";

export function useSkills(): UseQueryResult<Skill[]> {
  const agentId = useCurrentAgent().id;
  return useQuery({
    queryKey: ["skills", agentId],
    queryFn: async () => {
      if (isSupabaseConfigured && supabase) {
        // TODO(worker:skills): agent_skills for agentId → toSkill
        return mock.skills;
      }
      return mock.skills;
    },
  });
}
