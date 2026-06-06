// Daemon hooks. Worker unit 2 fills the configured branch.
// Daemon.capabilities is populated by joining daemon_capabilities + plugins inside
// this module's adapter (toDaemon) — capabilities live on the daemon, per the type.
import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import { supabase, isSupabaseConfigured } from "../../lib/supabase";
import * as mock from "../../data/mock";
import type { Daemon } from "../../types";

export function useDaemons(): UseQueryResult<Daemon[]> {
  return useQuery({
    queryKey: ["daemons"],
    queryFn: async () => {
      if (isSupabaseConfigured && supabase) {
        // TODO(worker:daemons): daemon_overview view (+ daemon_capabilities/plugins) → toDaemon
        return mock.daemons;
      }
      return mock.daemons;
    },
  });
}

export function useDaemon(id: string | undefined): UseQueryResult<Daemon | undefined> {
  return useQuery({
    queryKey: ["daemon", id],
    queryFn: async () => {
      if (isSupabaseConfigured && supabase) {
        // TODO(worker:daemons): daemon_overview where id = $id → toDaemon
        return mock.daemons.find((d) => d.id === id);
      }
      return mock.daemons.find((d) => d.id === id);
    },
    enabled: id != null,
  });
}
