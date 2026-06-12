// Handoff flows + chain grants (§11). Flow CRUD goes through the Supabase data API
// (RLS, members read+write); publish/revoke go through the Cloud Backend (it compiles +
// signs the chain grant). In mock mode (no Supabase env) an in-memory store backs the
// canvas so it is fully interactive offline — the mutations update it and the publish
// no-ops, mirroring queries/grants.ts.
import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseQueryResult,
} from "@tanstack/react-query";
import { supabase, isSupabaseConfigured } from "../../lib/supabase";
import type { AgentFlow, ChainGrant } from "../../types";
import { apiPost, isApiConfigured } from "../client";
import { flowToRow, toChainGrant, toFlow } from "../adapters/flows";
import { seedMockFlows } from "../../screens/flow/templates";

// ── in-memory mock store (offline / design mode) ─────────────────────────────
let MOCK_FLOWS: AgentFlow[] = seedMockFlows();

function uid(prefix: string): string {
  const rnd =
    typeof crypto !== "undefined" && "randomUUID" in crypto
      ? crypto.randomUUID()
      : Math.random().toString(16).slice(2);
  return `${prefix}_${rnd}`;
}

// Resolve the caller's org_id from the Supabase session (app/user metadata), matching
// the pattern in queries/runs.ts and queries/approvals.ts.
async function currentOrgId(): Promise<string> {
  if (!supabase) return "";
  const { data } = await supabase.auth.getUser();
  return (
    (data.user?.app_metadata?.org_id as string | undefined) ??
    (data.user?.user_metadata?.org_id as string | undefined) ??
    ""
  );
}

// ── flows ────────────────────────────────────────────────────────────────────
export function useFlows(): UseQueryResult<AgentFlow[]> {
  return useQuery({
    queryKey: ["flows"],
    queryFn: async () => {
      if (isSupabaseConfigured && supabase) {
        const { data, error } = await supabase
          .from("agent_flows")
          .select("*")
          .neq("status", "archived")
          .order("updated_at", { ascending: false });
        if (error) throw error;
        return data.map(toFlow);
      }
      return [...MOCK_FLOWS];
    },
  });
}

export function useFlow(flowId: string | undefined): UseQueryResult<AgentFlow | undefined> {
  return useQuery({
    queryKey: ["flow", flowId],
    queryFn: async () => {
      if (isSupabaseConfigured && supabase && flowId) {
        const { data, error } = await supabase
          .from("agent_flows")
          .select("*")
          .eq("id", flowId)
          .maybeSingle();
        if (error) throw error;
        return data ? toFlow(data) : undefined;
      }
      return MOCK_FLOWS.find((f) => f.id === flowId);
    },
    enabled: flowId != null,
  });
}

export function useCreateFlow() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (flow: AgentFlow): Promise<AgentFlow> => {
      if (isSupabaseConfigured && supabase) {
        const { data, error } = await supabase
          .from("agent_flows")
          .insert({ ...flowToRow(flow), org_id: await currentOrgId() })
          .select("*")
          .single();
        if (error) throw error;
        return toFlow(data);
      }
      const created = { ...flow, id: uid("flw"), created: "just now", updated: "just now" };
      MOCK_FLOWS = [created, ...MOCK_FLOWS];
      return created;
    },
    onSettled: () => qc.invalidateQueries({ queryKey: ["flows"] }),
  });
}

export function useSaveFlow() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (flow: AgentFlow): Promise<AgentFlow> => {
      if (isSupabaseConfigured && supabase) {
        const { data, error } = await supabase
          .from("agent_flows")
          .update({ ...flowToRow(flow), updated_at: new Date().toISOString() })
          .eq("id", flow.id)
          .select("*")
          .single();
        if (error) throw error;
        return toFlow(data);
      }
      const next = { ...flow, updated: "just now" };
      MOCK_FLOWS = MOCK_FLOWS.map((f) => (f.id === flow.id ? next : f));
      return next;
    },
    onSettled: (_d, _e, flow) => {
      qc.invalidateQueries({ queryKey: ["flows"] });
      qc.invalidateQueries({ queryKey: ["flow", flow.id] });
    },
  });
}

export function useArchiveFlow() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (flowId: string) => {
      if (isSupabaseConfigured && supabase) {
        const { error } = await supabase
          .from("agent_flows")
          .update({ status: "archived" })
          .eq("id", flowId);
        if (error) throw error;
        return;
      }
      MOCK_FLOWS = MOCK_FLOWS.filter((f) => f.id !== flowId);
    },
    onSettled: () => qc.invalidateQueries({ queryKey: ["flows"] }),
  });
}

// ── chain grants ─────────────────────────────────────────────────────────────
export function useChainGrants(): UseQueryResult<ChainGrant[]> {
  return useQuery({
    queryKey: ["chain-grants"],
    queryFn: async () => {
      if (isSupabaseConfigured && supabase) {
        const { data, error } = await supabase
          .from("agent_chain_grants")
          .select("*")
          .order("created_at", { ascending: false });
        if (error) throw error;
        return data.map(toChainGrant);
      }
      return [];
    },
  });
}

export function usePublishFlow() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ flowId, expiresInSeconds }: { flowId: string; expiresInSeconds: number }) => {
      if (isApiConfigured()) {
        await apiPost(`/flows/${flowId}/publish`, { expires_in_seconds: expiresInSeconds });
      } else {
        // Offline: mark the flow published so the canvas reflects the signed state.
        MOCK_FLOWS = MOCK_FLOWS.map((f) =>
          f.id === flowId ? { ...f, status: "published", publishedGrantId: uid("chn") } : f,
        );
      }
    },
    onSettled: (_d, _e, v) => {
      qc.invalidateQueries({ queryKey: ["flows"] });
      qc.invalidateQueries({ queryKey: ["flow", v.flowId] });
      qc.invalidateQueries({ queryKey: ["chain-grants"] });
    },
  });
}

export function useRevokeChainGrant() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ grantId }: { grantId: string; flowId?: string }) => {
      if (isApiConfigured()) await apiPost(`/chain-grants/${grantId}/revoke`);
    },
    onSettled: (_d, _e, v) => {
      qc.invalidateQueries({ queryKey: ["chain-grants"] });
      qc.invalidateQueries({ queryKey: ["flows"] });
      if (v.flowId) qc.invalidateQueries({ queryKey: ["flow", v.flowId] });
    },
  });
}
