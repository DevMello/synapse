// DB row → UI view-model. Worker unit 9 implements; foundation stub throws.
// t (cmd/info/ok/warn) derived from role/content; text from content_redacted.
import type { Database } from "../../lib/database.types";
import type { TraceLine } from "../../types";

type TraceRow = Database["public"]["Tables"]["reasoning_traces"]["Row"];

export function toTraceLine(_row: TraceRow): TraceLine {
  throw new Error("toTraceLine not implemented");
}
