// Capability catalog hook. Worker unit 12 fills the configured branch.
// Returns the CapabilityDef catalog (the installable MCP servers / plugins). The
// per-daemon capability *state* lives on each Daemon (see queries/daemons.ts).
import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import { supabase, isSupabaseConfigured } from "../../lib/supabase";
import * as mock from "../../data/mock";
import type { CapabilityDef } from "../../types";

export function useCapabilityDefs(): UseQueryResult<CapabilityDef[]> {
  return useQuery({
    queryKey: ["capabilityDefs"],
    queryFn: async () => {
      if (isSupabaseConfigured && supabase) {
        // TODO(worker:capabilities): plugins catalog → CapabilityDef[]
        return mock.CAP_DEFS;
      }
      return mock.CAP_DEFS;
    },
  });
}
