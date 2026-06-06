// DB row → UI view-model. Worker unit 3 implements; foundation stub throws.
// type 'cli'→"CLI tool", 'api'→"API model"; status derivation (running/idle/passed/
// offline); spend/tokens/runsTotal/errRate from rollup columns; relativeTime(last_run_at).
import type { Database } from "../../lib/database.types";
import type { Agent } from "../../types";

type AgentOverviewRow = Database["public"]["Views"]["agent_overview"]["Row"];

export function toAgent(_row: AgentOverviewRow): Agent {
  throw new Error("toAgent not implemented");
}
