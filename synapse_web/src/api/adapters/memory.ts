// DB row → UI view-model.
import type { Database } from "../../lib/database.types";
import type { MemoryEntry } from "../../types";
import { relativeTime } from "../format";

type MemoryRow = Database["public"]["Tables"]["agent_memory"]["Row"];

export function toMemoryEntry(row: MemoryRow): MemoryEntry {
  return {
    key: row.key,
    ns: row.namespace,
    val: row.text_redacted ?? (row.value_redacted ? JSON.stringify(row.value_redacted) : ""),
    tags: row.tags ?? [],
    size: `${((row.bytes ?? 0) / 1024).toFixed(1)} KB`,
    updated: relativeTime(row.updated_at),
  };
}
