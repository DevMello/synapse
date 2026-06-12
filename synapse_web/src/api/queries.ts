// Synapse Web UI — server-state hooks barrel (TanStack Query). The hooks live in
// per-domain modules under ./queries/* (one file per domain so the Supabase
// migration parallelizes cleanly); this barrel re-exports them so screens keep
// importing from "../api/queries" unchanged. Each hook resolves the typed mock
// fleet until Supabase is configured (isSupabaseConfigured), then real data — the
// single seam where the data API drops in.
export { useOrg, useOrgs, useCreateOrg, type OrgRecord } from "./queries/org";
export { useDaemons, useDaemon } from "./queries/daemons";
export { useAgents, useAgent } from "./queries/agents";
export { useRuns } from "./queries/runs";
export { useApprovals } from "./queries/approvals";
export { useAlerts } from "./queries/alerts";
export { useEnvVars } from "./queries/env";
export { useMemory } from "./queries/memory";
export { useLogLines } from "./queries/logs";
export { useTraceLines } from "./queries/trace";
export { useVersions, usePrompt } from "./queries/versions";
export { useTemplates } from "./queries/templates";
export { useSkills } from "./queries/skills";
export { useCapabilityDefs } from "./queries/capabilities";
export {
  useMembers, useInvitations, useInviteMember, useUpdateMemberRole, useRemoveMember, useRevokeInvitation,
} from "./queries/members";
export {
  useTeams, useCreateTeam, useDeleteTeam, useAddTeamMember, useRemoveTeamMember,
} from "./queries/teams";
export { useOrchestrationGrants, useMintGrant, useRevokeGrant } from "./queries/grants";
export { useAgentLineage } from "./queries/lineage";
export {
  useFlows, useFlow, useCreateFlow, useSaveFlow, useArchiveFlow,
  useChainGrants, usePublishFlow, useRevokeChainGrant,
} from "./queries/flows";
export { useFlowTrace } from "./queries/flowTrace";

// Synchronous accessor for components that need the busy-fleet snapshot (e.g.
// cross-referencing an agent's host daemon) without a hook subscription. Screen-
// wiring units migrate these reads to hooks / the query cache; until then it
// resolves the mock fleet.
import * as mock from "../data/mock";
export const data = mock;
