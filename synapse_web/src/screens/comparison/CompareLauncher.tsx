// "Compare models" launcher (§10.12). A model multi-select grouped by provider, each with
// a per-model cost estimate and a running group total; an optional group cost cap; and a
// clear N× cost confirmation before launching. Used inside the Agent Detail "Compare" tab.
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Button, Icon } from "../../components/Primitives";
import { useUI } from "../../store/ui";
import { useComparisonModels, useComparisons, useLaunchComparison } from "../../api/queries";
import type { AvailableModel } from "../../types";
import "../../styles/comparison.css";

export default function CompareLauncher({ agentId, agentName }: { agentId: string; agentName: string }) {
  const navigate = useNavigate();
  const showToast = useUI((s) => s.showToast);
  const { data: models = [] } = useComparisonModels(agentId);
  const { data: groups = [] } = useComparisons(agentId);
  const launch = useLaunchComparison();

  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [capOn, setCapOn] = useState(false);
  const [cap, setCap] = useState(1);
  const [maxParallel, setMaxParallel] = useState(3);
  const [confirming, setConfirming] = useState(false);

  const byProvider = useMemo(() => groupByProvider(models), [models]);
  const total = useMemo(
    () => models.filter((m) => selected.has(m.model)).reduce((s, m) => s + m.estimateUsd, 0),
    [models, selected],
  );
  const n = selected.size;

  function toggle(model: string, ok: boolean) {
    if (!ok) return;
    setSelected((prev) => {
      const next = new Set(prev);
      next.has(model) ? next.delete(model) : next.add(model);
      return next;
    });
  }

  function doLaunch() {
    launch.mutate(
      {
        agentId,
        models: [...selected],
        groupCostCap: capOn ? cap : null,
        maxParallelVariants: maxParallel,
      },
      {
        onSuccess: (res) => {
          showToast({ text: `Comparison launched across ${n} models` });
          if (res.id) navigate(`/comparisons/${res.id}`);
        },
        onError: (e) => showToast({ text: (e as Error).message, variant: "warn" }),
      },
    );
    setConfirming(false);
  }

  return (
    <div className="db-tools">
      <div className="db-callout">
        <Icon name="git-pull-request" size={16} />
        <span>
          <b>Compare models.</b> Run <b>{agentName}</b>'s task across several models at once in{" "}
          <b>draft mode</b> — read-only tools run, but side-effecting calls are simulated, so
          nothing real happens. Review the columns, then pick a winner.
        </span>
      </div>

      {/* ── model multi-select (grouped by provider) ─────────────────── */}
      <div className="db-panel">
        <div className="db-panel-head"><h3 className="db-panel-title">Select models</h3></div>
        {byProvider.map(([provider, list]) => (
          <div key={provider} className="cmp-provider">
            <div className="cmp-provider-label">{provider}</div>
            <div className="cmp-model-grid">
              {list.map((m) => (
                <button
                  key={m.model}
                  className={
                    "cmp-model-chip" +
                    (selected.has(m.model) ? " on" : "") +
                    (m.hasCredentials ? "" : " disabled")
                  }
                  disabled={!m.hasCredentials}
                  title={m.hasCredentials ? "" : "No provider credentials on this daemon"}
                  onClick={() => toggle(m.model, m.hasCredentials)}
                >
                  <span className="cmp-model-name">{m.model}</span>
                  <span className="cmp-model-price db-mono">
                    ~${m.estimateUsd.toFixed(4)}
                    {!m.hasCredentials && <span className="cmp-nokey"> no key</span>}
                  </span>
                </button>
              ))}
            </div>
          </div>
        ))}

        {/* ── controls ───────────────────────────────────────────────── */}
        <div className="cmp-controls">
          <label className="cmp-control">
            <input type="checkbox" checked={capOn} onChange={(e) => setCapOn(e.target.checked)} />
            <span>Group cost cap</span>
            <input
              className="db-input" type="number" step="0.5" min={0} disabled={!capOn}
              style={{ marginBottom: 0, width: 90 }}
              value={cap} onChange={(e) => setCap(Number(e.target.value))}
            />
          </label>
          <label className="cmp-control">
            <span>Max parallel</span>
            <input
              className="db-input" type="number" min={1} max={16}
              style={{ marginBottom: 0, width: 80 }}
              value={maxParallel} onChange={(e) => setMaxParallel(Number(e.target.value))}
            />
          </label>
        </div>

        {/* ── estimate + launch ──────────────────────────────────────── */}
        <div className="cmp-launchbar">
          <div className="cmp-estimate db-mono">
            <Icon name="dollar-sign" size={14} />
            <b>{n}</b> model{n === 1 ? "" : "s"} · est. group total{" "}
            <b className="db-accent">${total.toFixed(4)}</b>
            {n > 1 && <span className="cmp-nx"> (~{n}× a single run)</span>}
          </div>
          {confirming ? (
            <div className="cmp-confirm">
              <span>Launch {n} draft runs for ~${total.toFixed(4)}?</span>
              <Button variant="primary" icon="check-circle" onClick={doLaunch}>Run comparison</Button>
              <Button variant="outline-light" onClick={() => setConfirming(false)}>Cancel</Button>
            </div>
          ) : (
            <Button
              variant="primary"
              icon="git-pull-request"
              disabled={n < 2}
              onClick={() => setConfirming(true)}
            >
              Compare {n > 1 ? `${n} models` : "models"}
            </Button>
          )}
        </div>
        {n < 2 && <div className="cmp-hint db-muted db-mono">Pick at least two models to compare.</div>}
      </div>

      {/* ── recent comparisons for this agent ──────────────────────────── */}
      <div className="db-panel">
        <div className="db-panel-head"><h3 className="db-panel-title">Recent comparisons {groups.length}</h3></div>
        {groups.length === 0 ? (
          <div className="db-mono db-muted" style={{ padding: 12 }}>No comparisons yet.</div>
        ) : (
          <div className="db-table-wrap">
            <table className="db-table">
              <thead><tr><th>Models</th><th>Status</th><th>Total</th><th>When</th><th></th></tr></thead>
              <tbody>
                {groups.map((g) => (
                  <tr key={g.id}>
                    <td className="db-mono">{g.models.join(", ")}</td>
                    <td><span className={"cmp-status cmp-status--" + g.status}>{g.status.replace(/_/g, " ")}</span></td>
                    <td className="db-mono">${g.totalCostUsd.toFixed(4)}</td>
                    <td className="db-mono db-muted">{g.created}</td>
                    <td>
                      <button className="db-inline-link" onClick={() => navigate(`/comparisons/${g.id}`)}>
                        open <Icon name="arrow-right" size={13} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

function groupByProvider(models: AvailableModel[]): [string, AvailableModel[]][] {
  const map = new Map<string, AvailableModel[]>();
  for (const m of models) {
    const arr = map.get(m.provider) ?? [];
    arr.push(m);
    map.set(m.provider, arr);
  }
  return [...map.entries()];
}
