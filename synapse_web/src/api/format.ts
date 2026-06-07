// Synapse Web UI — display formatting helpers. The DB stores timestamps; screens
// expect relative strings ("2 min ago"). Adapters call relativeTime() so screens
// stay unchanged.
import { formatDistanceToNowStrict } from "date-fns";

export function relativeTime(ts: string | number | Date | null | undefined): string {
  if (ts == null) return "—";
  const d = ts instanceof Date ? ts : new Date(ts);
  if (Number.isNaN(d.getTime())) return "—";
  return formatDistanceToNowStrict(d, { addSuffix: true });
}
