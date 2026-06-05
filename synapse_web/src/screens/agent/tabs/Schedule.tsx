import { useMemo, useState } from "react";
import { Icon, Button } from "../../../components/Primitives";
import { Segmented } from "../../../components/Common";
import { useCurrentAgent } from "../context";
import { useUI } from "../../../store/ui";

type Mode = "webhook" | "cron" | "interval" | "oneshot";
type MissedPolicy = "skip" | "once" | "coalesce";

const MODES: { id: Mode; icon: string; name: string; desc: string }[] = [
  { id: "webhook", icon: "webhook", name: "On webhook", desc: "Start when an external event fires" },
  { id: "cron", icon: "calendar", name: "Cron schedule", desc: "Recurring on an expression" },
  { id: "interval", icon: "refresh-cw", name: "Fixed interval", desc: "Every N minutes/hours" },
  { id: "oneshot", icon: "zap", name: "One-shot", desc: "Run once at a time" },
];

const CRON_PRESETS = ["0 2 * * *", "0 */6 * * *", "0 9 * * 1"];

const CRON_HUMAN: Record<string, string> = {
  "0 2 * * *": "At 02:00, every day",
  "0 */6 * * *": "Every 6 hours",
  "0 9 * * 1": "At 09:00, every Monday",
};

const FIRE_TIMES = [
  "Tomorrow · 02:00 EST",
  "Thu Jun 5 · 02:00 EST",
  "Fri Jun 6 · 02:00 EST",
  "Sat Jun 7 · 02:00 EST",
];

// Agent Detail — Schedule tab. Visual schedule builder: trigger-mode selector,
// cron expression with quick presets + human-readable preview, missed-run policy,
// and a preview of upcoming fire times. Selections are local UI state; fire-time
// strings are illustrative (mirrors the design prototype).
export default function ScheduleTab() {
  const agent = useCurrentAgent();
  const showToast = useUI((s) => s.showToast);
  const [mode, setMode] = useState<Mode>("webhook");
  const [cron, setCron] = useState("0 2 * * *");
  const [policy, setPolicy] = useState<MissedPolicy>("skip");

  const human = useMemo(() => CRON_HUMAN[cron] ?? "Custom expression", [cron]);

  return (
    <div className="db-schedule">
      <div className="db-sched-l">
        <div className="db-sublabel">Trigger</div>
        <div className="db-sched-modes">
          {MODES.map((m) => (
            <button
              key={m.id}
              className={"db-sched-mode" + (mode === m.id ? " sel" : "")}
              onClick={() => setMode(m.id)}
            >
              <span className="db-sched-mode-icon"><Icon name={m.icon} size={16} /></span>
              <div>
                <div className="db-sched-mode-name">{m.name}</div>
                <div className="db-sched-mode-desc">{m.desc}</div>
              </div>
              {mode === m.id && (
                <Icon name="check-circle" size={16} style={{ color: "var(--accent)", marginLeft: "auto" }} />
              )}
            </button>
          ))}
        </div>

        {mode === "cron" && (
          <div className="db-sched-cron">
            <div className="db-sublabel" style={{ marginTop: 18 }}>Expression</div>
            <input className="db-input db-mono" value={cron} onChange={(e) => setCron(e.target.value)} />
            <div className="db-cron-presets">
              {CRON_PRESETS.map((c) => (
                <button key={c} className="db-cron-preset db-mono" onClick={() => setCron(c)}>{c}</button>
              ))}
            </div>
            <div className="db-cron-human db-mono"><Icon name="clock" size={13} /> {human} · EST</div>
          </div>
        )}

        <div className="db-sublabel" style={{ marginTop: 18 }}>Missed-run policy</div>
        <Segmented<MissedPolicy>
          value={policy}
          onChange={setPolicy}
          options={[
            { value: "skip", label: "Skip" },
            { value: "once", label: "Run once" },
            { value: "coalesce", label: "Coalesce" },
          ]}
        />
      </div>

      <div className="db-sched-r">
        <div className="db-panel">
          <div className="db-panel-head"><h3 className="db-panel-title">Next fire times</h3></div>
          {mode === "webhook" ? (
            <div className="db-muted db-mono" style={{ padding: "4px 0" }}>
              Event-driven · no scheduled fires. Listening on {agent.name}'s webhook.
            </div>
          ) : (
            <div className="db-fire-list">
              {FIRE_TIMES.map((f, i) => (
                <div key={i} className="db-fire-row db-mono"><Icon name="clock" size={13} /> {f}</div>
              ))}
            </div>
          )}
        </div>
        <Button
          variant="primary"
          icon="save"
          onClick={() => showToast({ text: "Schedule saved" })}
          style={{ marginTop: 16 }}
        >
          Save schedule
        </Button>
      </div>
    </div>
  );
}
