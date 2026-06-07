// DB row → UI view-model. NEVER expose secret values: value is set only for
// non-secret rows (value_plain). origin 'ui'→"cloud", 'local'→"local".
import type { Database } from "../../lib/database.types";
import type { EnvVar } from "../../types";
import { relativeTime } from "../format";

type EnvVarRow = Database["public"]["Tables"]["env_var_refs"]["Row"];

export function toEnvVar(row: EnvVarRow): EnvVar {
  return {
    key: row.name,
    secret: row.secret,
    value: row.secret ? undefined : row.value_plain ?? undefined,
    origin: row.origin === "local" ? "local" : "cloud",
    updated: relativeTime(row.updated_at),
    by: row.updated_by ?? "—",
  };
}
