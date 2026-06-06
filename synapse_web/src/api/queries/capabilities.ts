// Capability catalog hook → Supabase plugins catalog. Per-daemon capability state
// lives on each Daemon (see queries/daemons.ts).
import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import { supabase, isSupabaseConfigured } from "../../lib/supabase";
import * as mock from "../../data/mock";
import type { CapabilityDef } from "../../types";
import { toCapabilityDef } from "../adapters/capabilities";

export function useCapabilityDefs(): UseQueryResult<CapabilityDef[]> {
  return useQuery({
    queryKey: ["capabilityDefs"],
    queryFn: async () => {
      if (isSupabaseConfigured && supabase) {
        const { data, error } = await supabase.from("plugins").select("*").order("name");
        if (error) throw error;
        return data.map(toCapabilityDef);
      }
      return mock.CAP_DEFS;
    },
  });
}
