// Template hooks. Worker unit 11 fills the configured branch.
import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import { supabase, isSupabaseConfigured } from "../../lib/supabase";
import * as mock from "../../data/mock";
import type { Template } from "../../types";

export function useTemplates(): UseQueryResult<Template[]> {
  return useQuery({
    queryKey: ["templates"],
    queryFn: async () => {
      if (isSupabaseConfigured && supabase) {
        // TODO(worker:templates): marketplace_listings kind=agent + synthetic "Blank" → toTemplate
        return mock.templates;
      }
      return mock.templates;
    },
  });
}
