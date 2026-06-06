// Org hook → Supabase (the signed-in user's org + their profile).
import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import { supabase, isSupabaseConfigured } from "../../lib/supabase";
import * as mock from "../../data/mock";
import type { Org } from "../../types";
import { toOrg } from "../adapters/org";

export function useOrg(): UseQueryResult<Org> {
  return useQuery({
    queryKey: ["org"],
    queryFn: async () => {
      if (isSupabaseConfigured && supabase) {
        const { data: auth } = await supabase.auth.getUser();
        const { data: org, error } = await supabase
          .from("organizations")
          .select("*")
          .limit(1)
          .maybeSingle();
        if (error) throw error;
        if (!org) return mock.ORG;
        let user = null;
        if (auth.user) {
          const { data: u } = await supabase
            .from("users")
            .select("*")
            .eq("id", auth.user.id)
            .maybeSingle();
          user = u;
        }
        return toOrg(org, user);
      }
      return mock.ORG;
    },
  });
}
