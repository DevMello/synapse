// Agent Detail — Overview tab. Ported from the prototype's AgentOverview:
// a 2-col grid with metric cards + recent-runs table on the left, and Host /
// Quick-edit panels on the right.
import { useSearchParams, useNavigate } from "react-router-dom";
import { useCurrentAgent } from "../context";
import { useRuns } from "../../../api/queries";
import { data } from "../../../api/queries";
import { Icon, Chip } from "../../../components/Primitives";
import { MetricCard, SectionRow, Link, daemonName } from "../../../components/Common";

export default function OverviewTab() {
  const agent = useCurrentAgent();
  const [, setParams] = useSearchParams();
  const navigate = useNavigate();
  const { data: allRuns } = useRuns();

  const recent = (allRuns ?? []).filter((r) => r.agentId === agent.id);
  const host = data.daemons.find((d) => d.id === agent.daemonId);

  const goTab = (tab: string) => setParams({ tab });

  return (
    <div className="db-ov-grid">
      <div className="db-ov-main">
        <div className="db-metric-grid db-metric-grid-3">
          <MetricCard
            label="Availability"
            n={agent.avail ? "Online" : "Offline"}
            sub={agent.avail ? `${daemonName(agent.daemonId)} healthy` : "host offline"}
          />
          <MetricCard label="Next run" n={agent.nextRun} sub="timezone EST" />
          <MetricCard
            label="Spend today"
            n={"$" + agent.spendToday.toFixed(2)}
            delta={`${(agent.tokensToday / 1e6).toFixed(2)}M tokens`}
          />
        </div>

        <SectionRow title="Recent runs">
          <Link icon="external-link" onClick={() => goTab("runs")}>All runs</Link>
        </SectionRow>
        <div className="db-table-wrap">
          <table className="db-table">
            <thead>
              <tr>
                <th>Run</th><th>Trigger</th><th>Started</th><th>Duration</th><th>Cost</th><th>Status</th>
              </tr>
            </thead>
            <tbody>
              {recent.length ? (
                recent.map((r) => (
                  <tr key={r.id} className="clickable-row" onClick={() => goTab("runs")}>
                    <td className="db-cell-primary db-mono">#{r.id.replace("r", "")}</td>
                    <td className="db-mono">{r.trigger}</td>
                    <td className="db-mono">{r.started}</td>
                    <td className="db-mono">{r.dur}</td>
                    <td className="db-mono">${r.cost.toFixed(2)}</td>
                    <td><Chip s={r.status} /></td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={6}>
                    <div className="db-muted db-mono" style={{ padding: "8px 0" }}>No runs yet.</div>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="db-ov-side">
        <div className="db-panel">
          <div className="db-panel-head"><h3 className="db-panel-title">Host</h3></div>
          <button className="db-ov-host" onClick={() => navigate("/daemons")}>
            <span className={"db-status-dot " + (host ? host.status : "offline")} />
            <div>
              <div className="db-ov-host-name">{host ? host.name : "—"}</div>
              <div className="db-ov-host-os db-mono">{host ? host.os : ""}</div>
            </div>
            <Icon name="chevron-right" size={16} style={{ color: "var(--mute)", marginLeft: "auto" }} />
          </button>
          <div className="db-ov-facts">
            <div className="db-ov-fact"><span className="db-ov-fact-l">Version</span><span className="db-mono">{agent.model}</span></div>
            <div className="db-ov-fact"><span className="db-ov-fact-l">Error rate</span><span className="db-mono">{agent.errRate}%</span></div>
            <div className="db-ov-fact"><span className="db-ov-fact-l">Total runs</span><span className="db-mono">{agent.runsTotal.toLocaleString()}</span></div>
          </div>
        </div>

        <div className="db-panel">
          <div className="db-panel-head"><h3 className="db-panel-title">Quick edit</h3></div>
          <div className="db-ov-links">
            <button className="db-ov-link" onClick={() => goTab("editor")}>
              <Icon name="file-text" size={15} /> Prompt &amp; skills <Icon name="chevron-right" size={15} className="db-ov-link-arr" />
            </button>
            <button className="db-ov-link" onClick={() => goTab("tools")}>
              <Icon name="puzzle" size={15} /> Tools &amp; blockers <Icon name="chevron-right" size={15} className="db-ov-link-arr" />
            </button>
            <button className="db-ov-link" onClick={() => goTab("schedule")}>
              <Icon name="calendar" size={15} /> Schedule <Icon name="chevron-right" size={15} className="db-ov-link-arr" />
            </button>
            <button className="db-ov-link" onClick={() => goTab("memory")}>
              <Icon name="brain" size={15} /> Memory <Icon name="chevron-right" size={15} className="db-ov-link-arr" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
