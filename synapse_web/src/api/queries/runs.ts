// Run hooks → Supabase runs ⋈ agents (denormalize agent name).
import { useQuery, useMutation, useQueryClient, type UseQueryResult } from "@tanstack/react-query";
import { supabase, isSupabaseConfigured } from "../../lib/supabase";
import * as mock from "../../data/mock";
import type { Run } from "../../types";
import { toRun } from "../adapters/runs";
import { apiPost } from "../client";
import { buildCommandAuth } from "../../lib/commandAuth";

type RunRow = Parameters<typeof toRun>[0];

async function getActorIds(): Promise<{ userId: string; orgId: string }> {
  if (!supabase) return { userId: "", orgId: "" };
  const { data } = await supabase.auth.getUser();
  const userId = data.user?.id ?? "";
  // org_id may be in app_metadata or user_metadata — check both
  const orgId =
    (data.user?.app_metadata?.org_id as string | undefined) ??
    (data.user?.user_metadata?.org_id as string | undefined) ??
    "";
  return { userId, orgId };
}

export function useStartRun(agentId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: {
      daemon_id?: string;
      trigger?: string;
      input?: Record<string, unknown>;
      idempotency_key?: string;
    }) => {
      let command_auth_token: Awaited<ReturnType<typeof buildCommandAuth>> | undefined;
      if (body.daemon_id) {
        try {
          const { userId, orgId } = await getActorIds();
          const payload = {
            run_id: "",
            agent_id: agentId,
            trigger: body.trigger ?? "manual",
            input: body.input ?? {},
          };
          command_auth_token = await buildCommandAuth(
            "agent.run", agentId, body.daemon_id, orgId, userId, payload,
          );
        } catch { /* degrade gracefully */ }
      }
      return apiPost(`/agents/${agentId}/runs`, {
        trigger: body.trigger ?? "manual",
        idempotency_key: body.idempotency_key,
        input: body.input,
        command_auth_token,
      });
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["runs"] });
      void qc.invalidateQueries({ queryKey: ["agents", agentId, "runs"] });
    },
  });
}

export function useCancelRun(runId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: { daemon_id?: string; agent_id?: string }) => {
      let command_auth_token: Awaited<ReturnType<typeof buildCommandAuth>> | undefined;
      if (body.daemon_id && body.agent_id) {
        try {
          const { userId, orgId } = await getActorIds();
          const payload = { run_id: runId, agent_id: body.agent_id };
          command_auth_token = await buildCommandAuth(
            "agent.cancel", body.agent_id, body.daemon_id, orgId, userId, payload,
          );
        } catch { /* degrade gracefully */ }
      }
      return apiPost(`/runs/${runId}/cancel`, { command_auth_token });
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["runs"] });
    },
  });
}

export function useRuns(): UseQueryResult<Run[]> {
  return useQuery({
    queryKey: ["runs"],
    queryFn: async () => {
      if (isSupabaseConfigured && supabase) {
        const { data, error } = await supabase
          .from("runs")
          .select("*, agents(name)")
          .order("created_at", { ascending: false })
          .limit(100);
        if (error) throw error;
        return (data as unknown as RunRow[]).map(toRun);
      }
      return mock.runs;
    },
  });
}
