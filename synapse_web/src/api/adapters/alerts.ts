// DB row → UI view-model. Worker unit 6 implements; foundation stub throws.
// detector→type ('cost_spike'→'cost', etc.); icon composed from type; sev from
// anomaly_severity (warning→"warn"); title/detail from detail jsonb.
import type { Database } from "../../lib/database.types";
import type { Alert } from "../../types";

type AnomalyRow = Database["public"]["Tables"]["anomaly_events"]["Row"];

export function toAlert(_row: AnomalyRow): Alert {
  throw new Error("toAlert not implemented");
}
