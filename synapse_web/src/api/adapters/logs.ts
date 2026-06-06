// DB row → UI view-model. Worker unit 9 implements; foundation stub throws.
// time from created_at (HH:MM:SS); tag from level/fields; msg from message;
// guard from fields jsonb.
import type { Database } from "../../lib/database.types";
import type { LogLine } from "../../types";

type LogRow = Database["public"]["Tables"]["logs"]["Row"];

export function toLogLine(_row: LogRow): LogLine {
  throw new Error("toLogLine not implemented");
}
