// DB row → UI view-model.
import type { Database } from "../../lib/database.types";
import type { TraceLine, TraceKind } from "../../types";

type TraceRow = Database["public"]["Tables"]["reasoning_traces"]["Row"];

export function toTraceLine(row: TraceRow): TraceLine {
  const text = row.content_redacted ?? "";
  const role = (row.role ?? "").toLowerCase();
  let t: TraceKind = "info";
  if (role === "command" || role === "cmd") t = "cmd";
  else if (/blocked|below|fail|warn/i.test(text)) t = "warn";
  else if (/\bok\b|resolved|done|passed|success/i.test(text)) t = "ok";
  return { t, text };
}
