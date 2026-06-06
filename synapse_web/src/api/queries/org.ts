// Org hook. Worker unit 1 fills the configured branch.
import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import { supabase, isSupabaseConfigured } from "../../lib/supabase";
import * as mock from "../../data/mock";
import type { Org } from "../../types";

export function useOrg(): UseQueryResult<Org> {
  return useQuery({
    queryKey: ["org"],
    queryFn: async () => {
      if (isSupabaseConfigured && supabase) {
        // TODO(worker:org): organizations (the user's org) + current users row → toOrg
        return mock.ORG;
      }
      return mock.ORG;
    },
  });
}
