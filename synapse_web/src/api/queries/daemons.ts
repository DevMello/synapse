// Daemon hooks → Supabase daemon_overview view (+ daemon_capabilities/plugins for
// per-daemon capability state, which lives on each Daemon per the type).
import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import { supabase, isSupabaseConfigured } from "../../lib/supabase";
import * as mock from "../../data/mock";
import type { Capability, Daemon } from "../../types";
import { toDaemon, toCapability } from "../adapters/daemons";

type DaemonCapRow = Parameters<typeof toCapability>[0];

async function capsForDaemons(ids: string[]): Promise<Map<string, Capability[]>> {
  const byDaemon = new Map<string, Capability[]>();
  if (!supabase || ids.length === 0) return byDaemon;
  const { data, error } = await supabase
    .from("daemon_capabilities")
    .select("*, plugins(name, kind)")
    .in("daemon_id", ids);
  if (error) throw error;
  for (const c of data ?? []) {
    const list = byDaemon.get(c.daemon_id) ?? [];
    list.push(toCapability(c as unknown as DaemonCapRow));
    byDaemon.set(c.daemon_id, list);
  }
  return byDaemon;
}

export function useDaemons(): UseQueryResult<Daemon[]> {
  return useQuery({
    queryKey: ["daemons"],
    queryFn: async () => {
      if (isSupabaseConfigured && supabase) {
        const { data, error } = await supabase.from("daemon_overview").select("*");
        if (error) throw error;
        const ids = data.map((r) => r.id).filter((x): x is string => Boolean(x));
        const caps = await capsForDaemons(ids);
        return data.map((r) => toDaemon(r, r.id ? caps.get(r.id) ?? [] : []));
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
        const { data, error } = await supabase
          .from("daemon_overview")
          .select("*")
          .eq("id", id!)
          .maybeSingle();
        if (error) throw error;
        if (!data) return undefined;
        const caps = await capsForDaemons([id!]);
        return toDaemon(data, caps.get(id!) ?? []);
      }
      return mock.daemons.find((d) => d.id === id);
    },
    enabled: id != null,
  });
}
