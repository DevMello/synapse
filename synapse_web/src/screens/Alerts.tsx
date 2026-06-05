// Alerts — anomaly / observability feed from the cloud detection engine.
// Ported from design-reference/app/Views.jsx → Alerts(), docs/web-ui.md §4.13.
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Icon } from "../components/Primitives";
import { PageHead, EmptyState, Segmented } from "../components/Common";
import { useAlerts } from "../api/queries";
import type { AlertSeverity } from "../types";

type SevFilter = "all" | AlertSeverity;

export default function Alerts() {
  const { data: alerts = [] } = useAlerts();
  const navigate = useNavigate();
  const [sev, setSev] = useState<SevFilter>("all");

  const shown = sev === "all" ? alerts : alerts.filter((a) => a.sev === sev);
  const warnCount = alerts.filter((a) => a.sev === "warn").length;

  return (
    <>
      <PageHead
        kicker="Alerts"
        title="What the fleet"
        serif="flagged for you"
        sub="Anomalies from the cloud detection engine: cost spikes, latency regressions, silent agents, offline daemons, and prompt-injection spikes."
        actions={alerts.length > 0 && (
          <span className="db-queue-count db-mono">
            <span className="eyebrow-pulse" style={{ position: "static" }} />
            {warnCount} need{warnCount === 1 ? "s" : ""} attention
          </span>
        )}
      />

      {alerts.length > 0 && (
        <div className="db-toolbar">
          <Segmented<SevFilter>
            value={sev}
            onChange={setSev}
            options={[
              { value: "all", label: "All" },
              { value: "warn", label: "Warnings" },
              { value: "info", label: "Info" },
            ]}
          />
        </div>
      )}

      {shown.length === 0 ? (
        <EmptyState name="alerts" icon="check-check" />
      ) : (
        <div className="db-alert-list">
          {shown.map((al) => (
            <div key={al.id} className={"db-alert-card sev-" + al.sev}>
              <span className={"db-alert-icon lg " + al.sev}><Icon name={al.icon} size={20} /></span>
              <div className="db-alert-card-meta">
                <div className="db-alert-card-top">
                  <h3 className="db-alert-card-title">{al.title}</h3>
                  <span className="db-mono db-muted">{al.when}</span>
                </div>
                <p className="db-alert-card-detail">{al.detail}</p>
                <div className="db-alert-metrics db-mono">
                  <span className="db-alert-metric">
                    <span className="db-alert-metric-l">{al.metric}</span>
                    baseline <b>{al.baseline}</b> → observed <b className="db-accent">{al.observed}</b>
                  </span>
                  <button
                    className="db-link"
                    onClick={() => navigate(al.type === "offline" ? "/daemons" : "/runs")}
                  >
                    <Icon name="external-link" size={13} /> {al.type === "offline" ? "View daemon" : "View runs"}
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </>
  );
}
