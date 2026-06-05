// Approvals — the live HITL queue. Paused runs awaiting a human decision; each gate
// is RBAC-checked, audit-logged, and routed back to the daemon to resume or abort.
// Approve/deny mutates the global UI store so the sidebar Approvals badge stays in sync.
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { HatchCorners, Icon } from "../components/Primitives";
import { PageHead, SectionRow } from "../components/Common";
import { useUI } from "../store/ui";
import type { Approval } from "../types";

export default function Approvals() {
  const navigate = useNavigate();
  const queue = useUI((s) => s.approvals);
  const resolved = useUI((s) => s.resolved);
  const resolveApproval = useUI((s) => s.resolveApproval);
  const showToast = useUI((s) => s.showToast);

  // Optional per-card reason note, keyed by approval id.
  const [reasons, setReasons] = useState<Record<string, string>>({});

  function decide(ap: Approval, decision: "approve" | "deny") {
    const reason = reasons[ap.id]?.trim() || undefined;
    resolveApproval(ap.id, decision, reason);
    showToast({
      text: decision === "approve"
        ? `Approved — routed to ${ap.daemon} to resume`
        : `Denied — run aborted on ${ap.daemon}`,
      variant: decision === "approve" ? "ok" : "warn",
    });
  }

  return (
    <>
      <PageHead
        kicker="Approvals"
        title="Paused runs"
        serif="awaiting your call"
        sub="Each gate is RBAC-checked, written to the audit log, and routed back to the daemon to resume or abort. The same gate is mirrored to Slack, Discord, and Email."
        actions={queue.length > 0 && (
          <span className="db-queue-count db-mono">
            <span className="eyebrow-pulse" style={{ position: "static" }} />
            {queue.length} in queue
          </span>
        )}
      />

      {queue.length === 0 ? (
        <div className="db-empty">
          <HatchCorners onLight />
          <span className="db-empty-icon ok"><Icon name="check-check" size={22} /></span>
          <div className="db-empty-caption">
            Queue clear · every gate resolved. Decisions are in the{" "}
            <span className="db-empty-cmd">audit log</span>.
          </div>
        </div>
      ) : (
        <div className="db-approvals">
          {queue.map((ap) => (
            <div key={ap.id} className="db-approval-card">
              <div className="db-approval-l">
                <div className="db-approval-head">
                  <span className={"db-sev-badge " + ap.severity}>
                    <Icon name="shield-alert" size={14} />{" "}
                    {ap.severity === "block" ? "blocked" : "requires approval"}
                  </span>
                  <button
                    className="db-approval-agent db-mono"
                    onClick={() => navigate(`/agents/${ap.agentId}`)}
                  >
                    <Icon name="cpu" size={12} /> {ap.agent}
                  </button>
                  <span className="db-mono db-muted">· {ap.daemon} · {ap.when}</span>
                </div>
                <h3 className="db-approval-action">{ap.action}</h3>
                <div className="db-approval-cmd db-mono">
                  <span className="db-cmd-prompt">$</span> {ap.command}
                </div>
                <div className="db-approval-reason">
                  <div className="db-sublabel">Agent's reasoning</div>
                  <p>{ap.reason}</p>
                </div>
                <div className="db-approval-context db-mono">
                  <Icon name="corner-down-right" size={13} /> {ap.context}
                </div>
              </div>
              <div className="db-approval-r">
                <div className="db-sublabel">Decision</div>
                <textarea
                  className="db-input db-approval-note"
                  placeholder="Optional reason (logged)…"
                  value={reasons[ap.id] || ""}
                  onChange={(e) => setReasons((p) => ({ ...p, [ap.id]: e.target.value }))}
                />
                <button
                  className="btn btn-primary db-approval-btn"
                  onClick={() => decide(ap, "approve")}
                >
                  <Icon name="check" size={15} stroke={2} /> Approve & resume
                </button>
                <button
                  className="btn btn-danger-ghost db-approval-btn"
                  onClick={() => decide(ap, "deny")}
                >
                  <Icon name="x" size={15} stroke={2} /> Deny & abort
                </button>
                <div className="db-approval-mirror db-mono">
                  <Icon name="slack" size={12} /> mirrored to #ops-approvals
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {resolved.length > 0 && (
        <>
          <SectionRow title="Just resolved" />
          <div className="db-resolved-list">
            {resolved.map((r) => (
              <div key={r.id} className="db-resolved-row">
                <span className={"db-resolved-icon " + r.decision}>
                  <Icon name={r.decision === "approve" ? "check" : "x"} size={14} />
                </span>
                <span className="db-resolved-action">{r.action}</span>
                <span className="db-mono db-muted">
                  {r.agent} · {r.decision === "approve" ? "resumed" : "aborted"}
                </span>
                {r.reason && (
                  <span className="db-mono db-muted db-resolved-reason">“{r.reason}”</span>
                )}
              </div>
            ))}
          </div>
        </>
      )}
    </>
  );
}
