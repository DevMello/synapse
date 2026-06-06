// DB row → UI view-model. Worker unit 4 implements; foundation stub throws.
// Worker may widen the param to include the embedded agents row (runs ⋈ agents) to
// denormalize the agent name.
import type { Database } from "../../lib/database.types";
import type { Run } from "../../types";

type RunRow = Database["public"]["Tables"]["runs"]["Row"];

export function toRun(_row: RunRow): Run {
  throw new Error("toRun not implemented");
}
