// DB row → UI view-model. Worker unit 2 implements; foundation stub throws.
// relativeTime(last_seen); status 'revoked' → treat as offline for the UI's
// two-state DaemonStatus. capabilities[] joined from daemon_capabilities + plugins.
import type { Database } from "../../lib/database.types";
import type { Daemon } from "../../types";

type DaemonOverviewRow = Database["public"]["Views"]["daemon_overview"]["Row"];

export function toDaemon(_row: DaemonOverviewRow): Daemon {
  throw new Error("toDaemon not implemented");
}
