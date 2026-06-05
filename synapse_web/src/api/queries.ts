// Synapse Web UI — server-state hooks (TanStack Query). Today they resolve the
// typed mock fleet; this is the single seam where real REST (same-origin, served
// by the Cloud Backend) and the Supabase data API drop in. Screens never import
// src/data/mock directly — they go through these hooks so the swap is local.
import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import * as mock from "../data/mock";
import type {
  Agent, Alert, Approval, Daemon, EnvVar, LogLine, MemoryEntry, Org, Run, Skill,
  Template, TraceLine, Version,
} from "../types";

// Resolve mock data through a microtask so hooks behave like real async queries.
function mockQuery<T>(value: T): Promise<T> {
  return Promise.resolve(value);
}

export function useOrg(): UseQueryResult<Org> {
  return useQuery({ queryKey: ["org"], queryFn: () => mockQuery(mock.ORG) });
}
export function useDaemons(): UseQueryResult<Daemon[]> {
  return useQuery({ queryKey: ["daemons"], queryFn: () => mockQuery(mock.daemons) });
}
export function useDaemon(id: string | undefined): UseQueryResult<Daemon | undefined> {
  return useQuery({
    queryKey: ["daemon", id],
    queryFn: () => mockQuery(mock.daemons.find((d) => d.id === id)),
    enabled: id != null,
  });
}
export function useAgents(): UseQueryResult<Agent[]> {
  return useQuery({ queryKey: ["agents"], queryFn: () => mockQuery(mock.agents) });
}
export function useAgent(id: string | undefined): UseQueryResult<Agent | undefined> {
  return useQuery({
    queryKey: ["agent", id],
    queryFn: () => mockQuery(mock.agents.find((a) => a.id === id)),
    enabled: id != null,
  });
}
export function useRuns(): UseQueryResult<Run[]> {
  return useQuery({ queryKey: ["runs"], queryFn: () => mockQuery(mock.runs) });
}
export function useApprovals(): UseQueryResult<Approval[]> {
  return useQuery({ queryKey: ["approvals"], queryFn: () => mockQuery(mock.approvals) });
}
export function useAlerts(): UseQueryResult<Alert[]> {
  return useQuery({ queryKey: ["alerts"], queryFn: () => mockQuery(mock.alerts) });
}
export function useEnvVars(): UseQueryResult<EnvVar[]> {
  return useQuery({ queryKey: ["env"], queryFn: () => mockQuery(mock.envVars) });
}
export function useMemory(): UseQueryResult<MemoryEntry[]> {
  return useQuery({ queryKey: ["memory"], queryFn: () => mockQuery(mock.memory) });
}
export function useLogLines(): UseQueryResult<LogLine[]> {
  return useQuery({ queryKey: ["logs"], queryFn: () => mockQuery(mock.logLines) });
}
export function useSkills(): UseQueryResult<Skill[]> {
  return useQuery({ queryKey: ["skills"], queryFn: () => mockQuery(mock.skills) });
}
export function useVersions(): UseQueryResult<Version[]> {
  return useQuery({ queryKey: ["versions"], queryFn: () => mockQuery(mock.versions) });
}
export function useTemplates(): UseQueryResult<Template[]> {
  return useQuery({ queryKey: ["templates"], queryFn: () => mockQuery(mock.templates) });
}
export function usePrompt(): UseQueryResult<string> {
  return useQuery({ queryKey: ["prompt"], queryFn: () => mockQuery(mock.PROMPT) });
}
export function useTraceLines(): UseQueryResult<TraceLine[]> {
  return useQuery({ queryKey: ["traceLines"], queryFn: () => mockQuery(mock.traceLines) });
}

// Synchronous accessors for components that just need the busy-fleet snapshot
// (e.g. cross-referencing an agent's host daemon) without a hook subscription.
export const data = mock;
