// Synapse Web UI — typed domain models. These mirror the cloud's records and the
// telemetry shapes the Web UI renders. The mock fleet in src/data/mock.ts conforms
// to these; the TanStack hooks in src/api/queries.ts are the seam to real data.

export type DaemonStatus = "online" | "offline";
export type CapabilityKind = "MCP server" | "plugin";
export type CapabilityState = "ready" | "installing" | "available" | "failed";

export interface Org {
  name: string;
  plan: string;
  operator: string;
  initials: string;
}

export interface CapabilityDef {
  id: string;
  name: string;
  kind: CapabilityKind;
  desc: string;
  builtin: boolean;
}

export interface Capability extends CapabilityDef {
  state: CapabilityState;
}

export interface Daemon {
  id: string;
  name: string;
  hostname: string;
  os: string;
  ip: string;
  status: DaemonStatus;
  version: string;
  lastSeen: string;
  cpu: number;
  mem: number;
  activeRuns: number;
  uptime: number;
  tags: string[];
  platform: string;
  heartbeat: number[];
  capabilities: Capability[];
}

export type AgentType = "CLI tool" | "API model";
export type AgentStatus = "running" | "idle" | "passed" | "offline";

export interface Agent {
  id: string;
  name: string;
  type: AgentType;
  engine: string;
  daemonId: string;
  status: AgentStatus;
  avail: boolean;
  lastRun: string;
  nextRun: string;
  spendToday: number;
  runsTotal: number;
  errRate: number;
  tokensToday: number;
  model: string;
  desc: string;
}

export type RunTrigger = "webhook" | "schedule" | "manual";
export type RunStatus = "running" | "blocked" | "passed" | "recovering";

export interface Run {
  id: string;
  agentId: string;
  agent: string;
  trigger: RunTrigger;
  status: RunStatus;
  started: string;
  dur: string;
  cost: number;
  tokens: number;
  exit: string;
}

export type Severity = "block" | "require-approval" | "warn";

export interface Approval {
  id: string;
  agentId: string;
  agent: string;
  daemon: string;
  severity: Exclude<Severity, "warn">;
  action: string;
  command: string;
  reason: string;
  context: string;
  when: string;
}

export type AlertSeverity = "warn" | "info";

export interface Alert {
  id: string;
  type: string;
  icon: string;
  sev: AlertSeverity;
  title: string;
  metric: string;
  baseline: string;
  observed: string;
  agent: string;
  when: string;
  detail: string;
}

export type EnvOrigin = "cloud" | "local";

export interface EnvVar {
  key: string;
  secret: boolean;
  value?: string;
  origin: EnvOrigin;
  updated: string;
  by: string;
}

export interface MemoryEntry {
  key: string;
  ns: string;
  val: string;
  tags: string[];
  size: string;
  updated: string;
}

export type LogTag = "plan" | "build" | "qa" | "mcp";

export interface LogLine {
  time: string;
  tag: LogTag;
  msg: string;
  guard?: string;
}

export interface Skill {
  name: string;
  scope: string;
  size: string;
}

export type VersionTag = "production" | "known-good" | string;

export interface Version {
  id: string;
  label: string;
  author: string;
  when: string;
  msg: string;
  tags: VersionTag[];
  current?: boolean;
}

export interface Template {
  id: string;
  name: string;
  desc: string;
  kicker: string;
  icon: string;
  rating?: number;
}

export type TraceKind = "cmd" | "info" | "ok" | "warn";

export interface TraceLine {
  t: TraceKind;
  text: string;
  comment?: string;
}

// Org membership — mirrors the `memberships` row joined to the member's user.
export type Role = "owner" | "admin" | "operator" | "viewer";

export interface Member {
  userId: string; // user id for real members; the invitation id for pending invites
  name: string;
  email: string;
  role: Role;
  init: string;
  active: string; // relative "joined" time, or "invited" for a pending invitation
  pending?: boolean; // true = an unaccepted org_invitations row, not yet a member
}

// Team / business-unit hierarchy within an org (teams self-nest via parentId).
export interface TeamMemberLite {
  userId: string;
  name: string;
  init: string;
}

export interface TeamNode {
  id: string;
  name: string;
  parentId: string | null;
  members: TeamMemberLite[];
  children: TeamNode[];
}
