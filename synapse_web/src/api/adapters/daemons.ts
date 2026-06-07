// DB row → UI view-model. relativeTime(last_seen); status 'revoked' → offline.
// capabilities[] built from daemon_capabilities ⋈ plugins.
import type { Database } from "../../lib/database.types";
import type { Capability, CapabilityKind, CapabilityState, Daemon } from "../../types";
import { relativeTime } from "../format";

type DaemonOverviewRow = Database["public"]["Views"]["daemon_overview"]["Row"];
type DaemonCapRow = Database["public"]["Tables"]["daemon_capabilities"]["Row"] & {
  plugins: { name: string; kind: Database["public"]["Enums"]["capability_kind"] } | null;
};

const CAP_STATE: Record<string, CapabilityState> = {
  ready: "ready",
  installing: "installing",
  failed: "failed",
};

export function toCapability(dc: DaemonCapRow): Capability {
  const rawKind = dc.plugins?.kind ?? dc.kind;
  const kind: CapabilityKind = rawKind === "mcp" ? "MCP server" : "plugin";
  return {
    id: dc.plugin_id ?? dc.id,
    name: dc.plugins?.name ?? "capability",
    kind,
    desc: "",
    builtin: false,
    state: CAP_STATE[dc.install_status] ?? "available",
  };
}

export function toDaemon(row: DaemonOverviewRow, capabilities: Capability[] = []): Daemon {
  const online = row.status === "online";
  return {
    id: row.id ?? "",
    name: row.name ?? "",
    hostname: row.hostname ?? "",
    os: row.os_version ?? "",
    ip: row.last_ip ? String(row.last_ip) : "",
    status: online ? "online" : "offline",
    version: row.version ?? "",
    lastSeen: relativeTime(row.last_seen),
    cpu: Math.round(row.cpu ?? 0),
    mem: Math.round(row.mem ?? 0),
    activeRuns: row.active_runs ?? 0,
    uptime: 99.9,
    tags: row.tags ?? [],
    platform: row.platform ?? "",
    heartbeat: online
      ? [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1]
      : [1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0],
    capabilities,
  };
}
