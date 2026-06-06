// DB row → UI view-model. Worker unit 7 implements; foundation stub throws.
// secret from env_var_refs.secret; value = secret ? undefined : value_plain;
// origin 'ui'→"cloud", 'local'→"local"; by/updated from updated_by/updated_at.
import type { Database } from "../../lib/database.types";
import type { EnvVar } from "../../types";

type EnvVarRow = Database["public"]["Tables"]["env_var_refs"]["Row"];

export function toEnvVar(_row: EnvVarRow): EnvVar {
  throw new Error("toEnvVar not implemented");
}
