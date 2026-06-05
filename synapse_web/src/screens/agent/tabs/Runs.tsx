// Agent Detail — Runs tab (hero #2: the live trace viewer).
// Left: this agent's run list (selectable). Right: the live streaming trace
// viewer, or — for a run in a recovery state — a checkpoint progress marker with
// Resume / Restart / Abort overrides. Ported from design-reference RunsTab.
import { useSearchParams } from "react-router-dom";
import { useCurrentAgent } from "../context";
import { useRuns } from "../../../api/queries";
import { Button, Chip } from "../../../components/Primitives";
import { TraceViewer } from "../Trace";
import type { Run } from "../../../types";

export default function RunsTab() {
  const agent = useCurrentAgent();
  const { data: allRuns } = useRuns();
  const [params, setParams] = useSearchParams();

  const runs: Run[] = (allRuns ?? []).filter((r) => r.agentId === agent.id);
  const live = runs.find((r) => r.status === "running");
  const recovering = runs.find((r) => r.status === "recovering");

  // Deep-linkable selection via ?runId=, else the live run, else the first run.
  const requested = params.get("runId");
  const fallback = live?.id ?? runs[0]?.id;
  const sel = runs.some((r) => r.id === requested) ? requested! : fallback;
  const selectRun = (id: string) => {
    const next = new URLSearchParams(params);
    next.set("runId", id);
    setParams(next, { replace: true });
  };

  const showRecovery = recovering != null && sel === recovering.id;

  return (
    <div className="db-runs">
      <div className="db-runs-list-col">
        <div className="db-sublabel">Run history</div>
        <div className="db-runs-list">
          {runs.map((r) => (
            <button
              key={r.id}
              className={"db-run-item" + (sel === r.id ? " sel" : "")}
              onClick={() => selectRun(r.id)}
              type="button"
            >
              <Chip s={r.status} />
              <div className="db-run-item-meta">
                <div className="db-run-item-id db-mono">#{r.id.replace("r", "")}</div>
                <div className="db-run-item-sub db-mono">{r.trigger} · {r.started}</div>
              </div>
              <div className="db-run-item-cost db-mono">${r.cost.toFixed(2)}</div>
            </button>
          ))}
        </div>
      </div>

      <div className="db-runs-trace-col">
        {showRecovery && recovering ? (
          <div className="db-recovery">
            <div className="db-recovery-head">
              <span className="status-chip recovering">recovering</span>
              <span className="db-mono">run #{recovering.id.replace("r", "")} · checkpoint resume</span>
            </div>
            <div className="db-recovery-progress">
              <div className="db-recovery-bar"><div className="db-recovery-fill" style={{ width: "47%" }} /></div>
              <div className="db-mono db-muted">step 14 / 30 · resumed on macbook-pro-m3 after a dropped connection</div>
            </div>
            <div className="db-recovery-actions">
              <Button variant="primary" icon="play">Resume</Button>
              <Button variant="outline-light" icon="refresh-cw">Restart</Button>
              <Button variant="danger-ghost" icon="square">Abort</Button>
            </div>
            <p className="db-muted db-mono" style={{ marginTop: 14 }}>
              Auto-recovery is handling this. Manual override is here for the rare case it needs a human decision.
            </p>
          </div>
        ) : (
          <TraceViewer
            // Remount per selected run so each starts from a clean stream state
            // (otherwise stale `shown`/`playing` from the prior run would leak in).
            key={sel ?? "none"}
            autoplay={sel != null && sel === live?.id}
            title={`${agent.name} · run #${(sel ?? "").replace("r", "")}`}
            embedded
          />
        )}
      </div>
    </div>
  );
}
