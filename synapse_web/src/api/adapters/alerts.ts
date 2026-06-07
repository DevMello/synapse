// DB row → UI view-model. detector→type; icon composed; sev from anomaly_severity;
// title/detail from detail jsonb.
import type { Database } from "../../lib/database.types";
import type { Alert, AlertSeverity } from "../../types";
import { relativeTime } from "../format";

type AnomalyRow = Database["public"]["Tables"]["anomaly_events"]["Row"] & {
  agents: { name: string } | null;
  daemons: { name: string } | null;
};

const TYPE: Record<string, string> = {
  cost_spike: "cost",
  prompt_injection: "prompt-injection",
  daemon_offline: "offline",
};

const ICON: Record<string, string> = {
  cost: "trending-up",
  offline: "wifi-off",
  "prompt-injection": "shield-alert",
};

export function toAlert(row: AnomalyRow): Alert {
  const type = TYPE[row.detector] ?? row.detector;
  const detail = (row.detail ?? {}) as { title?: string; message?: string };
  const sev: AlertSeverity = row.severity === "info" ? "info" : "warn";
  return {
    id: row.id,
    type,
    icon: ICON[type] ?? "alert-triangle",
    sev,
    title: detail.title ?? row.detector,
    metric: row.metric ?? "",
    baseline: row.baseline != null ? String(row.baseline) : "",
    observed: row.observed != null ? String(row.observed) : "",
    agent: row.agents?.name ?? row.daemons?.name ?? "—",
    when: relativeTime(row.created_at),
    detail: detail.message ?? "",
  };
}
