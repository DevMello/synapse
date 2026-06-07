// DB row → UI view-model.
import type { Database } from "../../lib/database.types";
import type { LogLine, LogTag } from "../../types";

type LogRow = Database["public"]["Tables"]["logs"]["Row"];

const LOG_TAGS: LogTag[] = ["plan", "build", "qa", "mcp"];

export function toLogLine(row: LogRow): LogLine {
  const fields = (row.fields ?? {}) as { tag?: string; guard?: string };
  const raw = fields.tag ?? row.level ?? "plan";
  const tag = (LOG_TAGS as string[]).includes(raw) ? (raw as LogTag) : "plan";
  return {
    time: new Date(row.created_at).toLocaleTimeString("en-GB"),
    tag,
    msg: row.message ?? "",
    guard: fields.guard,
  };
}
